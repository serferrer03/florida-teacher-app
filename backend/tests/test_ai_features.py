from app import ai

from .test_api import api, h, wait_state  # noqa: F401
from .test_phase2 import login


def test_settings_keys_encrypted_and_hidden(api, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = api.get("/api/settings", headers=h(api)).json()
    assert s["ai_active"] is None and not s["gemini_api_key"]["configured"]
    r = api.put("/api/settings", headers=h(api), json={"gemini_api_key": "AIzaSECRETO1234", "ai_provider": "auto"})
    assert r.status_code == 200
    s = r.json()
    assert s["ai_active"] == "gemini" and s["ai_model_active"] == ai.GEMINI_DEFAULT
    assert s["gemini_api_key"] == {"configured": True, "hint": "…1234"} and "SECRETO" not in r.text
    assert b"AIzaSECRETO" not in (tmp_path / "app.db").read_bytes()   # cifrada en la BD
    api.put("/api/settings", headers=h(api), json={"anthropic_api_key": "sk-ant-xxxxABCD"})
    assert api.get("/api/settings", headers=h(api)).json()["ai_active"] == "claude"   # auto: Claude primero
    api.put("/api/settings", headers=h(api), json={"ai_provider": "gemini"})
    assert api.get("/api/settings", headers=h(api)).json()["ai_active"] == "gemini"
    api.put("/api/settings", headers=h(api), json={"gemini_api_key": "", "anthropic_api_key": ""})
    assert api.get("/api/settings", headers=h(api)).json()["ai_active"] is None
    bad = api.put("/api/settings", headers=h(api), json={"sheets_url": "https://evil.example/x"})
    assert bad.status_code == 422


def test_ai_features_endpoints(api, monkeypatch):
    login(api)
    calls = []

    async def fake_json(system, parts, schema, max_tokens=16000):
        calls.append(parts[0]["text"])
        if "name" in schema["properties"]:
            return {"name": "Práctica bucles", "description": "Enunciado", "criteria": "Funciona (10 p)",
                    "grade_max": 10, "online_text": False, "file_submissions": False, "max_files": 50,
                    "due_in_days": 4, "due_time": "23:55"}
        if "criteria" in schema["properties"]:
            return {"criteria": "Correcto 5 p; claro 5 p"}
        return {"text": "Buen trabajo; revisa los casos límite."}

    monkeypatch.setattr(ai, "generate_json", fake_json)
    d = api.post("/api/ai/draft-assignment", headers=h(api), json={"course_id": 7, "prompt": "práctica de bucles para el viernes"}).json()
    assert d["name"] == "Práctica bucles" and d["file_submissions"] and d["max_files"] == 20
    assert "Programación DAM 1" in calls[0]
    assert api.post("/api/ai/rubric", headers=h(api), json={"name": "P1"}).json()["criteria"].startswith("Correcto")
    assert "casos" in api.post("/api/ai/improve-feedback", headers=h(api), json={"text": "mal hecho", "grade": "4"}).json()["text"]


def test_ai_not_configured_and_pairing(api, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = api.post("/api/ai/rubric", headers=h(api), json={"name": "P1"})
    assert r.status_code == 409 and "Ajustes" in r.json()["detail"]
    t = api.post("/api/settings/test-ai", headers=h(api)).json()
    assert t["ok"] is False
    p = api.get("/api/pairing", headers=h(api)).json()
    assert p["code"] == api.token and p["http_url"].startswith("http://") and p["https_url"] is None
    assert api.post("/api/settings/test-sheets", headers=h(api)).json()["ok"] is False
