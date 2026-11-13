from .test_api import api, h, wait_state  # noqa: F401
from .test_phase2 import login


def test_submissions_grade_and_file(api, fake, tmp_path):
    login(api)
    r = api.get("/api/courses/7/assign/500/submissions", headers=h(api))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["counts"] == {"total": 14, "submitted": 1, "late": 1, "files": 1}  # 2 páginas
    ana = next(s for s in data["submissions"] if s["userid"] == 41)
    assert ana["name"] == "Ana Pérez" and ana["userid"] == 41 and ana["late"]
    assert ana["files"][0]["name"] == "ana_practica.pdf"
    assert "Enviado para calificar" in ana["status"]
    assert "@" not in str(ana)  # no se leen correos

    r = api.post("/api/courses/7/assign/500/grade", headers=h(api),
                 json={"userid": 41, "grade": 7.5, "feedback": "Bien hecho", "notify": False})
    assert r.status_code == 200, r.text
    assert fake.grades[41] == {"grade": "7,5", "feedback": "<p>Bien hecho</p>", "notify": False}
    ana = next(s for s in api.get("/api/courses/7/assign/500/submissions", headers=h(api)).json()["submissions"] if s["userid"] == 41)
    assert ana["grade"].startswith("7,5") and ana["feedback"] == "Bien hecho"

    f = api.get("/api/courses/7/assign/500/file", headers=h(api), params={"url": ana["files"][0]["url"]})
    assert f.status_code == 200 and f.content == b"%PDF entrega"
    assert "ana_practica.pdf" in f.headers["content-disposition"] and f.headers["cache-control"] == "no-store"
    bad = api.get("/api/courses/7/assign/500/file", headers=h(api), params={"url": "https://evil.example/x"})
    assert bad.status_code == 400

    # Nada del alumnado queda en el PC
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert b"Ana P" not in p.read_bytes(), p
