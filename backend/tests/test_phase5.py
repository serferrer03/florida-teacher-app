from .test_api import api, h, wait_state  # noqa: F401
from .test_phase2 import login


def test_templates_crud(api):
    data = {"name": "Práctica", "rel": {"due": {"days": 7, "time": "23:55"}}, "grade_max": 10}
    r = api.post("/api/templates", headers=h(api), json={"name": "  Práctica   semanal ", "data": data})
    tid = r.json()["id"]
    lst = api.get("/api/templates", headers=h(api)).json()["templates"]
    assert lst[0]["name"] == "Práctica semanal" and lst[0]["data"] == data
    assert api.delete(f"/api/templates/{tid}", headers=h(api)).status_code == 200
    assert api.delete(f"/api/templates/{tid}", headers=h(api)).status_code == 404


def test_calendar_month(api):
    login(api)
    r = api.get("/api/calendar?year=2026&month=12", headers=h(api))
    assert r.status_code == 200, r.text
    ev = r.json()["events"]
    assert len(ev) == 1 and ev[0]["course"] == "Programación DAM 1" and ev[0]["modname"] == "assign"
    assert api.get("/api/calendar?year=2026&month=13", headers=h(api)).status_code == 422
