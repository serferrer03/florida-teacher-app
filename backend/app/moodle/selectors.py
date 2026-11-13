"""Selectores y rutas de Florida Oberta (Moodle + inicio de sesión Microsoft/Office 365).

Si Florida Oberta o Microsoft cambian sus páginas y algo deja de funcionar,
ajusta SOLO este archivo. Cada selector admite alternativas separadas por coma
(sintaxis CSS estándar).
"""

# ============================ MOODLE ======================================
# --- Rutas relativas a MOODLE_BASE_URL ------------------------------------
LOGIN_PATH = "/login/index.php"
DASHBOARD_PATH = "/my/"
MY_COURSES_PATH = "/my/courses.php"
AJAX_SERVICE_PATH = "/lib/ajax/service.php"
COURSE_VIEW_PATH = "/course/view.php?id={id}"

# --- Botón "Iniciar sesión con Microsoft" (Florida Oberta usa auth_oidc -> /auth/oidc/) --
IDP_BUTTON = (
    "a.login-identityprovider-btn, .potentialidplist a, "
    "a[href*='/auth/oidc/'], a[href*='/auth/oauth2/login.php'], a[href*='/auth/saml2/login.php']"
)

# --- Formulario de login propio de Moodle (alternativa, LOGIN_MODE=moodle) --
LOGIN_USERNAME = "input#username, input[name='username']"
LOGIN_PASSWORD = "input#password, input[name='password']"
LOGIN_SUBMIT = "button#loginbtn, input#loginbtn, form#login [type='submit'], form.login-form [type='submit']"
LOGIN_ERROR = "#loginerrormessage, .loginerrors .error, .login-form .alert-danger, .alert.alert-danger"

# --- Indicadores de sesión iniciada en Moodle -----------------------------
LOGGED_IN_MARKER = "#user-menu-toggle, .usermenu .userbutton, a[href*='login/logout.php']"
USER_FULLNAME = "#user-menu-toggle .userinitials, .usermenu .usertext, .userbutton .usertext"

# --- Listado de cursos (alternativa por DOM si falla la llamada AJAX) -------
COURSE_LINK = "a[href*='/course/view.php?id=']"
COURSE_NAME = ".multiline, .coursename, [data-region='course-name']"

# --- Llamada AJAX interna de Moodle (la misma que usa el panel /my/) --------
# No requiere token de servicios web: usa la cookie de sesión + sesskey.
AJAX_COURSES_METHOD = "core_course_get_enrolled_courses_by_timeline_classification"
JS_SESSKEY = "() => (window.M && M.cfg && M.cfg.sesskey) || null"

# ===================== MICROSOFT (login.microsoftonline.com) ===============
MS_EMAIL = "input[name='loginfmt']"
MS_PASSWORD = "input[name='passwd']"
# Botón principal (Siguiente / Iniciar sesión / Sí). Interfaz clásica y nueva.
MS_SUBMIT = "#idSIButton9, button[data-testid='primaryButton'], button[type='submit'], input[type='submit']"
MS_ERROR = "#usernameError, #passwordError, #idTD_Error, #field-error, [data-testid='errorMessage'], .alert-error"
# Selector de cuenta ("Elegir una cuenta") -> "Usar otra cuenta"
MS_OTHER_ACCOUNT = "#otherTile, [data-test-id='otherTile']"
# MFA: número que hay que escribir en Microsoft Authenticator
MS_MFA_NUMBER = "#idRichContext_DisplaySign, [data-testid='displaySign']"
# MFA: aprobación push sin número ("Aprobar solicitud de inicio de sesión")
MS_MFA_PUSH = "#idDiv_SAOTCAS_Title, #idDiv_SAOTCAS_Description"
# MFA: código de verificación (SMS / app / llamada)
MS_MFA_CODE = "input[name='otc'], #idTxtBx_SAOTCC_OTC"
MS_MFA_CODE_SUBMIT = "#idSubmit_SAOTCC_Continue, button[type='submit'], input[type='submit']"
# MFA: lista para elegir método de verificación -> se usa el primero (el predeterminado)
MS_MFA_PROOFS = "#idDiv_SAOTCS_Proofs [role='listitem'], #idDiv_SAOTCS_Proofs .table, [data-testid='proofList'] [role='button']"
# "¿Quiere mantener la sesión iniciada?"
MS_KMSI = "#KmsiDescription, #KmsiCheckboxField, form[action*='kmsi']"
MS_KMSI_YES = "#idSIButton9, button[data-testid='primaryButton']"
MS_KMSI_NO = "#idBtn_Back, button[data-testid='secondaryButton']"

