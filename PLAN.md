# Florida Teacher App — Plan

App para gestionar Florida Oberta (Moodle) desde una tablet Android. El servidor
corre en el PC del profesor y la tablet lo usa como PWA a través de la red local.

## Estado

| Fase | Estado |
|------|--------|
| 1. Base: login y listado de cursos | ✅ Hecha |
| 2. Creación de tareas (fechas, archivos, restricciones) | ⏭️ Siguiente |
| 3. Contenidos del curso | Pendiente |
| 4. Entregas y calificación | Pendiente |
| 5. Planificación, plantillas y calendario | Pendiente |
| 6. Robustez y usabilidad | Pendiente |
| 7. Seguridad, empaquetado y publicación | Pendiente |

## Arquitectura

```
Tablet Android (PWA)  ──LAN/HTTP──▶  PC: FastAPI :8000  ──Playwright/HTTPS──▶  Florida Oberta (Moodle)
                                        │
                                        └─ backend/data/  (SQLite, clave Fernet, sesión del navegador)
```

- **Backend (`backend/`)**: FastAPI + SQLite (`backend/data/app.db`, sin ORM). Es el único punto
  de integración con Florida Oberta. En producción también sirve la PWA compilada
  (`frontend/dist`) en el mismo puerto.
- **Integración Moodle sin token** (`backend/app/moodle/`): Playwright (Chromium) rellena el
  formulario de login como una persona. El estado de sesión (cookies) se guarda en
  `backend/data/storage_state.json` y se reutiliza; si caduca, se vuelve a iniciar sesión
  automáticamente. Los cursos se obtienen con la misma llamada AJAX interna que usa el panel de
  Moodle (`core_course_get_enrolled_courses_by_timeline_classification`, con cookie + `sesskey`,
  sin token de servicios web) y, si falla, leyendo los enlaces de `/my/courses.php`.
- **Selectores centralizados**: todas las rutas y selectores CSS de Moodle están en
  `backend/app/moodle/selectors.py`. Si Florida Oberta cambia de tema o versión, solo se toca ese
  archivo.
- **Credenciales cifradas**: la contraseña se cifra con Fernet antes de guardarse en SQLite. La
  clave se genera en el primer arranque en `backend/data/secret.key` (permisos 600, carpeta 700).
  La API nunca devuelve la contraseña. Todo `backend/data/` y `backend/.env` están en `.gitignore`.
- **Frontend (`frontend/`)**: React + Vite + `vite-plugin-pwa` (manifest, service worker, iconos).
  Las llamadas `/api` nunca se cachean. En desarrollo Vite hace de proxy de `/api` hacia el PC.
- **Acceso en la red local**: el servidor escucha en `0.0.0.0`. Opcionalmente, `APP_ACCESS_TOKEN`
  en `backend/.env` obliga a enviar la cabecera `X-App-Token` (la tablet pide el código una vez y
  lo recuerda). Úsalo solo en una red privada de confianza y nunca lo expongas a Internet.

### API (Fase 1)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Comprobación sin autenticación |
| GET | `/api/status` | URL de Moodle, usuario guardado, última sincronización |
| PUT | `/api/credentials` | Prueba el login y guarda las credenciales cifradas (`?verify=false` para no probar) |
| DELETE | `/api/credentials` | Borra credenciales y sesión |
| POST | `/api/login/test` | Fuerza un login real con las credenciales guardadas |
| GET | `/api/courses` | Cursos guardados en SQLite |
| POST | `/api/courses/sync` | Descarga los cursos de Florida Oberta y los guarda |

## Puesta en marcha

Requisitos en el PC: Python 3.11+, Node 18+.

1. `cp backend/.env.example backend/.env` y define `MOODLE_BASE_URL` (URL de Florida Oberta, sin
   barra final). Opcional: `APP_ACCESS_TOKEN`, `MOODLE_HEADLESS=false` para ver el navegador.
2. Arranque rápido: `./start.sh` (Linux/macOS) o `.\start.ps1` (Windows). Crea el entorno virtual,
   instala Chromium de Playwright, compila la PWA y lanza el servidor en el puerto 8000.
