import json

from .fake_moodle import PASSWORD, USER
from .test_api import api, h, wait_state  # noqa: F401
from .test_phase2 import login


def contents(api):
    r = api.get("/api/courses/7/contents", headers=h(api))
    assert r.status_code == 200, r.text
    return r.json()["sections"]


def test_contents_visibility_rename_and_resources(api, fake, tmp_path):
    login(api)
    secs = contents(api)
    assert [s["name"] for s in secs] == ["General", "Tema 1: Introducción"]
    assert secs[1]["items"][1] == {"cmid": 3, "name": "Práctica 0", "modname": "assign", "visible": False,
                                   "url": f"{fake.url}/mod/assign/view.php?id=3"}

    assert api.post("/api/courses/7/visibility", headers=h(api),
                    json={"kind": "cm", "id": 3, "visible": True}).status_code == 200
    assert api.post("/api/courses/7/visibility", headers=h(api),
                    json={"kind": "section", "id": 101, "visible": False}).status_code == 200
    assert api.post("/api/courses/7/rename", headers=h(api),
                    json={"kind": "section", "id": 101, "name": "  Tema 1:   Bucles "}).status_code == 200
    assert fake.inplace[-1] == {"component": "format_topics", "itemtype": "sectionname", "itemid": 101,
                                "value": "Tema 1: Bucles"}
    api.post("/api/courses/7/rename", headers=h(api), json={"kind": "cm", "id": 2, "name": "Apuntes"})
    s1 = contents(api)[1]
    assert s1["name"] == "Tema 1: Bucles" and not s1["visible"]
    assert [(i["name"], i["visible"]) for i in s1["items"]] == [("Apuntes", True), ("Práctica 0", True)]

    data = {"type": "file", "name": "Apuntes T2", "section": 1, "visible": False, "description": "PDF"}
    r = api.post("/api/courses/7/resources", headers=h(api), data={"data": json.dumps(data)},
                 files=[("files", ("t2.pdf", b"%PDF", "application/pdf"))])
    assert r.status_code == 200, r.text
    url = {"type": "url", "name": "Documentación", "section": 0, "url": "https://docs.python.org"}
    assert api.post("/api/courses/7/resources", headers=h(api), data={"data": json.dumps(url)}).status_code == 200
    bad = {**url, "url": "javascript:alert(1)"}
    assert api.post("/api/courses/7/resources", headers=h(api), data={"data": json.dumps(bad)}).status_code == 422

    new = {c["name"]: c for c in fake.cms.values() if "form" in c}
    assert new["Apuntes T2"]["form"]["files"] == "t2.pdf" and new["Apuntes T2"]["form"]["visible"] == "0"
    assert new["Documentación"]["form"]["externalurl"] == "https://docs.python.org"
    assert not any((tmp_path / "uploads").iterdir())
    secs = contents(api)
    assert "Documentación" in [i["name"] for i in secs[0]["items"]]


def test_contents_fallback_without_state_api(api, fake):
    login(api)
    fake.state_api = False
    try:
        r = api.get("/api/courses/7/contents", headers=h(api))
        assert r.status_code == 200 and r.json()["sections"][0]["name"] == "General"
    finally:
        fake.state_api = True
