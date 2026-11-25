@echo off
setlocal EnableExtensions
title LeonRadio - probar la interfaz sin servidor
cd /d "%~dp0"

echo.
echo  ===== LeonRadio: probar la interfaz SIN servidor =====
echo  Genera dist\LeonRadio-demo.html con tus ultimos cambios y lo abre.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo  ERROR: no encuentro Python. Instala Python 3.12 o superior desde python.org
  echo  y marca "Add python.exe to PATH".
  pause
  exit /b 1
)

%PY% tools\build_demo.py
if errorlevel 1 (
  echo.
  echo  ERROR: no se pudo generar el HTML.
  pause
  exit /b 1
)

if not defined LEONRADIO_NO_BROWSER start "" "%~dp0dist\LeonRadio-demo.html"
echo.
echo  Listo. Tras cambiar el codigo, vuelve a ejecutar este archivo y recarga la pagina.
ping -n 4 127.0.0.1 >nul
