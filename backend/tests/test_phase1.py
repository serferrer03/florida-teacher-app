import asyncio
import os
from dataclasses import replace

import pytest

from app.config import get_settings
from app.crypto import CredentialCipher
from app.db import Database
from app.moodle.client import Credentials, MoodleClient, MoodleLoginError

from .fake_moodle import PASSWORD, USER, FakeMoodle, serve


@pytest.fixture(scope="module")
def fake():
    fake = FakeMoodle()
    url, server = serve(fake)
    fake.url = url
    yield fake
    server.should_exit = True


@pytest.fixture
def client(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = replace(get_settings(), moodle_base_url=fake.url, timeout_ms=10000)
    fake.ajax_enabled = True
    return MoodleClient(settings)


def run(coro):
    return asyncio.run(coro)


def test_cipher_roundtrip(tmp_path):
    c = CredentialCipher(tmp_path / "k")
    token = c.encrypt("contraseña")
    assert b"contrase" not in token
    assert CredentialCipher(tmp_path / "k").decrypt(token) == "contraseña"
    assert oct((tmp_path / "k").stat().st_mode)[-3:] == "600"


def test_db_courses(tmp_path):
    db = Database(tmp_path / "a.db")
    db.replace_courses([{"id": 1, "fullname": "B", "shortname": None, "category": None, "url": "u"},
                        {"id": 2, "fullname": "a", "shortname": None, "category": None, "url": "u"}])
    assert [c["fullname"] for c in db.list_courses()] == ["a", "B"]
    assert db.get_meta("courses_synced_at")


def test_login_ok_and_session_reuse(client, fake):
    creds = Credentials(USER, PASSWORD)
    before = fake.logins
    assert run(client.check_login(creds))["ok"]
    assert client.settings.storage_state_path.exists()
    courses = run(client.list_courses(creds))
    assert fake.logins == before + 1  # reutiliza la sesión guardada
    assert [c["id"] for c in courses] == [7, 3]
    assert courses[0]["category"] == "DAM"


def test_login_wrong_password(client):
    with pytest.raises(MoodleLoginError, match="erróneos"):
        run(client.check_login(Credentials(USER, "mal")))


def test_dom_fallback(client, fake):
    fake.ajax_enabled = False
    courses = run(client.list_courses(Credentials(USER, PASSWORD)))
    assert {c["id"]: c["fullname"] for c in courses} == {3: "Bases de datos", 7: "Programación DAM 1"}
