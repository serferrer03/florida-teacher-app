@echo off
title Actualizar Florida Teacher App
cd /d "%~dp0"
echo Descargando la ultima version...
git pull || (echo No se pudo actualizar & pause & exit /b 1)
if exist backend\.venv backend\.venv\Scripts\pip install -q -r backend\requirements.txt
cd frontend && call npm install --no-fund --no-audit && call npm run build && cd ..
echo.
echo Listo. Cierra la ventana negra de la app (si esta abierta) y vuelve a abrir Iniciar.bat
pause