# ================== FASE 2: CREAR TAREAS (mod/assign) =====================
# Secciones (temas) en la página del curso
COURSE_SECTION = "li.section[id^='section-'], li.course-section[id^='section-']"
COURSE_SECTION_NAME = ".sectionname, [data-for='section_title'], h3"

# Formulario estándar de Moodle para añadir una tarea
ASSIGN_ADD_PATH = "/course/modedit.php?add=assign&type=&course={course}&section={section}&return=0&sr=0"
ASSIGN_VIEW_PATH = "/mod/assign/view.php?id={cmid}"
MODEDIT_FORM = "form.mform"
# ids de los campos (formslib: id_<nombre>)
ASSIGN_FIELDS = {
    "name": "id_name",
    "intro": "id_introeditor",              # descripción (TinyMCE/Atto sobre este textarea)
    "showdescription": "id_showdescription",
    "visible": "id_visible",
    "onlinetext": "id_assignsubmission_onlinetext_enabled",
    "file": "id_assignsubmission_file_enabled",
    "maxfiles": "id_assignsubmission_file_maxfiles",
    "maxsize": "id_assignsubmission_file_maxsizebytes",
    "grade_type": "id_grade_modgrade_type",
    "grade_point": "id_grade_modgrade_point",
    "availability": "id_availabilityconditionsjson",  # JSON de "Restricciones de acceso"
}
# Fechas: id_<base>_enabled, id_<base>_day/_month/_year/_hour/_minute
ASSIGN_DATES = {
    "allow_from": "allowsubmissionsfromdate",
    "due": "duedate",
    "cutoff": "cutoffdate",
    "grading_due": "gradingduedate",
}
ASSIGN_SUBMIT = "#id_submitbutton"          # "Guardar cambios y mostrar"
FORM_ERRORS = "[id^='id_error_'], .invalid-feedback, span.error, .alert-danger"

# "Archivos adicionales" (filemanager introattachments) y selector de archivos
ATTACH_ADD = "#fitem_id_introattachments .fp-btn-add a, #fitem_id_introattachments .fp-btn-add button"
ATTACH_FILENAME = "#fitem_id_introattachments .fp-filename"
PICKER_DIALOG = ".file-picker"
PICKER_UPLOAD_REPO = ".fp-repo:has-text('Subir un archivo'), .fp-repo:has-text('Upload a file')"
PICKER_FILE_INPUT = "input[type='file'][name='repo_upload_file']"
PICKER_UPLOAD_BTN = ".fp-upload-btn"
PICKER_ERROR = ".fp-msg-error, .moodle-dialogue .fp-msg"

# Datos que el propio formulario carga para el editor de restricciones
# (solo nombres de grupos/agrupamientos/elementos de calificación, sin alumnado)
JS_AVAILABILITY_OPTIONS = """() => {
  const g = (o, k) => (o && o.form && o.form[k]) || [];
  const M_ = window.M || {};
  return {
    enabled: !!document.getElementById('id_availabilityconditionsjson'),
    groups: g(M_.availability_group, 'groups'),
    groupings: g(M_.availability_grouping, 'groupings'),
    grades: g(M_.availability_grade, 'grades'),
  };
}"""
