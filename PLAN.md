# Florida Teacher App — Plan

App para gestionar Florida Oberta (Moodle) desde una tablet Android. El servidor
corre en el PC del profesor y la tablet lo usa como PWA a través de la red local.

## Estado

| Fase | Estado |
|------|--------|
| 1. Base: login Microsoft (Office 365) y listado de cursos | ✅ Hecha |
| 2. Creación de tareas (fechas, archivos, restricciones) | ✅ Hecha y validada |
| 3. Contenidos del curso | ✅ Hecha (pendiente de validar con Florida Oberta real) |
| 4. Entregas y calificación | ✅ Hecha (pendiente de validar con Florida Oberta real) |
| 5. Planificación, plantillas y calendario | ✅ Hecha (pendiente de validar con Florida Oberta real) |
| 6. Robustez y usabilidad | ✅ Hecha |
| 7. Seguridad, empaquetado y publicación | ✅ Hecha |

## Arquitectura

```
Tablet Android (PWA)  ──LAN/HTTP──▶  PC: FastAPI :8000  ──Playwright/HTTPS──▶  Florida Oberta (Moodle)
                                        │
                                        └─ backend/data/  (SQLite, clave Fernet, sesión del navegador)
```

- **Backend (`backend/`)**: FastAPI + SQLite (`backend/data/app.db`, sin ORM). Es el único punto
  de integración con Florida Oberta. En producción también sirve la PWA compilada
  (`frontend/dist`) en el mismo puerto.
- **Integración Moodle sin token** (`backend/app/moodle/`): Florida Oberta inicia sesión con
  **Microsoft (Office 365)**. Playwright (Chromium) recorre ese flujo como una persona: botón de
  Microsoft en Moodle → correo → contraseña → verificación en dos pasos → «¿Mantener la sesión
  iniciada?». La **MFA nunca se salta**: la tablet muestra el número de Microsoft Authenticator o
  pide el código, y el profesor aprueba en su móvil. El login corre en segundo plano y la tablet
  consulta su estado. Las cookies (Moodle + Microsoft) se guardan **cifradas** en
  `backend/data/session.enc`, se reutilizan y caducan a los `SESSION_MAX_DAYS` días. Si la sesión
  caduca, se reintenta en silencio; si Microsoft pide MFA, la API responde 409 y la tablet pide
  reconectar. Alternativas: `LOGIN_MODE=moodle` (formulario propio de Moodle) y «login manual»
  en una ventana de Chromium del PC para cuentas con métodos no soportados. Los cursos se obtienen con la misma llamada AJAX interna que usa el panel de
  Moodle (`core_course_get_enrolled_courses_by_timeline_classification`, con cookie + `sesskey`,
  sin token de servicios web) y, si falla, leyendo los enlaces de `/my/courses.php`.
- **Selectores centralizados**: todas las rutas y selectores CSS de Moodle están en
  `backend/app/moodle/selectors.py`. Si Florida Oberta cambia de tema o versión, solo se toca ese
  archivo.
- **Credenciales cifradas**: la contraseña **solo se guarda si el profesor marca «Recordar
  contraseña»**, y entonces cifrada con Fernet. La clave se genera en el primer arranque en
  `backend/data/secret.key` (permisos 600, carpeta 700). La API nunca devuelve la contraseña.
  Todo `backend/data/` y `backend/.env` están en `.gitignore`.
- **Protección de datos**: ver [PRIVACIDAD.md](PRIVACIDAD.md) (RGPD/LOPDGDD: minimización,
  cifrado, caducidad, derecho de acceso y supresión desde la pestaña *Privacidad*, y pasos que
  debe dar el profesor, empezando por la autorización de Florida).
- **Frontend (`frontend/`)**: React + Vite + `vite-plugin-pwa` (manifest, service worker, iconos).
  Las llamadas `/api` nunca se cachean. En desarrollo Vite hace de proxy de `/api` hacia el PC.
- **Acceso en la red local**: el servidor escucha en `0.0.0.0`. Toda la API exige un **código de
  emparejamiento** (cabecera `X-App-Token`): se genera al azar en el primer arranque
  (`backend/data/access_code`, se muestra en la consola) o se fija con `APP_ACCESS_TOKEN`. La
  tablet lo pide una vez. 5 intentos fallidos bloquean la IP 5 minutos. Sin CORS, con cabeceras de
  seguridad (CSP, `no-store`). Úsalo solo en una red privada y nunca lo expongas a Internet.

### API (Fase 1)

