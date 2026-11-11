# Florida Teacher App — Plan

## Architecture

This project runs on the teacher's PC and is intended to be opened from a tablet on the same trusted local network.

- **Backend:** FastAPI provides a small REST API, serves as the sole integration point with Florida Oberta, and stores app data in SQLite (`backend/data/app.db`).
- **Moodle integration:** Playwright automates an ordinary browser login using the user's own credentials. Moodle-specific selectors live together in `backend/app/moodle/selectors.py` so they can be updated in one place. The Moodle base URL is configurable through `MOODLE_BASE_URL`; no API token is assumed.
- **Credential and session storage:** Credentials are encrypted at rest with Fernet. The encryption key is generated locally and stored under `backend/data/`; neither credentials nor keys belong in source control. Playwright's reusable authenticated storage state is also kept under that local data directory. These files are sensitive and are excluded by `.gitignore`.
- **Frontend:** React + Vite provides the setup/login and course-listing interface; the PWA manifest/service worker makes the app installable on Android. The UI communicates with FastAPI over the local network.
- **Network/security boundary:** The backend may listen on the PC's LAN interface so a tablet can reach it. Use only on a trusted private network, keep the firewall enabled, and do not expose the service to the public internet. The initial local app has no user-account/authentication layer; adding one is a later-phase hardening item.

## Run locally (development)

1. Configure `MOODLE_BASE_URL` to the Florida Oberta Moodle login/site URL.
2. Install backend dependencies from `backend/requirements.txt`, install Playwright's Chromium browser, and start FastAPI on `0.0.0.0:8000`.
3. Install frontend dependencies in `frontend/` and start Vite with host access enabled. Open the Vite URL from the tablet using the PC's LAN IP.
4. Enter the Moodle username and password in the app. The backend encrypts and saves them locally, launches Playwright for login, and reuses the saved authenticated session on later course refreshes. If the session expires, log in again.

## Seven phases

1. **Foundation (current):** FastAPI + SQLite, React/Vite installable PWA, local encrypted credential storage, Playwright login/session reuse, centralized selectors, and first course list.
2. **Course detail:** Navigate course pages and present relevant sections, resources, and activities.
3. **Teacher workflows:** Add safe, explicit workflows for common teaching tasks, with confirmation before consequential changes.
4. **Files and materials:** Organize, preview, and download course materials with clear local storage controls.
5. **Planning and reminders:** Add schedules, deadlines, and configurable local reminders.
6. **Resilience and usability:** Improve offline behavior, tablet accessibility, session-expiry recovery, and Moodle selector diagnostics.
7. **Hardening and release:** Add local app authentication, stronger secret/key management and backup guidance, tests, packaging/startup tooling, and security review before wider use.

## Initial scope and limitations

Phase 1 only signs in and lists courses. Moodle may change its login or course markup; central selectors should then be adjusted and the authentication/course-list flows retested. Credentials and browser state remain on the PC. This is a local integration, not an official Moodle API client.
