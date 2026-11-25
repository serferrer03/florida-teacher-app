import asyncio
import json
from types import SimpleNamespace

from app import ai

SCHEMA = {"type": "object", "properties": {"ok": {"type": "string"}}, "required": ["ok"], "additionalProperties": False}
PARTS = [{"kind": "pdf", "data": b"%PDF", "title": "archivo_1.pdf"}, {"kind": "image", "mime": "image/png", "data": b"\x89PNG"},
         {"kind": "text", "text": "hola"}]


def test_claude_adapter(monkeypatch):
    import anthropic
    seen = {}

    class FakeMessages:
        async def create(self, **kw):
            seen.update(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"ok": "sí"}')])

    class FakeClient:
        def __init__(self, api_key=None):
            seen["key"] = api_key
            self.beta = SimpleNamespace(messages=FakeMessages())

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert asyncio.run(ai.generate_json("sys", PARTS, SCHEMA)) == {"ok": "sí"}
    assert seen["model"] == "claude-opus-5-5" and seen["key"] == "sk-ant-test"
    assert seen["output_config"]["format"]["schema"] == SCHEMA and seen["fallbacks"] == "default"
    types_ = [b["type"] for b in seen["messages"][0]["content"]]
    assert types_ == ["document", "image", "text"]


def test_gemini_adapter(monkeypatch):
    from google import genai
    seen = {}

    class FakeModels:
        async def generate_content(self, model, contents, config):
            seen.update(model=model, contents=contents, config=config)
            return SimpleNamespace(text=json.dumps({"ok": "sí"}))

    class FakeClient:
        def __init__(self, api_key=None):
            seen["key"] = api_key
            self.aio = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    assert asyncio.run(ai.generate_json("sys", PARTS, SCHEMA)) == {"ok": "sí"}
    assert seen["model"] == ai.GEMINI_DEFAULT and seen["key"] == "AIza-test"
    assert seen["config"].response_mime_type == "application/json" and seen["config"].response_json_schema == SCHEMA
    assert seen["config"].system_instruction == "sys" and len(seen["contents"]) == 3
    assert seen["contents"][0].inline_data.mime_type == "application/pdf"