Todas salvo `/api/health` exigen la cabecera `X-App-Token`.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Comprobación sin autenticación |
| GET | `/api/status` | Configuración, cuenta, sesión, última sincronización, login en curso |
| POST | `/api/login/start` | Inicia el login en segundo plano (`username`, `password`, `remember_password`, `manual`) |
| GET | `/api/login/status` | Estado: `working`, `mfa_number` (+`number`), `mfa_push`, `mfa_code`, `manual`, `success`, `error`, `cancelled` |
| POST | `/api/login/code` | Envía el código de verificación de Microsoft |
| POST | `/api/login/cancel` | Cancela el login en curso |
| POST | `/api/logout` | Borra cookies y contraseña recordada |
| GET | `/api/courses` | Cursos guardados en SQLite |
| POST | `/api/courses/sync` | Descarga los cursos (409 si hay que reconectar) |
| GET | `/api/privacy` | Inventario de datos guardados (derecho de acceso) |
| DELETE | `/api/data` | Borra todo y destruye la clave (derecho de supresión) |

## Puesta en marcha

Requisitos en el PC: Python 3.11+, Node 18+.

0. Lee [PRIVACIDAD.md](PRIVACIDAD.md) y pide el visto bueno a Florida (DPD / informática).
1. **Windows:** doble clic en `Iniciar.bat`. **Linux/macOS:** `./start.sh`. La primera vez instala
   dependencias y Chromium, crea `backend/.env` (ya apunta a `https://www.floridaoberta.com`),
   compila la PWA y, en Windows, crea una regla de firewall solo para redes privadas.
2. La consola muestra la dirección para la tablet (`http://IP-DEL-PC:8000`) y el **código de
   acceso**. Ábrela en Chrome de la tablet (misma Wi-Fi), escribe el código, tu correo
   institucional y contraseña, y aprueba en Microsoft Authenticator si lo pide.
3. **En el PC** la interfaz se abre sola en una ventana propia (Edge/Chrome en modo app) en
   `http://localhost:8000`, ya vinculada: el lanzador pasa el código en el fragmento `#code=`
   (no llega al servidor y se borra de la barra). En Windows se crea además el acceso directo
   «Florida Teacher App» en el escritorio. Desde Edge se puede instalar como app
   (⋯ → Aplicaciones → Instalar).
4. Opcional: `MOODLE_HEADLESS=false` en `backend/.env` para ver el navegador en el PC.

Florida Oberta (`https://www.floridaoberta.com`) usa el botón «Conectar con Office 365»
(`/auth/oidc/`) que redirige a `login.microsoftonline.com` (inquilino de Grupo Florida);
comprobado contra la web real.

Desarrollo con recarga en caliente:

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt \
  && .venv/bin/python -m playwright install chromium
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd frontend && npm install && npm run dev   # http://IP-DEL-PC:5173
```

Pruebas: `cd backend && .venv/bin/pytest`. Usan un Moodle y un login de Microsoft simulados
(`tests/fake_moodle.py`, en dominios distintos) que cubren: Microsoft sin MFA, con número y con
código, código/contraseña/usuario erróneos, relogin silencioso que se detiene ante MFA,
reutilización de la sesión cifrada, formulario propio de Moodle, alternativa por DOM, código de
acceso y bloqueo, cabeceras de seguridad, que la contraseña nunca queda en claro en disco, y el
borrado total.

**Nota PWA en Android**: Chrome solo registra el service worker (instalación completa, modo
offline) en orígenes seguros. Por `http://IP-local` se puede «Añadir a pantalla de inicio» pero
sin service worker. Para la PWA completa: HTTPS local (p. ej. certificado de `mkcert` instalado en
la tablet y `uvicorn --ssl-keyfile/--ssl-certfile`) o, solo para pruebas, la opción
`chrome://flags/#unsafely-treat-insecure-origin-as-secure`. Se automatiza en la Fase 6.

## Las 7 fases

### 1. Base: login Microsoft y listado de cursos ✅
FastAPI + SQLite, PWA React/Vite, login Playwright vía Microsoft (Office 365) con MFA aprobada
desde la tablet, sesión y contraseña opcional cifradas, selectores centralizados, sincronización y
listado de cursos, código de emparejamiento obligatorio, pestaña de privacidad con borrado total,
scripts de arranque y pruebas con Moodle/Microsoft simulados.

