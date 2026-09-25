"""The single place the application talks to the Claude API.

Every pipeline stage calls `generate(...)` with a prompt and the Pydantic model
it expects back. The client:

1. asks Claude for JSON matching that model's schema (API structured outputs);
2. validates the reply with Pydantic, which also applies our own business rules
   (ID formats, unique IDs, rationale on critical questions);
3. if validation fails, retries once, telling Claude exactly what was wrong;
4. converts SDK exceptions into friendly application errors.

Anything that follows the `LLMClient` protocol can stand in for Claude. The
tests use a fake client, so they need no API key and cost nothing.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.utils.errors import AIResponseError, AIServiceError, MissingCredentialsError
from app.utils.json_parsing import parse_model

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

MAX_ATTEMPTS = 2  # first try + one corrective retry


@dataclass
class CallRecord:
    """Usage log for one stage, used for cost and latency reporting."""

    stage: str
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    succeeded: bool = False


class LLMClient(Protocol):
    calls: list[CallRecord]

    def generate(
        self, *, stage: str, system: str, prompt: str, output_model: type[ModelT], context: dict | None = None
    ) -> ModelT: ...


@dataclass
class ClaudeClient:
    settings: Settings = field(default_factory=get_settings)
    calls: list[CallRecord] = field(default_factory=list)
    _client: anthropic.Anthropic | None = field(default=None, repr=False)

    def __post_init__(self):
        if not self.settings.has_api_key:
            raise MissingCredentialsError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(
            api_key=self.settings.anthropic_api_key,
            timeout=180.0,
            max_retries=2,  # the SDK retries rate limits, 5xx and connection errors
        )

    def generate(
        self, *, stage: str, system: str, prompt: str, output_model: type[ModelT], context: dict | None = None
    ) -> ModelT:
        """`context` is passed to validation, e.g. {"known_ids": {...}} for reference checks."""
        record = CallRecord(stage=stage)
        self.calls.append(record)
        schema = anthropic.transform_schema(output_model)
        messages: list[dict] = [{"role": "user", "content": prompt}]
        started = time.monotonic()
        last_error: AIResponseError | None = None

        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                record.attempts = attempt
                response = self._call(system, messages, schema)
                record.input_tokens += response.usage.input_tokens
                record.output_tokens += response.usage.output_tokens

                text = self._response_text(response, stage)
                try:
                    result = parse_model(text, output_model, context)
                    record.succeeded = True
                    return result
                except AIResponseError as exc:
                    last_error = exc
                    logger.warning("Stage %s attempt %d failed validation: %s", stage, attempt, exc.detail)
                    # Show Claude its own answer and what was wrong with it, then ask again.
                    messages += [
                        {"role": "assistant", "content": text},
                        {"role": "user", "content": _correction_prompt(exc.detail)},
                    ]
        finally:
            record.seconds = round(time.monotonic() - started, 2)

        raise last_error  # both attempts failed validation

    def _call(self, system: str, messages: list[dict], schema: dict):
        try:
            return self._client.messages.create(
                model=self.settings.model,
                max_tokens=self.settings.max_output_tokens,
                system=system,
                messages=messages,
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.AuthenticationError as exc:
            raise MissingCredentialsError(
                str(exc), "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in your .env file."
            ) from exc
        except anthropic.PermissionDeniedError as exc:
            raise AIServiceError(str(exc), "This API key doesn't have permission to use the configured model.") from exc
        except anthropic.NotFoundError as exc:
            raise AIServiceError(
                str(exc), f"Model '{self.settings.model}' was not found. Check CLAUDE_MODEL in your .env file."
            ) from exc
        except anthropic.RateLimitError as exc:
            raise AIServiceError(str(exc), "The AI service is busy (rate limit reached). Wait a minute and try again.") from exc
        except anthropic.BadRequestError as exc:
            if "credit balance" in str(exc).lower():
                raise AIServiceError(
                    str(exc), "Your Anthropic account is out of credits. Add credits in the Anthropic Console."
                ) from exc
            raise AIServiceError(str(exc), "The AI service rejected the request. Try shortening the input.") from exc
        except anthropic.APITimeoutError as exc:
            raise AIServiceError(str(exc), "The AI service took too long to respond. Please try again.") from exc
        except anthropic.APIConnectionError as exc:
            raise AIServiceError(str(exc), "Couldn't reach the AI service. Check your internet connection.") from exc
        except anthropic.APIStatusError as exc:
            raise AIServiceError(str(exc), "The AI service returned an error. Please try again shortly.") from exc

    @staticmethod
    def _response_text(response, stage: str) -> str:
        if response.stop_reason == "refusal":
            raise AIResponseError(
                f"{stage}: model declined the request",
                "The AI declined to analyse this request. Rephrase it as a business need and try again.",
            )
        if response.stop_reason == "max_tokens":
            raise AIResponseError(
                f"{stage}: output hit the max_tokens limit",
                "The AI's answer was too long and got cut off. Try a shorter or more focused request.",
            )
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise AIResponseError(f"{stage}: response contained no text")
        return text


def _correction_prompt(errors: str) -> str:
    return (
        "Your previous response did not pass validation:\n"
        f"{errors}\n\n"
        "Return the complete corrected JSON. Keep everything that was valid and fix only these problems."
    )


def summarize_usage(calls: list[CallRecord]) -> dict:
    """Totals across all stages, for display in the UI."""
    return {
        "calls": len(calls),
        "attempts": sum(c.attempts for c in calls),
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "seconds": round(sum(c.seconds for c in calls), 1),
    }

