import asyncio
import json
from dataclasses import replace

import pytest

from app.config import get_settings
from app.crypto import CredentialCipher
from app.db import Database
from app.moodle.client import Credentials, MoodleAuthRequired, MoodleClient, MoodleLoginError
from app.session_store import SessionStore

from .fake_moodle import MFA_CODE, MFA_NUMBER, PASSWORD, USER


class RecordingUI:
    def __init__(self, fake=None, code=MFA_CODE):
        self.states, self.fake, self.code = [], fake, code

    async def update(self, state, **info):
        self.states.append((state, info.get("number")))
        if state == "mfa_number" and self.fake:
            self.fake.mfa_approved = True  # el profesor aprueba en su móvil

    async def request_code(self):
        self.states.append(("mfa_code", None))
        return self.code


@pytest.fixture
def client(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = replace(get_settings(), moodle_base_url=fake.url, login_timeout_s=30)
    fake.reset()
    store = SessionStore(settings.session_path, CredentialCipher(settings.key_path), settings.session_max_days)
    c = MoodleClient(settings, store)
    yield c
    run(c.close())


LOOP = asyncio.new_event_loop()  # un solo bucle: el navegador sigue abierto entre llamadas


def run(coro):
    return LOOP.run_until_complete(coro)


def test_cipher_roundtrip_and_reset(tmp_path):
    c = CredentialCipher(tmp_path / "k")
    token = c.encrypt("contraseña")
    assert b"contrase" not in token
    assert CredentialCipher(tmp_path / "k").decrypt(token) == "contraseña"
    assert oct((tmp_path / "k").stat().st_mode)[-3:] == "600"
    c.reset()
    with pytest.raises(ValueError):
        c.decrypt(token)


def test_session_store_encrypted_and_expires(tmp_path):
    import os
    store = SessionStore(tmp_path / "s.enc", CredentialCipher(tmp_path / "k"), max_days=1)
    store.save({"cookies": [{"name": "MoodleSession", "value": "SECRETO"}]})
    assert b"SECRETO" not in (tmp_path / "s.enc").read_bytes()
    assert store.load()["cookies"][0]["value"] == "SECRETO"
    os.utime(tmp_path / "s.enc", (0, 0))
    assert store.load() is None and not store.exists()


def test_db_migration_and_wipe(tmp_path):
    import sqlite3
    path = tmp_path / "a.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE credentials (id INTEGER PRIMARY KEY CHECK (id = 1), username TEXT NOT NULL, "
                 "password_enc BLOB NOT NULL, updated_at TEXT NOT NULL)")
    conn.execute("INSERT INTO credentials VALUES (1, 'u', x'00', 't')")
    conn.commit(); conn.close()
    db = Database(path)
    assert db.get_credentials()["username"] == "u"
    db.save_credentials("u", None)
    assert db.get_credentials()["password_enc"] is None
    db.replace_courses([{"id": 1, "fullname": "B", "shortname": None, "category": None, "url": "u"},
                        {"id": 2, "fullname": "a", "shortname": None, "category": None, "url": "u"}])
    assert [c["fullname"] for c in db.list_courses()] == ["a", "B"]
    db.wipe()
    assert db.get_credentials() is None and db.count_courses() == 0


def test_microsoft_login_without_mfa_and_session_reuse(client, fake):
    creds = Credentials(USER, PASSWORD)
    before = fake.logins
    assert run(client.interactive_login(creds, RecordingUI(), fresh=True))["ok"]
    assert fake.kmsi_answer == "yes"
    raw = client.settings.session_path.read_bytes()
    assert b"MoodleSession" not in raw  # cookies cifradas
    courses = run(client.list_courses(Credentials(USER, None)))
    assert fake.logins == before + 1  # reutiliza la sesión, sin pedir contraseña
    assert [c["id"] for c in courses] == [7, 3]


def test_microsoft_mfa_number(client, fake):
    fake.reset(mfa="number")
    ui = RecordingUI(fake)
    assert run(client.interactive_login(Credentials(USER, PASSWORD), ui, fresh=True))["ok"]
    assert ("mfa_number", MFA_NUMBER) in ui.states


def test_microsoft_mfa_code(client, fake):
    fake.reset(mfa="code")
    ui = RecordingUI()
    assert run(client.interactive_login(Credentials(USER, PASSWORD), ui, fresh=True))["ok"]
    assert ("mfa_code", None) in ui.states


def test_microsoft_wrong_code(client, fake):
    fake.reset(mfa="code")
    with pytest.raises(MoodleLoginError, match="código no válido"):
        run(client.interactive_login(Credentials(USER, PASSWORD), RecordingUI(code="000000"), fresh=True))


def test_microsoft_wrong_password(client):
    with pytest.raises(MoodleLoginError, match="contraseña"):
        run(client.interactive_login(Credentials(USER, "mal"), RecordingUI(), fresh=True))


def test_microsoft_unknown_user(client):
    with pytest.raises(MoodleLoginError, match="cuenta"):
        run(client.interactive_login(Credentials("otro@x", PASSWORD), RecordingUI(), fresh=True))


def test_background_relogin_stops_at_mfa(client, fake):
    fake.reset(mfa="number")
    with pytest.raises(MoodleAuthRequired):
        run(client.list_courses(Credentials(USER, PASSWORD)))


def test_no_session_no_password_requires_login(client):
    with pytest.raises(MoodleAuthRequired):
        run(client.list_courses(Credentials(USER, None)))


def test_moodle_local_form_and_dom_fallback(client, fake):
    fake.reset(mode="moodle")
    client.settings = replace(client.settings, login_mode="moodle")
    with pytest.raises(MoodleLoginError, match="erróneos"):
        run(client.interactive_login(Credentials(USER, "mal"), RecordingUI(), fresh=True))
    fake.ajax_enabled = False
    courses = run(client.list_courses(Credentials(USER, PASSWORD)))  # login silencioso sin MFA
    assert {c["id"]: c["fullname"] for c in courses} == {3: "Bases de datos", 7: "Programación DAM 1"}


def test_empty_ajax_falls_back_to_page(client, fake):
    fake.ajax_empty = True
    run(client.interactive_login(Credentials(USER, PASSWORD), RecordingUI(), fresh=True))
    courses = run(client.list_courses(Credentials(USER, None)))
    assert {c["id"] for c in courses} == {3, 7}


def test_restart_restores_encrypted_session(client, fake):
    run(client.interactive_login(Credentials(USER, PASSWORD), RecordingUI(), fresh=True))
    before = fake.logins
    run(client.forget())  # como si se reiniciara el servidor
    assert len(run(client.list_courses(Credentials(USER, None)))) == 2
    assert fake.logins == before


def test_microsoft_email_glitch_is_retried(client, fake):
    fake.email_glitches = 1
    assert run(client.interactive_login(Credentials(USER, PASSWORD), RecordingUI(), fresh=True))["ok"]
