@echo off
rem Doble clic: prueba balanza, lector e impresora del puesto y crea el acceso directo "Odoo Puesto".
rem Ejecuta probar-perifericos.ps1 (misma carpeta). No necesita administrador.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0probar-perifericos.ps1"
echo.
pause
