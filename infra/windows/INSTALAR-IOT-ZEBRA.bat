@echo off
rem Doble clic: pide permiso de administrador y ejecuta instalar-iot-zebra.ps1 (misma carpeta).
rem Instala la impresora de la Zebra y el IoT de Odoo; el token se pega despues en http://localhost:8069.
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar-iot-zebra.ps1"
echo.
pause
