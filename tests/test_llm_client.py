"""ClaudeClient behavior with the Anthropic SDK stubbed out."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.config import Settings
from app.models.artifacts import RequirementsResult
from app.services.llm_client import ClaudeClient, summarize_usage
from app.utils.errors import AIResponseError, AIServiceError, MissingCredentialsError
from tests.fakes import StubMessages, fake_message

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def make_settings(key="test-key") -> Settings:
    return Settings(
        anthropic_api_key=key, model="test-model", max_output_tokens=1000,
        database_path=None, demo_mode=False,
    )


def make_client(replies) -> tuple[ClaudeClient, StubMessages]:
    client = ClaudeClient(settings=make_settings())
    stub = StubMessages(replies)
    client._client = SimpleNamespace(messages=stub)
    return client, stub


def generate(client):
    return client.generate(stage="requirements", system="sys", prompt="prompt", output_model=RequirementsResult)


def status_error(cls, code, message="error"):
    return cls(message, response=httpx2.Response(code, request=REQUEST), body=None)


# --- Happy path ----------------------------------------------------------------

def test_valid_response_is_parsed_and_logged(order_stages):
    client, stub = make_client([fake_message(order_stages["requirements"], input_tokens=900, output_tokens=400)])
    result = generate(client)

    assert [r.id for r in result.functional] == ["FR-001", "FR-002", "FR-003"]
    record = client.calls[0]
    assert (record.stage, record.attempts, record.succeeded) == ("requirements", 1, True)
    assert (record.input_tokens, record.output_tokens) == (900, 400)


def test_request_uses_configured_model_and_json_schema(order_stages):
    client, stub = make_client([fake_message(order_stages["requirements"])])
    generate(client)

    sent = stub.requests[0]
    assert sent["model"] == "test-model"
    assert sent["system"] == "sys"
    output_format = sent["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert "functional" in output_format["schema"]["properties"]


# --- Corrective retry ----------------------------------------------------------

def test_invalid_response_is_retried_with_error_feedback(order_stages):
    bad = {"functional": [{"id": "REQ-1", "description": "x"}]}
    client, stub = make_client([fake_message(bad), fake_message(order_stages["requirements"])])
    result = generate(client)

    assert len(result.functional) == 3
    assert client.calls[0].attempts == 2
    assert client.calls[0].input_tokens == 200  # both attempts are counted
    retry_messages = stub.requests[1]["messages"]
    assert [m["role"] for m in retry_messages] == ["user", "assistant", "user"]
    assert "functional.0.id" in retry_messages[2]["content"]


def test_duplicate_ids_trigger_retry(order_stages):
    duplicated = order_stages["requirements"]
    duplicated["functional"][1]["id"] = "FR-001"
    client, stub = make_client([fake_message(duplicated), fake_message(duplicated)])
    with pytest.raises(AIResponseError, match="duplicate IDs"):
        generate(client)
    assert client.calls[0].succeeded is False


def test_unparseable_text_twice_raises():
    client, _ = make_client([fake_message("not json"), fake_message("still not json")])
    with pytest.raises(AIResponseError):
        generate(client)
    assert client.calls[0].attempts == 2


# --- Stop reasons ------------------------------------------------------------------

def test_refusal_is_reported_clearly(order_stages):
    client, _ = make_client([fake_message(order_stages["requirements"], stop_reason="refusal")])
    with pytest.raises(AIResponseError) as info:
        generate(client)
    assert "declined" in info.value.user_message


def test_truncated_output_is_reported(order_stages):
    client, _ = make_client([fake_message('{"functional": [', stop_reason="max_tokens")])
    with pytest.raises(AIResponseError) as info:
        generate(client)
    assert "cut off" in info.value.user_message


# --- API errors ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("error", "expected_type", "expected_text"),
    [
        (status_error(anthropic.AuthenticationError, 401), MissingCredentialsError, "rejected"),
        (status_error(anthropic.RateLimitError, 429), AIServiceError, "rate limit"),
        (status_error(anthropic.NotFoundError, 404), AIServiceError, "test-model"),
        (status_error(anthropic.BadRequestError, 400, "Your credit balance is too low"), AIServiceError, "out of credits"),
        (status_error(anthropic.InternalServerError, 500), AIServiceError, "returned an error"),
        (anthropic.APIConnectionError(request=REQUEST), AIServiceError, "internet connection"),
        (anthropic.APITimeoutError(request=REQUEST), AIServiceError, "too long"),
    ],
)
def test_api_errors_become_friendly_messages(error, expected_type, expected_text):
    client, _ = make_client([error])
    with pytest.raises(expected_type) as info:
        generate(client)
    assert expected_text in info.value.user_message


# --- Credentials & usage -------------------------------------------------------

def test_missing_api_key_fails_fast():
    with pytest.raises(MissingCredentialsError) as info:
        ClaudeClient(settings=make_settings(key=None))
    assert "Demo Mode" in info.value.user_message


def test_settings_repr_never_shows_key():
    assert "test-key" not in repr(make_settings())


def test_usage_summary(order_stages):
    client, _ = make_client([fake_message(order_stages["requirements"])] * 2)
    generate(client)
    generate(client)
    assert summarize_usage(client.calls) == {
        "calls": 2, "attempts": 2, "input_tokens": 200, "output_tokens": 100, "seconds": 0.0,
    }
