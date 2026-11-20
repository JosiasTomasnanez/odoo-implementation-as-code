@echo off
rem Doble clic: pide permiso de administrador y ejecuta habilitar-acceso-tecnico.ps1 (misma carpeta).
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0habilitar-acceso-tecnico.ps1"
echo.
pause
