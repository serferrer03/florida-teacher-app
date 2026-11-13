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
        self.email_glitches = 0
        self.created: list[dict] = []   # tareas recibidas por el formulario
        self.state_api = True            # core_courseformat_get_state disponible
        self.sections = [
            {"id": 100, "number": 0, "title": "General", "visible": True, "cmlist": [1]},
            {"id": 101, "number": 1, "title": "Tema 1: Introducción", "visible": True, "cmlist": [2, 3]},
        ]
        self.cms = {
            1: {"id": 1, "name": "Avisos", "module": "forum", "visible": True},
            2: {"id": 2, "name": "Apuntes T1", "module": "resource", "visible": True},
            3: {"id": 3, "name": "Práctica 0", "module": "assign", "visible": False},
        }
        self.inplace: list[dict] = []
        self.uploads: dict[str, bytes] = {}
        self.mode = "microsoft"
        self.mfa: str | None = None
        self.mfa_approved = False
        self.kmsi_answer: str | None = None
        self.app = self._build()

    def reset(self, mode: str = "microsoft", mfa: str | None = None) -> None:
        self.mode, self.mfa, self.mfa_approved, self.kmsi_answer = mode, mfa, False, None
        self.ajax_enabled = True
        self.ajax_empty = False
        self.email_glitches = 0

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
        async def ajax(req: Request, sesskey: str = ""):
            call = (await req.json())[0]
            method, args = call["methodname"], call["args"]
            if method != "core_course_get_enrolled_courses_by_timeline_classification":
                if not logged(req) or sesskey != SESSKEY:
                    return JSONResponse([{"error": True, "exception": {"errorcode": "invalidsesskey"}}])
                return JSONResponse([self.content_call(method, args)])
            if not self.ajax_enabled:
                return JSONResponse({"error": "disabled"}, status_code=500)
            if not logged(req) or sesskey != SESSKEY:
                return JSONResponse([{"error": True, "exception": {"message": "sesskey"}}])
            base = str(req.base_url).rstrip("/")
            courses = [] if self.ajax_empty else [{**c, "viewurl": f"{base}/course/view.php?id={c['id']}"} for c in COURSES]
            return JSONResponse([{"error": False, "data": {"courses": courses, "nextoffset": 2}}])

        # ------------------------------------------- Fase 2: curso y tareas
        @app.get("/course/view.php")
        def course_view(req: Request, id: int):
            if not logged(req):
                return RedirectResponse("/login/index.php", status_code=303)
            return HTMLResponse(f"""<html><body class="format-topics"><a id="user-menu-toggle"></a>
<script>window.M={{cfg:{{sesskey:'{SESSKEY}'}}}}</script><ul>
<li id="section-0" class="section"><h3 class="sectionname">General</h3></li>
<li id="section-1" class="section"><h3 class="sectionname">Tema 1: Introducción</h3></li>
<li id="section-2" class="section"><h3 class="sectionname">Tema 2</h3></li></ul></body></html>""")

        def date_fields(base: str, enabled: bool) -> str:
            sel = lambda n, a, b: f'<select id="id_{base}_{n}" name="{base}[{n}]">' + "".join(  # noqa: E731
                f'<option value="{v}">{v}</option>' for v in range(a, b)) + "</select>"
            chk = "checked" if enabled else ""
            return (f'<input type="checkbox" id="id_{base}_enabled" name="{base}[enabled]" value="1" {chk}>'
                    + sel("day", 1, 32) + sel("month", 1, 13) + sel("year", 2020, 2031)
                    + sel("hour", 0, 24) + f'<select id="id_{base}_minute" name="{base}[minute]">'
                    + "".join(f'<option value="{m}">{m:02d}</option>' for m in range(0, 60, 5)) + "</select>")

        @app.get("/course/modedit.php")
        def modedit(req: Request, course: int = 0, section: int = 0, error: str = "", add: str = "assign"):
            if not logged(req):
                return RedirectResponse("/login/index.php", status_code=303)
            if add in ("resource", "url"):
                return HTMLResponse(self.resource_form(course, section, add))
            err = f'<div class="invalid-feedback" id="id_error_name">{error}</div>' if error else ""
            dates = "".join(date_fields(b, b != "cutoffdate") for b in
                            ("allowsubmissionsfromdate", "duedate", "cutoffdate", "gradingduedate"))
            return HTMLResponse(f"""<html><body>
<form class="mform" method="post" action="/course/modedit.php">
<input type="hidden" name="course" value="{course}"><input type="hidden" name="section" value="{section}">
<input id="id_name" name="name">{err}
<textarea id="id_introeditor" name="introeditor[text]"></textarea>
<input type="checkbox" id="id_showdescription" name="showdescription" value="1">
<div id="fitem_id_introattachments"><div class="fp-btn-add"><a href="#" onclick="openPicker();return false">Agregar</a></div>
<div class="fp-files"></div><input type="hidden" name="introattachments" id="att" value=""></div>
<fieldset style="display:none">{dates}
<input type="checkbox" id="id_assignsubmission_onlinetext_enabled" name="assignsubmission_onlinetext_enabled" value="1">
<input type="checkbox" id="id_assignsubmission_file_enabled" name="assignsubmission_file_enabled" value="1" checked>
<select id="id_assignsubmission_file_maxfiles" name="assignsubmission_file_maxfiles">{"".join(f'<option value="{i}">{i}</option>' for i in range(1, 21))}</select>
<select id="id_assignsubmission_file_maxsizebytes" name="assignsubmission_file_maxsizebytes">
<option value="0">Límite de subida del curso (100 MB)</option><option value="10485760">10 MB</option><option value="1048576">1 MB</option></select>
<select id="id_grade_modgrade_type" name="grade[modgrade_type]"><option value="none">Ninguna</option><option value="point" selected>Puntuación</option></select>
<input id="id_grade_modgrade_point" name="grade[modgrade_point]" value="100">
<select id="id_visible" name="visible"><option value="1">Mostrar</option><option value="0">Ocultar</option></select>
<textarea id="id_availabilityconditionsjson" name="availabilityconditionsjson"></textarea>
</fieldset>
<input type="submit" id="id_submitbutton2" value="Guardar y regresar al curso">
<input type="submit" id="id_submitbutton" name="submitbutton" value="Guardar cambios y mostrar">
</form>
<div class="file-picker" id="picker" style="display:none">
 <div class="fp-repo"><a href="#">Subir un archivo</a></div>
 <input type="file" name="repo_upload_file" id="upfile"><button class="fp-upload-btn" onclick="upload();return false">Subir este archivo</button>
</div>
<script>
window.M = {{cfg: {{sesskey: '{SESSKEY}'}},
  availability_group: {{form: {{groups: [{{id: 11, name: 'Grupo A'}}, {{id: 12, name: 'Grupo B'}}]}}}},
  availability_grouping: {{form: {{groupings: [{{id: 21, name: 'Mañana'}}]}}}},
  availability_grade: {{form: {{grades: [{{id: 31, name: 'Práctica 1'}}]}}}}}};
// Como formslib: el checkbox "Habilitar" activa/desactiva los selects de la fecha
document.querySelectorAll('input[id$="_enabled"][id^="id_"]').forEach(cb => {{
  const base = cb.id.replace('_enabled', '');
  const sync = () => document.querySelectorAll(`select[id^="${{base}}_"]`).forEach(s => s.disabled = !cb.checked);
  cb.addEventListener('click', sync); sync();
}});
function openPicker() {{ document.getElementById('picker').style.display = 'block'; }}
async function upload() {{
  const f = document.getElementById('upfile').files[0];
  const fd = new FormData(); fd.append('repo_upload_file', f);
  const r = await (await fetch('/repository/upload', {{method: 'POST', body: fd}})).json();
  const d = document.createElement('div'); d.className = 'fp-filename'; d.textContent = r.name;
  document.querySelector('#fitem_id_introattachments .fp-files').appendChild(d);
  const att = document.getElementById('att'); att.value = (att.value ? att.value + '|' : '') + r.name;
  document.getElementById('upfile').value = '';
  document.getElementById('picker').style.display = 'none';
}}
</script></body></html>""")

        # ------------------------------------------- Fase 4: entregas
        students = [
            {"id": 41, "name": "Ana Pérez", "status": "Enviado para calificar", "cls": "submissionstatussubmitted",
             "late": True, "file": "ana_practica.pdf"},
            {"id": 42, "name": "Luis Gómez", "status": "No entregado", "cls": "submissionstatus", "late": False, "file": None},
        ] + [{"id": 100 + i, "name": f"Alumno {i:02d}", "status": "No entregado", "cls": "submissionstatus",
              "late": False, "file": None} for i in range(12)]
        self.grades: dict[int, dict] = {}

        @app.get("/mod/assign/view.php")
        def assign_view(req: Request, id: int, action: str = "", page: int = 0, userid: int = 0):
            if not logged(req):
                return RedirectResponse("/login/index.php", status_code=303)
            head = f"<script>window.M={{cfg:{{sesskey:'{SESSKEY}'}}}}</script>"
            if action == "grading":
                rows = ""
                for s in students[page * 10:(page + 1) * 10]:
                    late = '<div class="latesubmission">Enviado con 2 días de retraso</div>' if s["late"] else ""
                    f = (f'<a href="/pluginfile.php/99/assignsubmission_file/submission_files/1/{s["file"]}">{s["file"]}</a>'
                         if s["file"] else "")
                    g = self.grades.get(s["id"], {})
                    rows += (f'<tr><td><input type="checkbox" name="selectedusers" value="{s["id"]}"></td>'
                             f'<td><a href="/user/view.php?id={s["id"]}&course=7">{s["name"]}</a></td>'
                             f'<td>{s["name"].lower().replace(" ", ".")}@alumnos.example</td>'
                             f'<td><div class="{s["cls"]}">{s["status"]}</div>{late}</td>'
                             f'<td>{g.get("grade", "-")} / 10,00</td><td>lunes, 1 de diciembre</td>'
                             f'<td>{f}</td><td>{g.get("feedback", "")}</td><td>-</td></tr>')
                if not rows:
                    rows = '<tr class="emptyrow"><td></td></tr>'
                return HTMLResponse(f"""<html lang="es"><body>{head}<table class="generaltable"><thead><tr>
<th>Seleccionar</th><th>Nombre / Apellido(s)</th><th>Dirección de correo</th><th>Estado</th><th>Calificación</th>
<th>Última modificación (entrega)</th><th>Archivos enviados</th><th>Comentarios de retroalimentación</th>
<th>Calificación final</th></tr></thead><tbody>{rows}</tbody></table></body></html>""")
            if action == "grade":
                return HTMLResponse(f"""<html lang="es"><body>{head}<form class="mform" method="post"
action="/mod/assign/grade?cmid={id}&userid={userid}"><input id="id_grade" name="grade">
<textarea id="id_assignfeedbackcomments_editor" name="assignfeedbackcomments_editor[text]"></textarea>
<input type="checkbox" id="id_sendstudentnotifications" name="sendstudentnotifications" value="1" checked>
<input type="submit" id="id_savegrade" value="Guardar cambios"></form></body></html>""")
            return HTMLResponse(f'<html><body><a id="user-menu-toggle"></a><h2>Tarea {id}</h2>{head}</body></html>')

        @app.post("/mod/assign/grade")
        async def grade_post(req: Request, cmid: int, userid: int):
            form = dict((await req.form()).multi_items())
            g = form.get("grade", "")
            try:
                if g:
                    float(g.replace(",", "."))
            except ValueError:
                return HTMLResponse('<html><body><div id="id_error_grade" class="invalid-feedback">Nota no válida</div></body></html>')
            self.grades[userid] = {"grade": g, "feedback": form.get("assignfeedbackcomments_editor[text]", ""),
                                   "notify": form.get("sendstudentnotifications") == "1"}
            return RedirectResponse(f"/mod/assign/view.php?id={cmid}&action=grading", status_code=303)

        @app.get("/pluginfile.php/{rest:path}")
        def pluginfile(req: Request, rest: str):
            if not logged(req):
                return HTMLResponse("login", status_code=403)
            return HTMLResponse(b"%PDF entrega", media_type="application/pdf")

        @app.post("/repository/upload")
        async def repo_upload(req: Request):
            form = await req.form()
            f = form["repo_upload_file"]
            self.uploads[f.filename] = await f.read()
            return {"name": f.filename}

        @app.post("/course/modedit.php")
        async def modedit_post(req: Request):
            form = dict((await req.form()).multi_items())
            if form.get("modulename") in ("resource", "url"):
                cmid = 900 + len(self.cms)
                self.cms[cmid] = {"id": cmid, "name": form["name"], "module": form["modulename"],
                                  "visible": form.get("visible") == "1", "form": form}
                sec = next(s for s in self.sections if s["number"] == int(form["section"]))
                sec["cmlist"].append(cmid)
                return RedirectResponse(f"/course/view.php?id={form['course']}", status_code=303)
            if not form.get("name"):
                return modedit(req, int(form.get("course", 0)), int(form.get("section", 0)),
                               "Falta incluir este campo")
            cmid = 500 + len(self.created)
            self.created.append(form)
            return RedirectResponse(f"/mod/assign/view.php?id={cmid}", status_code=303)


        # ------------------------------------------- Microsoft (simulado)
        @app.get("/ms/login")
        def ms_login(error: str = ""):
            err = f'<div id="usernameError">{error}</div>' if error else ""
            return HTMLResponse(f"""<html><body>{MS_STYLE}{err}
<form method="post" action="/ms/login"><input type="email" name="loginfmt">
<input type="submit" id="idSIButton9" value="Siguiente"></form></body></html>""")

        @app.post("/ms/login")
        def ms_login_post(loginfmt: str = Form("")):
            if self.email_glitches > 0:  # como cuando la página borra el campo al cargar
                self.email_glitches -= 1
                return ms_login("Escriba una dirección de correo electrónico, un número de teléfono o un nombre Skype válidos.")
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

    # --------------------------------------------- Fase 3 (contenidos)
    def content_call(self, method: str, args: dict) -> dict:
        import json as _json
        if method == "core_courseformat_get_state":
            if not self.state_api:
                return {"error": True, "exception": {"errorcode": "servicenotavailable"}}
            return {"error": False, "data": _json.dumps({"section": self.sections, "cm": list(self.cms.values())})}
        if method == "core_courseformat_update_course":
            kind, act = args["action"].split("_")
            for i in args["ids"]:
                target = self.cms[i] if kind == "cm" else next(s for s in self.sections if s["id"] == i)
                target["visible"] = act == "show"
            return {"error": False, "data": "[]"}
        if method == "core_update_inplace_editable":
            self.inplace.append(args)
            if args["itemtype"] == "activityname":
                self.cms[args["itemid"]]["name"] = args["value"]
            else:
                next(s for s in self.sections if s["id"] == args["itemid"])["title"] = args["value"]
            return {"error": False, "data": {}}
        if method == "core_calendar_get_calendar_monthly_view":
            import datetime as _dt
            t = int(_dt.datetime(args["year"], args["month"], 15, 23, 55).timestamp())
            ev = {"id": 77, "name": "Práctica 1 debe entregarse", "timestart": t, "modulename": "assign",
                  "normalisedeventtype": "course", "url": "/mod/assign/view.php?id=500",
                  "course": {"id": 7, "fullname": "Programación DAM 1"}}
            return {"error": False, "data": {"weeks": [{"days": [{"events": [ev]}, {"events": [ev]}]}]}}
        return {"error": True, "exception": {"errorcode": "invalidparameter", "message": method}}

    def resource_form(self, course: int, section: int, mod: str) -> str:
        extra = ('<input id="id_externalurl" name="externalurl">' if mod == "url" else
                 '<div id="fitem_id_files"><div class="fp-btn-add"><a href="#" onclick="openPicker();return false">'
                 'Agregar</a></div><div class="fp-files"></div><input type="hidden" name="files" id="att"></div>')
        return f"""<html><body>
<form class="mform" method="post" action="/course/modedit.php">
<input type="hidden" name="course" value="{course}"><input type="hidden" name="section" value="{section}">
<input type="hidden" name="modulename" value="{mod}">
<input id="id_name" name="name"><textarea id="id_introeditor" name="introeditor[text]"></textarea>
<input type="checkbox" id="id_showdescription" name="showdescription" value="1">{extra}
<select id="id_visible" name="visible"><option value="1">Mostrar</option><option value="0">Ocultar</option></select>
<input type="submit" id="id_submitbutton2" name="submitbutton2" value="Guardar cambios y regresar al curso">
</form>
<div class="file-picker" id="picker" style="display:none"><div class="fp-repo"><a href="#">Subir un archivo</a></div>
<input type="file" name="repo_upload_file" id="upfile"><button class="fp-upload-btn" onclick="upload();return false">Subir</button></div>
<script>
window.M = {{cfg: {{sesskey: '{SESSKEY}'}}}};
function openPicker() {{ document.getElementById('picker').style.display = 'block'; }}
async function upload() {{
  const f = document.getElementById('upfile').files[0];
  const fd = new FormData(); fd.append('repo_upload_file', f);
  const r = await (await fetch('/repository/upload', {{method: 'POST', body: fd}})).json();
  const d = document.createElement('div'); d.className = 'fp-filename'; d.textContent = r.name;
  document.querySelector('#fitem_id_files .fp-files').appendChild(d);
  const att = document.getElementById('att'); att.value = (att.value ? att.value + '|' : '') + r.name;
  document.getElementById('upfile').value = ''; document.getElementById('picker').style.display = 'none';
}}
</script></body></html>"""


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
