#!/usr/bin/env bash
# Arranca la app en el PC (Linux/macOS): compila la PWA y lanza FastAPI en la red local.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
  backend/.venv/bin/python -m playwright install chromium
fi
[ -f backend/.env ] || cp backend/.env.example backend/.env
(cd frontend && { [ -d node_modules ] || npm install; } && npm run build)
export PORT="${PORT:-8000}"
cd backend && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
