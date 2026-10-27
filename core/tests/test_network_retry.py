"""A dropped connection is tried again, like a timeout (2026-10-27: xAI's "Remote end closed connection without
response" failed a whole reading instead of being retried). No network: `urlopen` is replaced."""

import http.client
import io
import json

import pytest

from maindscout.intelligence import exa, llm, research


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def drops_once(payload: dict):
    calls: list = []

    def urlopen(request, timeout=None):
        calls.append(request)
        if len(calls) == 1:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return Answer(json.dumps(payload).encode())

    return urlopen, calls


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)


def test_the_model_client_tries_again_when_the_connection_drops(monkeypatch):
    urlopen, calls = drops_once({"choices": [{"message": {"content": json.dumps({"ok": True})}}], "usage": {}})
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    result = llm.XaiClient(api_key="test-key").complete_json("system", "user", {"type": "object"}, "check")
    assert result.data == {"ok": True}
    assert len(calls) == 2


def test_the_research_client_tries_again_when_the_connection_drops(monkeypatch):
    answer = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"ok": True})}]}]}
    urlopen, calls = drops_once(answer)
    monkeypatch.setattr(research.urllib.request, "urlopen", urlopen)
    data, _, _ = research.XaiSearchClient(api_key="test-key").search_json("system", "user", {"type": "object"}, "check")
    assert data == {"ok": True}
    assert len(calls) == 2


def test_the_exa_client_tries_again_when_the_connection_drops(monkeypatch):
    urlopen, calls = drops_once({"results": []})
    monkeypatch.setattr(exa.urllib.request, "urlopen", urlopen)
    assert exa.ExaClient(key="test-key").call({"query": "x"}) == {"results": []}
    assert len(calls) == 2