### 2. Creación de tareas ✅
Implementado: tocar un curso → «Nueva tarea» → formulario → revisión → creación. API:
`GET /api/courses/{id}/assign-options` (temas, grupos, agrupamientos, elementos de calificación,
límites de archivos; solo nombres, sin alumnado), `POST /api/courses/{id}/assignments` (multipart:
`data` JSON + `files`), `GET /api/courses/{id}/assignments` (registro local). Lógica en
`backend/app/moodle/assign.py` y `backend/app/assignments.py`; ids del formulario en `selectors.py`
(`ASSIGN_FIELDS`, `ASSIGN_DATES`, `ATTACH_*`, `PICKER_*`). Las restricciones se escriben como el JSON
de `core_availability`.

Alcance original:
Crear actividades «Tarea» (`mod/assign`) en un curso desde la tablet:
- Formulario: nombre, descripción, sección/tema destino, visibilidad.
- Fechas: disponible desde, fecha de entrega, fecha límite, recordarme calificar.
- Archivos adicionales (enunciados) subidos desde la tablet al PC y adjuntados vía el selector de
  archivos de Moodle.
- Tipos de entrega (texto en línea / archivos, nº y tamaño máximo) y calificación máxima.
- Restricciones de acceso: por fecha, grupo/agrupamiento y calificación de otra actividad.
- Resumen previo y confirmación explícita antes de crear; guardar registro local (SQLite) y enlace
  a la tarea creada. Selectores del formulario `modedit.php` en `selectors.py`.
- Privacidad: los archivos subidos se guardan en el PC solo hasta adjuntarlos y luego se borran;
  restricciones por grupo usan solo el nombre/id del grupo, sin listar alumnado.

### 3. Contenidos del curso ✅
Implementado: pestaña «Contenidos» en cada curso con temas y elementos (tipo, nombre, visibilidad),
mostrar/ocultar y renombrar temas y elementos (con confirmación), y añadir Archivo o Enlace a un
tema. Lectura con `core_courseformat_get_state` (alternativa: página del curso); cambios con
`core_courseformat_update_course` (alternativa `core_course_edit_module/section`) y
`core_update_inplace_editable`; recursos con `modedit.php` (`mod_resource`, `mod_url`). API:
`GET /api/courses/{id}/contents`, `POST …/visibility`, `POST …/rename`, `POST …/resources`.
Código en `backend/app/moodle/contents.py`; nombres en `selectors.py` (sección FASE 3).
No se borra nada desde la app.

Alcance original:
Ver secciones, recursos y actividades de cada curso; subir archivos/recursos, renombrar secciones,
mostrar/ocultar elementos, con confirmación antes de cambios.

### 4. Entregas y calificación ✅
Implementado (con autorización de Florida): pestaña «Entregas y notas» en cada curso → tarea →
lista de participantes con filtros (entregados, sin entregar, con retraso, sin nota), archivos
descargables a la tablet, texto en línea, y nota + comentario + notificar con confirmación. Lectura
de la tabla «Ver todas las entregas» (todas las páginas); calificación con el formulario clásico
`action=grade`. Datos del alumnado sin persistencia (ver PRIVACIDAD.md §6). API:
`GET /api/courses/{id}/assign/{cmid}/submissions`, `POST …/grade`, `GET …/file?url=`.
Código en `backend/app/moodle/grading.py`; selectores en `selectors.py` (sección FASE 4).

Alcance original:
Listar entregas por tarea (pendientes, entregadas, con retraso), descargar entregas al PC,
calificar y añadir retroalimentación desde la tablet. **Trata datos del alumnado**: requiere
autorización expresa de Florida, minimización (descargar solo lo necesario y borrarlo después),
cifrado de lo que se guarde e inventario/borrado en la pestaña *Privacidad*
(ver [PRIVACIDAD.md](PRIVACIDAD.md) §6).

### 5. Planificación, plantillas y calendario ✅
Implementado: plantillas de tarea guardadas en el PC con fechas relativas (+N días a HH:MM),
crear la misma tarea en varios cursos (sin copiar restricciones de grupo/agrupamiento/nota, que
son de cada curso) y pestaña «Calendario» mensual con los eventos de Florida Oberta
(`core_calendar_get_calendar_monthly_view`). API: `GET/POST/DELETE /api/templates`,
`GET /api/calendar?year=&month=`. Recordatorios con notificaciones quedan para la Fase 6 (requieren
HTTPS en la tablet).

Alcance original:
Plantillas de tareas reutilizables, duplicar una tarea en varios cursos/grupos con desplazamiento
de fechas, vista de calendario de entregas y recordatorios locales.

