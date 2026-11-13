#!/usr/bin/env bash
# Arranca la app en el PC (Linux/macOS): compila la PWA y lanza FastAPI en la red local.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
  backend/.venv/bin/python -m playwright install chromium
else
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
[ -f backend/.env ] || cp backend/.env.example backend/.env
(cd frontend && { [ -d node_modules ] || npm install; } && npm run build)
export PORT="${PORT:-8000}"
( for i in $(seq 60); do curl -fs "http://localhost:$PORT/api/health" >/dev/null && break; sleep 1; done
  code=$(sed -n 's/^APP_ACCESS_TOKEN=\(..*\)$/\1/p' backend/.env); [ -n "$code" ] || code=$(cat backend/data/access_code 2>/dev/null)
  url="http://localhost:$PORT/#code=$code"
  (command -v xdg-open >/dev/null && xdg-open "$url" || open "$url") >/dev/null 2>&1 ) &
cd backend && exec .venv/bin/python run.py
