"""Selectores y rutas de Moodle (Florida Oberta) en un único lugar.

Si Florida Oberta cambia su tema o actualiza Moodle y algo deja de funcionar,
ajusta SOLO este archivo. Cada selector admite alternativas separadas por coma
(sintaxis CSS estándar): Playwright usa la primera que encuentre.
"""

# --- Rutas relativas a MOODLE_BASE_URL ------------------------------------
LOGIN_PATH = "/login/index.php"
DASHBOARD_PATH = "/my/"
MY_COURSES_PATH = "/my/courses.php"
AJAX_SERVICE_PATH = "/lib/ajax/service.php"
COURSE_VIEW_PATH = "/course/view.php?id={id}"

# --- Formulario de login (login/index.php estándar de Moodle 3.x/4.x) -------
LOGIN_USERNAME = "input#username, input[name='username']"
LOGIN_PASSWORD = "input#password, input[name='password']"
LOGIN_SUBMIT = "button#loginbtn, input#loginbtn, form#login [type='submit'], form.login-form [type='submit']"
# Mensaje de error tras credenciales incorrectas
LOGIN_ERROR = "#loginerrormessage, .loginerrors .error, .login-form .alert-danger, .alert.alert-danger"

# --- Indicadores de sesión iniciada ----------------------------------------
# Menú de usuario de la barra superior (Moodle 4.x usa #user-menu-toggle)
LOGGED_IN_MARKER = "#user-menu-toggle, .usermenu .userbutton, a[href*='login/logout.php']"
USER_FULLNAME = "#user-menu-toggle .userinitials, .usermenu .usertext, .userbutton .usertext"

# --- Listado de cursos (alternativa por DOM si falla la llamada AJAX) -------
# Enlaces de curso del bloque "Vista general de cursos" en /my/courses.php
COURSE_LINK = "a[href*='/course/view.php?id=']"
# Texto visible del nombre dentro del enlace (evita el texto oculto "Nombre del curso")
COURSE_NAME = ".multiline, .coursename, [data-region='course-name']"
# Contenedor que indica que el bloque ya terminó de cargar
COURSE_LIST_READY = "[data-region='courses-view'] [data-region='course-content'], [data-region='courses-view'] .empty-message, .coursebox"

# --- Llamada AJAX interna de Moodle (la misma que usa el panel /my/) --------
# No requiere token de servicios web: usa la cookie de sesión + sesskey.
AJAX_COURSES_METHOD = "core_course_get_enrolled_courses_by_timeline_classification"
JS_SESSKEY = "() => (window.M && M.cfg && M.cfg.sesskey) || null"
