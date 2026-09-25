"""Turning raw AI output into validated models.

The Claude client asks for structured tool output, so responses normally
arrive as dicts. This module is the safety net for anything else: JSON
wrapped in Markdown fences, text before or after the JSON, or JSON whose
shape does not match the schema.
"""

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.utils.errors import AIResponseError

ModelT = TypeVar("ModelT", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict | list:
    """Find and parse the first JSON object or array in `text`."""
    if not text or not text.strip():
        raise AIResponseError("AI response was empty")

    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        span = _outermost_json_span(candidate)
        if span:
            try:
                return json.loads(span)
            except json.JSONDecodeError:
                continue
    raise AIResponseError(f"No valid JSON found in AI response: {text[:200]!r}")


def _outermost_json_span(text: str) -> str | None:
    """Return the first balanced {...} or [...] block, respecting strings."""
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        return None
    stack, in_string, escaped = [], False, False
    pairs = {"{": "}", "[": "]"}
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in "}]":
            if not stack or stack.pop() != ch:
                return None
            if not stack:
                return text[start : i + 1]
    return None


def format_validation_errors(exc: ValidationError, limit: int = 8) -> str:
    """Summarise Pydantic errors compactly, e.g. for a retry prompt."""
    lines = []
    for err in exc.errors()[:limit]:
        location = ".".join(str(part) for part in err["loc"]) or "(root)"
        lines.append(f"- {location}: {err['msg']}")
    extra = len(exc.errors()) - limit
    if extra > 0:
        lines.append(f"- ...and {extra} more")
    return "\n".join(lines)


def parse_model(payload: str | dict | list, model: type[ModelT], context: dict | None = None) -> ModelT:
    """Validate an AI payload (raw text or already-parsed JSON) against a model.

    `context` is passed to Pydantic validators, e.g. {"known_ids": {...}} so
    cross-stage references can be checked.
    """
    data = extract_json(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise AIResponseError(f"Expected a JSON object for {model.__name__}, got {type(data).__name__}")
    try:
        return model.model_validate(data, context=context)
    except ValidationError as exc:
        raise AIResponseError(
            f"{model.__name__} failed validation:\n{format_validation_errors(exc)}"
        ) from exc