3. En la tablet (misma Wi-Fi), abre `http://IP-DEL-PC:8000`, introduce usuario y contraseña de
   Florida Oberta y pulsa «Iniciar sesión y guardar». Permite el puerto 8000 en el firewall del PC
   solo para la red privada.

Desarrollo con recarga en caliente:

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt \
  && .venv/bin/python -m playwright install chromium
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd frontend && npm install && npm run dev   # http://IP-DEL-PC:5173
```

Pruebas: `cd backend && .venv/bin/pytest`. Usan un Moodle simulado local
(`tests/fake_moodle.py`) que cubre login correcto/incorrecto, reutilización de sesión, la vía
AJAX y la alternativa por DOM.

**Nota PWA en Android**: Chrome solo registra el service worker (instalación completa, modo
offline) en orígenes seguros. Por `http://IP-local` se puede «Añadir a pantalla de inicio» pero
sin service worker. Para la PWA completa: HTTPS local (p. ej. certificado de `mkcert` instalado en
la tablet y `uvicorn --ssl-keyfile/--ssl-certfile`) o, solo para pruebas, la opción
`chrome://flags/#unsafely-treat-insecure-origin-as-secure`. Se automatiza en la Fase 6.

## Las 7 fases

### 1. Base: login y listado de cursos ✅
FastAPI + SQLite, PWA React/Vite, credenciales cifradas en local, login Playwright con
reutilización de sesión, selectores centralizados, sincronización y listado de cursos, token de
acceso opcional, scripts de arranque y pruebas con Moodle simulado.

### 2. Creación de tareas
Crear actividades «Tarea» (`mod/assign`) en un curso desde la tablet:
- Formulario: nombre, descripción, sección/tema destino, visibilidad.
- Fechas: disponible desde, fecha de entrega, fecha límite, recordarme calificar.
- Archivos adicionales (enunciados) subidos desde la tablet al PC y adjuntados vía el selector de
  archivos de Moodle.
- Tipos de entrega (texto en línea / archivos, nº y tamaño máximo) y calificación máxima.
- Restricciones de acceso: por fecha, grupo/agrupamiento y calificación de otra actividad.
- Resumen previo y confirmación explícita antes de crear; guardar registro local (SQLite) y enlace
  a la tarea creada. Selectores del formulario `modedit.php` en `selectors.py`.

### 3. Contenidos del curso
Ver secciones, recursos y actividades de cada curso; subir archivos/recursos, renombrar secciones,
mostrar/ocultar elementos, con confirmación antes de cambios.

### 4. Entregas y calificación
Listar entregas por tarea (pendientes, entregadas, con retraso), descargar entregas al PC,
calificar y añadir retroalimentación desde la tablet.

### 5. Planificación, plantillas y calendario
Plantillas de tareas reutilizables, duplicar una tarea en varios cursos/grupos con desplazamiento
de fechas, vista de calendario de entregas y recordatorios locales.

### 6. Robustez y usabilidad
Modo offline de la PWA (lectura de datos cacheados), HTTPS local asistido, recuperación de sesión
caducada, reintentos, diagnóstico de selectores (captura de pantalla + HTML cuando algo falla),
accesibilidad y ajustes para tablet.

### 7. Seguridad, empaquetado y publicación
Autenticación local robusta (emparejamiento de dispositivos), gestión de la clave (keyring del
sistema), copias de seguridad, más pruebas automatizadas, arranque como servicio/instalador en el
PC y revisión de seguridad.

## Limitaciones conocidas

- No es un cliente oficial de la API de Moodle: si Florida Oberta cambia el login (p. ej. SSO
  externo o captcha) o el marcado, hay que ajustar `selectors.py`. Con SSO puede ser necesario un
  login manual con `MOODLE_HEADLESS=false` para guardar la sesión.
- Las operaciones de navegador se ejecutan de una en una (bloqueo interno).
- Quien tenga acceso a `backend/data/` en el PC puede descifrar las credenciales.
