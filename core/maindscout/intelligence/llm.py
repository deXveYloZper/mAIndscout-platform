"""Model access. Pure network client: no database. One interface, a real xAI client, a test fake."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

XAI_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4.20-0309-non-reasoning"
TICKS_PER_USD = 10_000_000_000  # xAI reports cost in 1e-10 USD


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    usd: float


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str) -> LLMResult: ...


def load_env_key(name: str = "XAI_API_KEY") -> str | None:
    """Read from the environment, else from core/.env (never committed)."""
    from maindscout.settings import env

    return env(name)


class XaiClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL, timeout: float = 120, retries: int = 3):
        self.api_key = api_key or load_env_key()
        if not self.api_key:
            raise LLMError("XAI_API_KEY is not set")
        self.model, self.timeout, self.retries = model, timeout, retries

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str) -> LLMResult:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
            }
        ).encode()
        request = urllib.request.Request(
            XAI_URL, body, {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        )
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                break
            except urllib.error.HTTPError as error:
                last = error
                if error.code not in (429, 500, 502, 503, 504):
                    raise LLMError(f"xAI returned HTTP {error.code}") from error
            except (urllib.error.URLError, TimeoutError) as error:
                last = error
            time.sleep(2**attempt)
        else:
            raise LLMError(f"xAI request failed after {self.retries} attempts: {last}")
        try:
            data = json.loads(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, json.JSONDecodeError) as error:
            raise LLMError("xAI returned unreadable output") from error
        usage = payload.get("usage", {})
        return LLMResult(
            data=data,
            model=payload.get("model", self.model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            usd=usage.get("cost_in_usd_ticks", 0) / TICKS_PER_USD,
        )


class FakeClient:
    """Returns a canned response. For tests."""

    def __init__(self, data: dict[str, Any], model: str = "fake-model"):
        self.data, self.model, self.calls = data, model, []

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str) -> LLMResult:
        self.calls.append({"system": system, "user": user, "name": name})
        return LLMResult(data=self.data, model=self.model, input_tokens=0, output_tokens=0, usd=0.0)
