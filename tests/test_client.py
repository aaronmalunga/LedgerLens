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
