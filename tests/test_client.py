"""MetaModelClient request shape, tested against a stub (no network)."""
import json
import sys
import types

from ledgerlens.core.models import SourceType
from ledgerlens.llm.client import MetaModelClient


class _Resp:
    class _Msg:
        content = json.dumps({"date": "2026-02-03", "direction": "in", "amount": "150.00", "currency": "ZMW",
                              "source_type": "sms", "txn_id": "MP1"})
    class _Choice:
        pass
    usage = types.SimpleNamespace(prompt_tokens=400, completion_tokens=60)

    def __init__(self):
        c = self._Choice()
        c.message = self._Msg()
        self.choices = [c]


def _stub(monkeypatch, captured):
    class Completions:
        def create(self, **kw):
            captured.update(kw)
            return _Resp()

    class OpenAI:
        def __init__(self, **kw):
            captured["client_kwargs"] = kw
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))


def test_uses_json_schema_response_format_and_records_usage(monkeypatch):
    cap = {}
    _stub(monkeypatch, cap)
    monkeypatch.setenv("LEDGERLENS_VISION_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("MODEL_API_KEY", "k")  # Meta's documented name
    monkeypatch.delenv("META_API_KEY", raising=False)
    c = MetaModelClient()
    tx = c.extract(media=None, mime=None, text="MTN: received K150", source_hint=SourceType.SMS)
    rf = cap["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["name"] == "Transaction"
    assert "properties" in rf["json_schema"]["schema"]
    assert cap["client_kwargs"]["api_key"] == "k" and cap["temperature"] == 0
    assert str(tx.amount) == "150.00" and c.last_usage == (400, 60)


def test_reasoning_effort_goes_in_extra_body_and_is_validated(monkeypatch):
    import pytest
    cap = {}
    _stub(monkeypatch, cap)
    monkeypatch.setenv("LEDGERLENS_VISION_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.setenv("LEDGERLENS_REASONING_EFFORT", "low")
    c = MetaModelClient()
    c.extract(media=None, mime=None, text="x", source_hint=SourceType.SMS)
    assert cap["extra_body"] == {"reasoning_effort": "low"}
    monkeypatch.setenv("LEDGERLENS_REASONING_EFFORT", "none")  # the API answers 400 to "none"
    with pytest.raises(ValueError):
        MetaModelClient()


def test_no_effort_means_no_extra_body(monkeypatch):
    cap = {}
    _stub(monkeypatch, cap)
    monkeypatch.setenv("LEDGERLENS_VISION_MODEL", "muse-spark-1.3")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.delenv("LEDGERLENS_REASONING_EFFORT", raising=False)
    MetaModelClient().extract(media=None, mime=None, text="x", source_hint=SourceType.SMS)
    assert "extra_body" not in cap
