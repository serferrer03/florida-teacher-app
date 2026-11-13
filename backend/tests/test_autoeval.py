import time

from app import ai_eval

from .test_api import api, h, wait_state  # noqa: F401
from .test_phase2 import login


def test_students_overview(api):
    login(api)
    r = api.get("/api/courses/7/students-overview", headers=h(api))
    assert r.status_code == 200, r.text
    d = r.json()
    cmids = [a["cmid"] for a in d["assignments"]]
    assert cmids and len(d["students"]) == 14
    ana = next(s for s in d["students"] if s["name"] == "Ana Pérez")
    assert all(ana["tasks"][str(c)]["submitted"] for c in cmids)
    luis = next(s for s in d["students"] if s["name"] == "Luis Gómez")
    assert not luis["tasks"][str(cmids[0])]["submitted"]


def test_build_content_hides_names():
    blocks, skipped = ai_eval.build_content(
        "Práctica 1", "Correcto 50%, estilo 50%", 10,
        ai_eval.Submission("Mi respuesta", [("ana_perez_practica.pdf", b"%PDF"), ("codigo.py", b"print(1)"),
                                            ("video.mp4", b"x")]))
    text = str(blocks)
    assert "ana" not in text.lower() and "archivo_1.pdf" in text and "print(1)" in text
    assert skipped == ["archivo_3.mp4"]


def test_autoeval_flow(api, fake, monkeypatch):
    login(api)
    main = api.main
    seen = []

    async def fake_eval(task, criteria, grade_max, sub):
        seen.append((task, criteria, sub))
        return ai_eval.Evaluation(8.25, "Buen trabajo; mejora los comentarios.", False)

    pushed = []

    async def fake_push(rows):
        pushed.extend(rows)
        return None

    monkeypatch.setattr(main.autoeval, "evaluator", fake_eval)
    monkeypatch.setattr("app.autoeval.sheets.push", fake_push)
    monkeypatch.setattr("app.main.sheets.push", fake_push)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")

    cfg = {"name": "Práctica 0", "criteria": "Funciona y está bien explicado", "grade_max": 10,
           "close_at": "2020-01-01T00:00"}
    assert api.put("/api/courses/7/assign/3/autoeval", headers=h(api), json=cfg).status_code == 403
    api.post("/api/autoeval/ack", headers=h(api))
    assert api.put("/api/courses/7/assign/3/autoeval", headers=h(api), json=cfg).status_code == 200

    # el programador detecta que la tarea ya cerró
    assert api.post("/api/courses/7/assign/3/autoeval/run", headers=h(api)).status_code == 200
    for _ in range(100):
        d = api.get("/api/courses/7/assign/3/autoeval", headers=h(api)).json()
        if d["config"]["state"] == "review":
            break
        time.sleep(0.2)
    assert d["config"]["state"] == "review", d["config"]
    assert [r["name"] for r in d["results"]] == ["Ana Pérez"] and d["results"][0]["grade"] == 8.25
    task, criteria, sub = seen[0]
    assert "Ana" not in task + criteria + sub.onlinetext   # el nombre no llega a la IA
    assert pushed[0]["alumno"] == "Ana Pérez" and pushed[0]["estado"].startswith("Propuesta")

    # el nombre se guarda cifrado en el PC
    assert b"Ana" not in main.db.list_results(3)[0]["name_enc"]

    api.patch("/api/courses/7/assign/3/autoeval/results/41", headers=h(api),
              json={"grade": 8.5, "observation": "Buen trabajo."})
    r = api.post("/api/courses/7/assign/3/autoeval/publish", headers=h(api), json={"notify": False}).json()
    assert r["published"] == 1 and not r["errors"]
    assert fake.grades[41]["grade"] == "8,5" and fake.grades[41]["feedback"] == "<p>Buen trabajo.</p>"
    assert pushed[-1]["estado"] == "Publicada en Florida Oberta"
    assert api.get("/api/courses/7/assign/3/autoeval", headers=h(api)).json()["config"]["state"] == "done"


def test_scheduler_runs_only_after_close(api, monkeypatch):
    login(api)
    main = api.main
    calls = []

    async def fake_run(cmid):
        calls.append(cmid)

    monkeypatch.setattr(main.autoeval, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    api.post("/api/autoeval/ack", headers=h(api))
    base = {"criteria": "Criterios de prueba", "grade_max": 10}
    api.put("/api/courses/7/assign/3/autoeval", headers=h(api),
            json={**base, "name": "Futura", "close_at": "2999-01-01T00:00"})
    api.portal.call(main.autoeval.run_due)
    assert calls == []
    api.put("/api/courses/7/assign/3/autoeval", headers=h(api),
            json={**base, "name": "Cerrada", "close_at": "2020-01-01T00:00"})
    api.portal.call(main.autoeval.run_due)
    assert calls == [3]
