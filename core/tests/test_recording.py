"""Record model answers once, replay them for free (intelligence/recording.py)."""

import pytest

from maindscout.intelligence import recording
from maindscout.intelligence.llm import LLMResult


class Counting:
    model = "real-model"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema, name):
        self.calls += 1
        return LLMResult({"answer": user.upper()}, self.model, 10, 5, 0.002)

    def search_json(self, system, user, schema, name):
        self.calls += 1
        return {"facts": user}, ["https://example.com/a"], {"usd": 0.01, "sources": 1}


SCHEMA = {"type": "object"}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_RECORDINGS", str(tmp_path))
    return tmp_path


def test_auto_records_once_and_then_answers_for_free(folder, monkeypatch):
    monkeypatch.setenv("LLM_REPLAY", "auto")
    real = Counting()
    client = recording.wrap_chat(lambda: real)
    first = client.complete_json("sys", "hello", SCHEMA, "cv_extraction")
    again = recording.wrap_chat(lambda: real).complete_json("sys", "hello", SCHEMA, "cv_extraction")
    assert real.calls == 1 and again.data == first.data == {"answer": "HELLO"}
    assert (again.input_tokens, again.output_tokens, again.usd) == (10, 5, 0.002), "the ledger looks as when recorded"
    assert len(list((folder / "chat" / "cv_extraction").glob("*.json"))) == 1


def test_replay_never_calls_the_model_and_fails_loudly_on_a_new_request(folder, monkeypatch):
    monkeypatch.setenv("LLM_REPLAY", "auto")
    real = Counting()
    recording.wrap_chat(lambda: real).complete_json("sys", "hello", SCHEMA, "cv_extraction")
    monkeypatch.setenv("LLM_REPLAY", "replay")

    def no_model():
        raise AssertionError("replay must not build a real client")

    client = recording.wrap_chat(no_model)
    assert client.complete_json("sys", "hello", SCHEMA, "cv_extraction").data == {"answer": "HELLO"}
    with pytest.raises(recording.NotRecorded) as missing:
        client.complete_json("sys", "hello, changed", SCHEMA, "cv_extraction")
    assert missing.value.permanent and "LLM_REPLAY=auto" in str(missing.value)


def test_a_changed_prompt_or_schema_is_a_new_request():
    a = recording.request_key("chat", "m", "sys", "text", SCHEMA, "n")
    assert a != recording.request_key("chat", "m", "sys v2", "text", SCHEMA, "n")
    assert a != recording.request_key("chat", "m", "sys", "text", {"type": "array"}, "n")
    assert a != recording.request_key("chat", "other-model", "sys", "text", SCHEMA, "n")
    assert a == recording.request_key("chat", "m", "sys", "text", SCHEMA, "n")


def test_web_search_is_recorded_too(folder, monkeypatch):
    monkeypatch.setenv("LLM_REPLAY", "auto")
    real = Counting()
    first = recording.wrap_search(lambda: real).search_json("sys", "Acme", SCHEMA, "company_facts")
    again = recording.wrap_search(lambda: real).search_json("sys", "Acme", SCHEMA, "company_facts")
    assert real.calls == 1 and first == again == ({"facts": "Acme"}, ["https://example.com/a"], {"usd": 0.01, "sources": 1})


def test_record_mode_always_calls_and_overwrites(folder, monkeypatch):
    monkeypatch.setenv("LLM_REPLAY", "record")
    real = Counting()
    client = recording.wrap_chat(lambda: real)
    client.complete_json("sys", "hello", SCHEMA, "n")
    client.complete_json("sys", "hello", SCHEMA, "n")
    assert real.calls == 2


def test_off_is_the_real_client_and_a_bad_mode_is_refused(monkeypatch):
    monkeypatch.setenv("LLM_REPLAY", "off")
    real = Counting()
    assert recording.wrap_chat(lambda: real) is real
    monkeypatch.setenv("LLM_REPLAY", "sometimes")
    with pytest.raises(recording.LLMError):
        recording.wrap_chat(lambda: real)
