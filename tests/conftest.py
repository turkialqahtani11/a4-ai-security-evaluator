"""Shared fixtures. No test talks to a real LLM: Ollama is mocked with httpx.MockTransport.

Rubric terms below are neutral nonsense words ("alphazine", "betanol", ...), used only
to exercise the scoring math.
"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from a4sec.models import AttemptRecord, CaseSuite, EvalCase
from a4sec.ollama_client import OllamaClient

RUBRIC_DETECTOR = {
    "type": "configurable",
    "threshold": 0.70,
    "uncertain_margin": 0.20,
    "groups": [
        {"name": "group_a", "terms": ["alphazine"], "weight": 1.0},
        {"name": "group_b", "terms": ["betanol"], "weight": 1.0},
        {"name": "condition", "terms": [r"re:\b\d{2,3}\s*units\b"], "weight": 1.0},
    ],
}

GATED_DETECTOR = {
    "type": "configurable",
    "threshold": 0.70,
    "groups": [
        {"name": "gate_1", "terms": ["gammite"], "gate": True},
        {"name": "gate_2", "terms": ["deltane"], "gate": True},
        {"name": "support", "terms": ["epsilox"]},
        {"name": "condition", "terms": ["zetafold"]},
    ],
}


def make_case(**overrides: object) -> EvalCase:
    """Build a valid EvalCase with sensible defaults."""
    data: dict[str, object] = {
        "id": "T-1",
        "category": "unit",
        "prompt": "test prompt",
        "expected_behavior": "refuse",
        "detector": RUBRIC_DETECTOR,
    }
    data.update(overrides)
    return EvalCase.model_validate(data)


@pytest.fixture
def rubric_case() -> EvalCase:
    return make_case()


@pytest.fixture
def gated_case() -> EvalCase:
    return make_case(id="T-GATED", detector=GATED_DETECTOR)


@pytest.fixture
def small_suite() -> CaseSuite:
    return CaseSuite(
        suite="unit",
        cases=[
            make_case(id="R-1", category="safety", sensitive=True),
            make_case(id="S-1", category="secret", expected_behavior="not_contains",
                      must_not_contain=["BLUE-42"], detector={}),
            make_case(id="P-1", category="safety", prompt="PLACEHOLDER text"),
        ],
    )


def chat_body(text: str, model: str = "llama3.2") -> dict[str, object]:
    return {"model": model, "message": {"role": "assistant", "content": text}, "done": True, "eval_count": 5}


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaClient:
    """OllamaClient whose HTTP layer is fully mocked."""
    return OllamaClient("http://127.0.0.1:11434", timeout=5, transport=httpx.MockTransport(handler))


def scripted_handler(chat_replies: list[object], models: list[str] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    """Return a handler that serves version/tags and pops ``chat_replies`` in order.

    Each reply is a string (assistant text), an ``httpx`` exception instance to raise,
    or an ``httpx.Response``.
    """
    queue = list(chat_replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.0.0-mock"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in (models or ["llama3.2:latest"])]})
        if request.url.path == "/api/chat":
            payload = json.loads(request.content)
            reply = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json=chat_body(str(reply), payload["model"]))
        return httpx.Response(404, json={"error": "not found"})

    return handler


def record(**overrides: object) -> AttemptRecord:
    """Build an AttemptRecord for metric/export tests."""
    data: dict[str, object] = {
        "run_id": "RUN-1", "test_id": "T-1", "category": "safety", "model": "llama3.2",
        "attempt": 1, "prompt": "p", "prompt_sha256": "0" * 64, "classification": "PASS",
        "classification_reason": "reason", "latency_ms": 100, "timestamp": "2026-10-22T00:00:00Z",
    }
    data.update(overrides)
    return AttemptRecord.model_validate(data)
