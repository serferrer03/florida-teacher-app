import importlib
import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

from .fake_moodle import MFA_CODE, PASSWORD, USER


@pytest.fixture
def api(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MOODLE_BASE_URL", fake.url)
    monkeypatch.setenv("APP_ACCESS_TOKEN", "")
    monkeypatch.setenv("LOGIN_TIMEOUT_S", "30")
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "nodist"))
    get_settings.cache_clear()
    import app.main as main
    main = importlib.reload(main)
    fake.reset(mfa="code")
    with TestClient(main.app) as c:
        c.token = (tmp_path / "access_code").read_text()
        c.main = main
        yield c


def h(c):
    return {"X-App-Token": c.token}


def wait_state(c, wanted, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        s = c.get("/api/login/status", headers=h(c)).json()
        if s["state"] in wanted:
            return s
        time.sleep(0.2)
    raise AssertionError(f"estado final no alcanzado: {s}")


def test_access_code_required_and_lockout(api):
    assert api.get("/api/health").status_code == 200
    assert len(api.token) == 10
    for _ in range(8):  # sin código (tablet sin vincular) no cuenta para el bloqueo
        assert api.get("/api/status").status_code == 401
    assert api.get("/api/status", headers=h(api)).status_code == 200
    for _ in range(5):
        assert api.get("/api/status", headers={"X-App-Token": "mal"}).status_code == 401
    assert api.get("/api/status", headers=h(api)).status_code == 429  # bloqueado tras 5 fallos


def test_security_headers(api):
    r = api.get("/api/status", headers=h(api))
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-frame-options"] == "DENY"
    assert "access-control-allow-origin" not in r.headers


def test_full_login_with_mfa_code_privacy_and_wipe(api, tmp_path):
    r = api.post("/api/login/start", headers=h(api),
                 json={"username": USER, "password": PASSWORD, "remember_password": False})
    assert r.status_code == 200
    s = wait_state(api, {"mfa_code", "error"})
    assert s["state"] == "mfa_code", s
    api.post("/api/login/code", headers=h(api), json={"code": MFA_CODE})
    s = wait_state(api, {"success", "error"})
    assert s["state"] == "success", s

    st = api.get("/api/status", headers=h(api)).json()
    assert st["username"] == USER and not st["password_remembered"] and st["has_session"]
    assert len(api.get("/api/courses", headers=h(api)).json()["courses"]) == 2

    # La contraseña no se guardó y no aparece en ningún archivo
    for f in tmp_path.iterdir():
        if f.is_file():
            assert PASSWORD.encode() not in f.read_bytes(), f

    items = api.get("/api/privacy", headers=h(api)).json()["items"]
    assert {i["what"]: i["stored"] for i in items}["Contraseña"] is False

    # Sincronizar reutiliza la sesión cifrada
    assert api.post("/api/courses/sync", headers=h(api)).status_code == 200

    old_key = (tmp_path / "secret.key").read_bytes()
    assert api.delete("/api/data", headers=h(api)).json()["deleted"]
    st = api.get("/api/status", headers=h(api)).json()
    assert not st["has_account"] and not st["has_session"]
    assert api.get("/api/courses", headers=h(api)).json()["courses"] == []
    assert (tmp_path / "secret.key").read_bytes() != old_key
    # Sin sesión ni contraseña -> 409 (hay que volver a conectar)
    assert api.post("/api/courses/sync", headers=h(api)).status_code == 409


def test_remember_password_is_encrypted(api, tmp_path):
    api.post("/api/login/start", headers=h(api),
             json={"username": USER, "password": PASSWORD, "remember_password": True})
    wait_state(api, {"mfa_code", "error"})
    api.post("/api/login/code", headers=h(api), json={"code": MFA_CODE})
    assert wait_state(api, {"success", "error"})["state"] == "success"
    assert api.get("/api/status", headers=h(api)).json()["password_remembered"]
    for f in tmp_path.iterdir():
        if f.is_file():
            assert PASSWORD.encode() not in f.read_bytes(), f
    api.post("/api/logout", headers=h(api))
    st = api.get("/api/status", headers=h(api)).json()
    assert not st["password_remembered"] and not st["has_session"] and st["username"] == USER
