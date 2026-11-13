import json
import ssl
import time

from cryptography import x509

from app import crypto
from app.tls import ensure_certs

from .test_api import api, h, wait_state  # noqa: F401


def test_tls_certs_constrained_and_renewed_on_ip_change(tmp_path):
    crt, key, ca = ensure_certs(tmp_path, "192.168.1.50")
    ca_cert = x509.load_pem_x509_certificate(ca.read_bytes())
    nc = ca_cert.extensions.get_extension_for_class(x509.NameConstraints)
    assert nc.critical and x509.DNSName("localhost") in nc.value.permitted_subtrees
    srv = x509.load_pem_x509_certificate(crt.read_bytes())
    ips = [str(i) for i in srv.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
           .get_values_for_type(x509.IPAddress)]
    assert "192.168.1.50" in ips
    assert oct((tmp_path / "tls" / "ca.key").stat().st_mode)[-3:] == "600"
    # el servidor valida contra la CA (cadena correcta)
    ctx = ssl.create_default_context(cafile=str(ca))
    ctx.load_cert_chain(str(crt), str(key))
    before = crt.read_bytes()
    assert ensure_certs(tmp_path, "192.168.1.50")[0].read_bytes() == before      # misma IP: se reutiliza
    assert ensure_certs(tmp_path, "192.168.1.77")[0].read_bytes() != before      # IP nueva: se renueva
    assert x509.load_pem_x509_certificate(ca.read_bytes()).serial_number == ca_cert.serial_number


class MemoryKeyring:
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, s, a):
        return self.store.get((s, a))

    def set_password(self, s, a, v):
        self.store[(s, a)] = v

    def delete_password(self, s, a):
        self.store.pop((s, a), None)


def test_key_migrates_to_keyring(tmp_path, monkeypatch):
    old = crypto.CredentialCipher(tmp_path / "secret.key")
    token = old.encrypt("x")
    kr = MemoryKeyring()
    monkeypatch.setattr(crypto, "_system_keyring", lambda: kr)
    c = crypto.CredentialCipher(tmp_path / "secret.key", use_keyring=True)
    assert c.decrypt(token) == "x" and not (tmp_path / "secret.key").exists() and len(kr.store) == 1
    assert "Llavero" in c.storage
    c.reset()
    assert not (tmp_path / "secret.key").exists() and len(kr.store) == 1  # clave nueva, en el llavero


def test_rotate_code_backup_and_connection(api):
    old = api.token
    r = api.post("/api/access/rotate", headers=h(api))
    assert r.status_code == 200
    assert api.get("/api/status", headers=h(api)).status_code == 401   # el código viejo ya no vale
    api.token = r.json()["code"]
    assert api.token != old and api.get("/api/status", headers=h(api)).status_code == 200

    api.post("/api/templates", headers=h(api), json={"name": "P1", "data": {"a": 1}})
    backup = api.get("/api/backup", headers=h(api))
    data = backup.json()
    assert data["templates"] == [{"name": "P1", "data": {"a": 1}}]
    for secret in ("password", "cookie", "access_code", api.token):
        assert secret not in backup.text
    api.delete(f"/api/templates/{api.get('/api/templates', headers=h(api)).json()['templates'][0]['id']}",
               headers=h(api))
    assert api.post("/api/backup", headers=h(api), json=data).json() == {"templates_added": 1}
    assert api.post("/api/backup", headers=h(api), json=data).json() == {"templates_added": 0}

    conn = api.get("/api/connection", headers=h(api)).json()
    assert conn["secure"] is False and conn["https_url"].startswith("https://")
    assert api.get("/ca.crt").status_code == 404   # sin run.py no hay certificados


def test_diagnostics_snapshot_on_error(api, fake, tmp_path, monkeypatch):
    from dataclasses import replace

    from .test_phase2 import login
    login(api)
    moodle = api.main.get_moodle()
    monkeypatch.setattr(moodle, "settings", replace(moodle.settings, diagnostics=True))
    r = api.post("/api/courses/7/rename", headers=h(api), json={"kind": "cm", "id": 999999, "name": "x"})
    assert r.status_code >= 400
    shots = list((tmp_path / "diagnostics").glob("*/pantalla.png"))
    assert shots and "pagina: /course/view.php" in (shots[0].parent / "info.txt").read_text()
