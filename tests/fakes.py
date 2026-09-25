"""Test doubles for the AI layer. No network access, no API key, no cost."""

import json
import threading
from types import SimpleNamespace

from app.services.llm_client import CallRecord
from app.utils.json_parsing import parse_model


class FakeLLMClient:
    """Stands in for ClaudeClient at the pipeline level.

    `responses` maps a stage name to the payload that stage should return
    (a dict, or an Exception to raise). Every request is recorded so tests can
    inspect the prompts that were sent.
    """

    def __init__(self, responses: dict):
        self.responses = responses
        self.requests: list[dict] = []
        self.calls: list[CallRecord] = []
        self._lock = threading.Lock()  # stages may run in parallel threads

    def generate(self, *, stage, system, prompt, output_model, context=None):
        with self._lock:
            self.requests.append({"stage": stage, "system": system, "prompt": prompt})
            self.calls.append(CallRecord(stage=stage, attempts=1, succeeded=True))
        payload = self.responses[stage]
        if isinstance(payload, Exception):
            raise payload
        if callable(payload):  # lets a test vary the reply per call, e.g. per batch
            payload = payload(prompt)
        return parse_model(payload, output_model, context)

    def prompt_for(self, stage: str) -> str:
        return next(r["prompt"] for r in self.requests if r["stage"] == stage)


def fake_message(payload, stop_reason="end_turn", input_tokens=100, output_tokens=50):
    """Mimic the shape of an anthropic Message object."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        content=[SimpleNamespace(type="text", text=text)],
    )


class StubMessages:
    """Replaces `anthropic.Anthropic().messages`. Returns queued replies in order."""

    def __init__(self, replies: list):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
