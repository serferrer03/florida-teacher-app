"""Moodle falso mínimo para probar el flujo de Playwright sin red."""
from __future__ import annotations

import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

USER, PASSWORD, SESSKEY = "profe", "secreto", "abc123"
COURSES = [
    {"id": 7, "fullname": "Programación DAM 1", "shortname": "PRG1", "coursecategory": "DAM"},
    {"id": 3, "fullname": "Bases de datos", "shortname": "BD", "coursecategory": "DAM"},
]


class FakeMoodle:
    def __init__(self) -> None:
        self.logins = 0
        self.ajax_enabled = True
        self.app = self._build()

    def _build(self) -> FastAPI:
        app = FastAPI()

        def logged(req: Request) -> bool:
            return req.cookies.get("MoodleSession") == "ok"

        def login_page(error: str = "") -> HTMLResponse:
            err = f'<div id="loginerrormessage" class="alert alert-danger">{error}</div>' if error else ""
            return HTMLResponse(f"""<html><body>{err}
<form id="login" method="post" action="/login/index.php">
<input id="username" name="username"><input id="password" name="password" type="password">
<button id="loginbtn" type="submit">Acceder</button></form>
<script>window.M={{cfg:{{sesskey:'guest'}}}}</script></body></html>""")

        @app.get("/login/index.php")
        def login_get():
            return login_page()

        @app.post("/login/index.php")
        def login_post(username: str = Form(...), password: str = Form(...)):
            if username == USER and password == PASSWORD:
                self.logins += 1
                r = RedirectResponse("/my/", status_code=303)
                r.set_cookie("MoodleSession", "ok")
                return r
            return login_page("Datos erróneos. Por favor, inténtelo otra vez.")

        @app.get("/my/")
        def dashboard(req: Request):
            if not logged(req):
                return RedirectResponse("/login/index.php", status_code=303)
            return HTMLResponse(f"""<html><body>
<a id="user-menu-toggle"><span class="userinitials">PF</span></a>
<script>window.M={{cfg:{{sesskey:'{SESSKEY}'}}}}</script></body></html>""")

        @app.get("/my/courses.php")
        def my_courses(req: Request):
            if not logged(req):
                return RedirectResponse("/login/index.php", status_code=303)
            items = "".join(
                f'<div data-region="course-content"><a href="/course/view.php?id={c["id"]}">'
                f'<span class="sr-only">Nombre del curso</span><span class="multiline">{c["fullname"]}</span></a></div>'
                for c in COURSES
            )
            return HTMLResponse(f'<html><body><div data-region="courses-view">{items}</div></body></html>')

        @app.post("/lib/ajax/service.php")
        def ajax(req: Request, sesskey: str = ""):
            if not self.ajax_enabled:
                return JSONResponse({"error": "disabled"}, status_code=500)
            if not logged(req) or sesskey != SESSKEY:
                return JSONResponse([{"error": True, "exception": {"message": "sesskey"}}])
            base = str(req.base_url).rstrip("/")
            courses = [{**c, "viewurl": f"{base}/course/view.php?id={c['id']}"} for c in COURSES]
            return JSONResponse([{"error": False, "data": {"courses": courses, "nextoffset": 2}}])

        return app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(fake: FakeMoodle) -> tuple[str, uvicorn.Server]:
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(fake.app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server
