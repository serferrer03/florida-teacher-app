import json
import time

import pytest
from pydantic import ValidationError

from app.assignments import AssignmentIn, availability_json, to_form_values

from .fake_moodle import MFA_CODE, PASSWORD, USER
from .test_api import api, h, wait_state  # noqa: F401  (fixture del API)


def test_validation_and_availability():
    with pytest.raises(ValidationError, match="anterior"):
        AssignmentIn(name="T", due="2026-12-01T10:00", cutoff="2026-11-30T10:00")
    with pytest.raises(ValidationError, match="tipo de entrega"):
        AssignmentIn(name="T", online_text=False, file_submissions=False)
    a = AssignmentIn(name="  Práctica   1 ", description="Hola <b>\n\nAdiós",
                     restrictions={"date_from": "2026-12-01T08:00", "group_ids": [11, 12],
                                   "grade": {"item_id": 31, "min_percent": 50}, "show_to_students": False})
    v = to_form_values(a)
    assert v["name"] == "Práctica 1"
    assert v["intro_html"] == "<p>Hola &lt;b&gt;</p><p>Adiós</p>"
    av = v["availability"]
    assert av["op"] == "&" and av["showc"] == [False, False, False]
    assert av["c"][2] == {"op": "|", "c": [{"type": "group", "id": 11}, {"type": "group", "id": 12}]}
    assert availability_json(AssignmentIn(name="x").restrictions) is None


def login(api):
    api.post("/api/login/start", headers=h(api), json={"username": USER, "password": PASSWORD})
    wait_state(api, {"mfa_code"})
    api.post("/api/login/code", headers=h(api), json={"code": MFA_CODE})
    assert wait_state(api, {"success", "error"})["state"] == "success"


def test_create_assignment_end_to_end(api, fake, tmp_path):
    login(api)
    fake.created.clear()
    opts = api.get("/api/courses/7/assign-options", headers=h(api)).json()
    assert [s["name"] for s in opts["sections"]][:2] == ["General", "Tema 1: Introducción"]
    assert opts["groups"] == [{"id": 11, "name": "Grupo A"}, {"id": 12, "name": "Grupo B"}]
    assert opts["grade_items"][0]["id"] == 31 and opts["restrictions_enabled"]
    assert opts["max_sizes"][1] == {"value": "10485760", "label": "10 MB"}

    data = {
        "name": "Práctica 1", "description": "Lee el enunciado.", "section": 1, "visible": False,
        "allow_from": "2026-12-01T08:00", "due": "2026-12-15T23:59", "cutoff": None,
        "grading_due": "2026-12-22T09:00", "online_text": True, "file_submissions": True,
        "max_files": 3, "max_size_bytes": 10485760, "grade_max": 10,
        "restrictions": {"group_ids": [12], "date_from": "2026-12-01T08:00"},
    }
    files = [("files", ("enunciado.pdf", b"%PDF-1 prueba", "application/pdf")),
             ("files", ("datos.csv", b"a,b\n1,2", "text/csv"))]
    r = api.post("/api/courses/7/assignments", headers=h(api), data={"data": json.dumps(data)}, files=files)
    assert r.status_code == 200, r.text
    assert r.json()["cmid"] == 500 and r.json()["url"].endswith("/mod/assign/view.php?id=500")

    f = fake.created[-1]
    assert f["name"] == "Práctica 1" and f["section"] == "1" and f["visible"] == "0"
    assert f["introeditor[text]"] == "<p>Lee el enunciado.</p>"
    assert (f["duedate[day]"], f["duedate[month]"], f["duedate[year]"], f["duedate[hour]"], f["duedate[minute]"]) \
        == ("15", "12", "2026", "23", "55")  # minutos: opción más cercana disponible
    assert f["duedate[enabled]"] == "1" and "cutoffdate[enabled]" not in f
    assert f["assignsubmission_onlinetext_enabled"] == "1" and f["assignsubmission_file_maxfiles"] == "3"
    assert f["assignsubmission_file_maxsizebytes"] == "10485760" and f["grade[modgrade_point]"] == "10"
    av = json.loads(f["availabilityconditionsjson"])
    assert {"type": "group", "id": 12} in av["c"] and av["c"][0]["type"] == "date"
    assert f["introattachments"] == "enunciado.pdf|datos.csv"
    assert fake.uploads["enunciado.pdf"] == b"%PDF-1 prueba"
    # Los archivos no quedan en el PC
    assert not any((tmp_path / "uploads").iterdir())
    assert api.get("/api/courses/7/assignments", headers=h(api)).json()["assignments"][0]["cmid"] == 500


def test_moodle_validation_error_is_reported(api, fake):
    login(api)
    data = {"name": "x", "file_submissions": True}
    # Nombre válido para nosotros pero vaciado por Moodle: simulamos con un curso y nombre vacío
    r = api.post("/api/courses/7/assignments", headers=h(api), data={"data": json.dumps({**data, "name": " "})})
    assert r.status_code == 422 and "vacío" in r.json()["detail"]
    r = api.post("/api/courses/999/assignments", headers=h(api), data={"data": json.dumps(data)})
    assert r.status_code == 404
