# Activa o desactiva que Florida Teacher App arranque al iniciar sesión en Windows.
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "Florida Teacher App.lnk"
if (Test-Path $lnk) {
  Remove-Item $lnk
  Write-Host "Inicio automático DESACTIVADO." -ForegroundColor Yellow
} else {
  $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $sc.TargetPath = Join-Path $PSScriptRoot "Iniciar.bat"
  $sc.WorkingDirectory = $PSScriptRoot
  $sc.WindowStyle = 7   # minimizada
  $sc.Save()
  Write-Host "Inicio automático ACTIVADO: la app arrancará minimizada al iniciar sesión." -ForegroundColor Green
}
Read-Host "Pulsa Intro para cerrar"
