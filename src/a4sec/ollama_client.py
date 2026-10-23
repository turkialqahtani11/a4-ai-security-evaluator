"""Minimal synchronous client for the local Ollama HTTP API.

Only three endpoints are used: ``/api/version``, ``/api/tags`` and ``/api/chat``.
``trust_env=False`` keeps requests off any system HTTP proxy, so traffic stays
on the local machine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from a4sec.utils import DEFAULT_OLLAMA_URL


class OllamaError(Exception):
    """Base error. ``retryable`` tells the runner whether another try makes sense."""

    retryable: bool = False


class OllamaConnectionError(OllamaError):
    """Ollama is not reachable (not started, wrong port, etc.)."""

    retryable = True


class OllamaTimeoutError(OllamaError):
    """The request exceeded the configured timeout."""

    retryable = True


class OllamaHTTPError(OllamaError):
    """Ollama answered with a non-2xx status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.retryable = status >= 500 or status == 429


class OllamaModelNotFoundError(OllamaHTTPError):
    """The requested model tag is not installed locally."""


class OllamaResponseError(OllamaError):
    """Ollama returned something that is not a valid chat response."""


@dataclass
class ChatResult:
    """A successful chat completion."""

    text: str
    latency_ms: int
    model: str
    stats: dict[str, Any] = field(default_factory=dict)


def model_available(requested: str, installed: list[str]) -> bool:
    """Match ``llama3.2`` against ``llama3.2:latest`` and exact tags alike."""
    wanted = requested if ":" in requested else f"{requested}:latest"
    return requested in installed or wanted in installed


class OllamaClient:
    """Thin wrapper around ``httpx.Client`` with clear, typed errors."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            transport=transport,
            trust_env=False,
        )

    # -- context manager ---------------------------------------------------- #
    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    # -- low level ---------------------------------------------------------- #
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"request to {self.base_url}{path} timed out after {self.timeout:g}s"
            ) from exc
        except httpx.TransportError as exc:
            raise OllamaConnectionError(
                f"cannot reach Ollama at {self.base_url} ({exc.__class__.__name__}). "
                "Start it with `ollama serve` or check the endpoint."
            ) from exc

        if response.status_code >= 400:
            message = _error_message(response)
            if response.status_code == 404 and "not found" in message.lower():
                raise OllamaModelNotFoundError(response.status_code, message)
            raise OllamaHTTPError(response.status_code, message)
        try:
            return response.json()
        except ValueError as exc:
            raise OllamaResponseError(f"non-JSON response from {path}") from exc

    # -- API ---------------------------------------------------------------- #
    def version(self) -> str:
        """Return the Ollama server version string."""
        data = self._request("GET", "/api/version")
        return str(data.get("version", "unknown"))

    def list_models(self) -> list[str]:
        """Return the locally installed model tags."""
        data = self._request("GET", "/api/tags")
        return sorted(m.get("name") or m.get("model", "") for m in data.get("models", []))

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        seed: int | None = None,
    ) -> ChatResult:
        """Send one non-streaming chat request and measure wall-clock latency."""
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if seed is not None:
            options["seed"] = seed
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if options:
            payload["options"] = options

        started = time.perf_counter()
        data = self._request("POST", "/api/chat", json=payload)
        latency_ms = int(round((time.perf_counter() - started) * 1000))

        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict) or "content" not in message:
            raise OllamaResponseError("chat response has no message.content")
        stats = {
            k: data[k]
            for k in ("total_duration", "load_duration", "prompt_eval_count", "eval_count", "done_reason")
            if k in data
        }
        return ChatResult(
            text=str(message.get("content") or ""),
            latency_ms=latency_ms,
            model=str(data.get("model", model)),
            stats=stats,
        )


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])
    except ValueError:
        pass
    return response.text[:200] or response.reason_phrase