### 6. Robustez y usabilidad ✅
Implementado: `backend/run.py` sirve HTTP (8000) y **HTTPS (8443)** a la vez. HTTPS usa una CA local
(`backend/app/tls.py`, `data/tls/`) limitada con *Name Constraints* a `localhost` y a IPs privadas,
de modo que su clave no sirve para suplantar webs de Internet; el certificado del servidor se
renueva si cambia la IP del PC. Instalando el certificado público (`/ca.crt`) en la tablet, la PWA
funciona completa (service worker, instalación). `HTTP_LAN=false` deja el HTTP solo para el propio
PC. Aviso de «sin conexión» en la app. Diagnóstico opcional (`DIAGNOSTICS=true`): captura y ruta de
la página cuando una operación falla, en `data/diagnostics/`, borrado a los 7 días y **nunca** en
las pantallas de entregas/notas. Recuperación de sesión, reintentos de login y selectores
centralizados ya estaban de fases anteriores.

Alcance original:
Modo offline de la PWA (lectura de datos cacheados), HTTPS local asistido, recuperación de sesión
caducada, reintentos, diagnóstico de selectores (captura de pantalla + HTML cuando algo falla),
accesibilidad y ajustes para tablet.

### 7. Seguridad, empaquetado y publicación ✅
Implementado: clave de cifrado en el **llavero del sistema** (Administrador de credenciales de
Windows; migración automática desde `secret.key`; `KEY_STORAGE=file` para desactivarlo), **cambio
del código de acceso** (desvincula todos los dispositivos), **copia de seguridad** sin datos
sensibles (plantillas y registro de tareas; `GET/POST /api/backup`), `Actualizar.bat` (git pull +
dependencias + compilación), `Inicio-automatico.bat` (activa/desactiva el arranque minimizado al
iniciar sesión), dependencias revisadas en cada arranque, reglas de firewall solo para redes
privadas, pruebas automáticas (pytest + Playwright contra Moodle/Microsoft simulados) y CI en
GitHub Actions. Revisión de seguridad: ver la sección «Seguridad» más abajo.

Alcance original:
Autenticación local robusta (emparejamiento de dispositivos), gestión de la clave (keyring del
sistema), copias de seguridad, más pruebas automatizadas, arranque como servicio/instalador en el
PC y revisión de seguridad.

## Limitaciones conocidas

- No es un cliente oficial de la API de Moodle: si Florida Oberta o Microsoft cambian sus páginas,
  hay que ajustar `selectors.py`. Los selectores de Microsoft cubren la interfaz clásica y la
  nueva, pero solo se han probado contra una simulación: la primera conexión real puede requerir
  ajustes. Métodos MFA no previstos (llave FIDO, Windows Hello) → «login manual» en el PC.
- El uso de la app debe estar permitido por las normas de Florida (ver PRIVACIDAD.md §1).
- Las operaciones de navegador se ejecutan de una en una (bloqueo interno).
- Quien tenga acceso a `backend/data/` en el PC (con tu usuario) puede descifrar la sesión y la
  contraseña recordada: activa el cifrado de disco. Guardar la clave en el llavero del sistema
  queda para la Fase 7.

## Seguridad (revisión de la Fase 7)

- Toda la API exige el código de acceso (salvo `/api/health` y el certificado público `/ca.crt`);
  5 fallos por IP → bloqueo 5 min; código rotable desde la app.
- Sin CORS, CSP restrictiva, `X-Frame-Options: DENY`, `no-store` en la API, sin docs públicas.
- Secretos: contraseña (opcional) y cookies cifradas con Fernet; clave en el llavero del sistema;
  archivos de datos con permisos 600 / carpeta 700; nada sensible en Git ni en las copias.
- Datos del alumnado sin persistencia (PRIVACIDAD.md §6); descargas sin escribir en disco y solo de
  URLs `pluginfile.php/…/assignsubmission_file/` del propio Florida Oberta.
- Entradas validadas (pydantic): fechas, tamaños (100 MB/archivo, 20 archivos), URLs solo http(s),
  nombres de archivo saneados; HTML de descripciones/comentarios escapado.
- MFA de Microsoft nunca se automatiza; cada cambio en Florida Oberta pide confirmación.
- Riesgos aceptados: el servidor HTTP en la LAN sigue activo por compatibilidad (`HTTP_LAN=false`
  para desactivarlo una vez instalado el certificado); quien controle tu usuario del PC puede leer
  los datos de la app.
