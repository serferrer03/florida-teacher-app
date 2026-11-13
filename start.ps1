# Florida Teacher App - arranque en Windows (lo lanza Iniciar.bat).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Need($cmd, $name, $url) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host "Falta $name. Instalalo desde $url (o: winget install $name) y vuelve a ejecutar." -ForegroundColor Red
    Read-Host "Pulsa Intro para salir"; exit 1
  }
}
Need python "Python.Python.3.12" "https://www.python.org (marca 'Add python.exe to PATH')"
Need npm "OpenJS.NodeJS.LTS" "https://nodejs.org"

if (-not (Test-Path backend\.venv)) {
  Write-Host "Primera ejecucion: instalando dependencias (unos minutos)..." -ForegroundColor Cyan
  python -m venv backend\.venv
  backend\.venv\Scripts\python -m pip install --upgrade pip
  backend\.venv\Scripts\pip install -r backend\requirements.txt
  backend\.venv\Scripts\python -m playwright install chromium
}
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }

Push-Location frontend
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location

# Permitir el puerto en el firewall solo para redes privadas (pide permisos de administrador una vez)
$port = if ($env:PORT) { $env:PORT } else { 8000 }
if (-not (Get-NetFirewallRule -DisplayName "Florida Teacher App" -ErrorAction SilentlyContinue)) {
  Write-Host "Creando regla de firewall (solo redes privadas, puerto $port)..." -ForegroundColor Cyan
  Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command New-NetFirewallRule -DisplayName 'Florida Teacher App' -Direction Inbound -Protocol TCP -LocalPort $port -Profile Private -Action Allow" -ErrorAction SilentlyContinue
}

# Acceso directo en el escritorio (una vez)
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Florida Teacher App.lnk"
if (-not (Test-Path $lnk)) {
  $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $sc.TargetPath = Join-Path $PSScriptRoot "Iniciar.bat"
  $sc.WorkingDirectory = $PSScriptRoot
  $sc.Save()
}

# Abrir la interfaz en el PC cuando el servidor esté listo (ventana propia de Edge/Chrome)
Start-Job -ArgumentList $PSScriptRoot, $port -ScriptBlock {
  param($root, $port)
  for ($i = 0; $i -lt 120; $i++) {
    try { Invoke-RestMethod "http://localhost:$port/api/health" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 }
  }
  $code = (Select-String -Path "$root\backend\.env" -Pattern '^APP_ACCESS_TOKEN=(.+)$' -ErrorAction SilentlyContinue).Matches.Groups[1].Value
  if (-not $code) { $code = (Get-Content "$root\backend\data\access_code" -ErrorAction SilentlyContinue | Select-Object -First 1) }
  $url = "http://localhost:$port/#code=$($code.Trim())"
  try { Start-Process msedge -ArgumentList "--app=$url" } catch {
    try { Start-Process chrome -ArgumentList "--app=$url" } catch { Start-Process $url } }
} | Out-Null

Set-Location backend
$env:PORT = $port
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port $port
