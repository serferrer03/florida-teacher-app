"""Moodle + login Microsoft falsos para probar el flujo de Playwright sin red.

mode: "moodle"  -> formulario propio de Moodle
      "microsoft" -> botón de Office 365 + páginas tipo login.microsoftonline.com
mfa:  None | "number" (aprobación en Authenticator) | "code" (código SMS/app)
"""
from __future__ import annotations

import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

USER, PASSWORD, SESSKEY = "profe@florida.example", "secreto", "abc123"
MFA_NUMBER, MFA_CODE = "42", "123456"
COURSES = [
    {"id": 7, "fullname": "Programación DAM 1", "shortname": "PRG1", "coursecategory": "DAM"},
    {"id": 3, "fullname": "Bases de datos", "shortname": "BD", "coursecategory": "DAM"},
]

MS_STYLE = "<style>body{font-family:sans-serif}</style>"


class FakeMoodle:
    def __init__(self) -> None:
        self.logins = 0
        self.ajax_enabled = True
        self.ajax_empty = False
        self.mode = "microsoft"
        self.mfa: str | None = None
        self.mfa_approved = False
        self.kmsi_answer: str | None = None
        self.app = self._build()

    def reset(self, mode: str = "microsoft", mfa: str | None = None) -> None:
        self.mode, self.mfa, self.mfa_approved, self.kmsi_answer = mode, mfa, False, None
        self.ajax_enabled = True
        self.ajax_empty = False

    def _build(self) -> FastAPI:
        app = FastAPI()

        def logged(req: Request) -> bool:
            return req.cookies.get("MoodleSession") == "ok"

        def finish_login() -> RedirectResponse:
            self.logins += 1
            r = RedirectResponse("/my/", status_code=303)
            r.set_cookie("MoodleSession", "ok")
            return r

        # ------------------------------------------------------- Moodle
        @app.get("/login/index.php")
        def login_get(error: str = ""):
            if self.mode == "microsoft":
                return HTMLResponse("""<html><body><div class="potentialidplist">
<a class="btn login-identityprovider-btn" href="/auth/oauth2/login.php?id=1">Office 365</a></div>
<script>window.M={cfg:{sesskey:'guest'}}</script></body></html>""")
            err = f'<div id="loginerrormessage" class="alert alert-danger">{error}</div>' if error else ""
            return HTMLResponse(f"""<html><body>{err}
<form id="login" method="post" action="/login/index.php">
<input id="username" name="username"><input id="password" name="password" type="password">
<button id="loginbtn" type="submit">Acceder</button></form>
<script>window.M={{cfg:{{sesskey:'guest'}}}}</script></body></html>""")

        @app.post("/login/index.php")
        def login_post(username: str = Form(...), password: str = Form(...)):
            if username == USER and password == PASSWORD:
                return finish_login()
            return login_get("Datos erróneos. Por favor, inténtelo otra vez.")

        # Microsoft vive en otro dominio: localhost frente a 127.0.0.1 de Moodle
        def ms(req: Request, path: str) -> str:
            return f"http://localhost:{req.url.port}{path}"

        def moodle(req: Request, path: str) -> str:
            return f"http://127.0.0.1:{req.url.port}{path}"

        @app.get("/auth/oauth2/login.php")
        def oauth_start(req: Request):
            return RedirectResponse(ms(req, "/ms/login"), status_code=303)

        @app.get("/auth/oauth2/callback")
        def oauth_callback():
            return finish_login()

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
            courses = [] if self.ajax_empty else [{**c, "viewurl": f"{base}/course/view.php?id={c['id']}"} for c in COURSES]
            return JSONResponse([{"error": False, "data": {"courses": courses, "nextoffset": 2}}])

        # ------------------------------------------- Microsoft (simulado)
        @app.get("/ms/login")
        def ms_login(error: str = ""):
            err = f'<div id="usernameError">{error}</div>' if error else ""
            return HTMLResponse(f"""<html><body>{MS_STYLE}{err}
<form method="post" action="/ms/login"><input type="email" name="loginfmt">
<input type="submit" id="idSIButton9" value="Siguiente"></form></body></html>""")

        @app.post("/ms/login")
        def ms_login_post(loginfmt: str = Form(...)):
            if loginfmt != USER:
                return ms_login("No encontramos ninguna cuenta con ese nombre de usuario.")
            return RedirectResponse("/ms/password", status_code=303)

        @app.get("/ms/password")
        def ms_password(error: str = ""):
            err = f'<div id="passwordError">{error}</div>' if error else ""
            return HTMLResponse(f"""<html><body>{MS_STYLE}{err}
<form method="post" action="/ms/password"><input type="hidden" name="loginfmt" value="{USER}">
<input type="password" name="passwd"><input type="submit" id="idSIButton9" value="Iniciar sesión">
</form></body></html>""")

        @app.post("/ms/password")
        def ms_password_post(passwd: str = Form(...)):
            if passwd != PASSWORD:
                return ms_password("La contraseña de la cuenta o la contraseña no son correctas.")
            if self.mfa == "number":
                return RedirectResponse("/ms/mfa/number", status_code=303)
            if self.mfa == "code":
                return RedirectResponse("/ms/mfa/code", status_code=303)
            return RedirectResponse("/ms/kmsi", status_code=303)

        @app.get("/ms/mfa/number")
        def ms_mfa_number():
            return HTMLResponse(f"""<html><body>{MS_STYLE}
<div id="idDiv_SAOTCAS_Title">Aprobar solicitud de inicio de sesión</div>
<div id="idRichContext_DisplaySign">{MFA_NUMBER}</div>
<script>setInterval(()=>fetch('/ms/mfa/poll').then(r=>r.json()).then(d=>{{if(d.ok)location='/ms/kmsi'}}),300)</script>
</body></html>""")

        @app.get("/ms/mfa/poll")
        def ms_mfa_poll():
            return {"ok": self.mfa_approved}

        @app.post("/ms/mfa/approve")
        def ms_mfa_approve():  # lo que haría el móvil del profesor
            self.mfa_approved = True
            return {"ok": True}

        @app.get("/ms/mfa/code")
        def ms_mfa_code(error: str = ""):
            err = f'<div id="idTD_Error">{error}</div>' if error else ""
            return HTMLResponse(f"""<html><body>{MS_STYLE}{err}
<form method="post" action="/ms/mfa/code"><input name="otc" id="idTxtBx_SAOTCC_OTC">
<input type="submit" id="idSubmit_SAOTCC_Continue" value="Comprobar"></form></body></html>""")

        @app.post("/ms/mfa/code")
        def ms_mfa_code_post(otc: str = Form(...)):
            if otc != MFA_CODE:
                return ms_mfa_code("Has escrito un código no válido.")
            return RedirectResponse("/ms/kmsi", status_code=303)

        @app.get("/ms/kmsi")
        def ms_kmsi():
            return HTMLResponse(f"""<html><body>{MS_STYLE}
<div id="KmsiDescription">¿Quiere mantener la sesión iniciada?</div>
<form method="post" action="/ms/kmsi"><input type="hidden" name="answer" id="ans" value="no">
<input type="submit" id="idBtn_Back" value="No">
<input type="submit" id="idSIButton9" value="Sí" onclick="document.getElementById('ans').value='yes'">
</form></body></html>""")

        @app.post("/ms/kmsi")
        def ms_kmsi_post(req: Request, answer: str = Form(...)):
            self.kmsi_answer = answer
            return RedirectResponse(moodle(req, "/auth/oauth2/callback"), status_code=303)

        return app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(fake: FakeMoodle, port: int | None = None) -> tuple[str, uvicorn.Server]:
    port = port or free_port()
    server = uvicorn.Server(uvicorn.Config(fake.app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server
