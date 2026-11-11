# Arranca la app en el PC (Windows PowerShell): compila la PWA y lanza FastAPI en la red local.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path backend\.venv)) {
  python -m venv backend\.venv
  backend\.venv\Scripts\pip install -r backend\requirements.txt
  backend\.venv\Scripts\python -m playwright install chromium
}
if (-not (Test-Path backend\.env)) {
  Copy-Item backend\.env.example backend\.env
  Write-Host "Edita backend\.env (MOODLE_BASE_URL) y vuelve a ejecutar."; exit 1
}
Push-Location frontend
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location
Set-Location backend
$port = if ($env:PORT) { $env:PORT } else { 8000 }
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port $port
