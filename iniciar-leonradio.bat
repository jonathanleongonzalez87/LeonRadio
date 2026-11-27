@echo off
setlocal EnableExtensions
title LeonRadio
cd /d "%~dp0"

rem ===== Configuracion (puedes cambiarla) =====
rem Por defecto visible en la red local (con clave): el telefono se conecta con el QR de Ayuda > Conectar el telefono.
rem En Windows, al preguntar por el Firewall, marca SOLO "Redes privadas". Solo este PC: set LEONRADIO_HOST=127.0.0.1 antes de ejecutar.
set "HOST=0.0.0.0"
if defined LEONRADIO_HOST set "HOST=%LEONRADIO_HOST%"
set "PORT=8765"
if defined LEONRADIO_PORT set "PORT=%LEONRADIO_PORT%"
set "VENV=%LOCALAPPDATA%\LeonRadio\venv"
set "LIB=%~1"
if "%LIB%"=="" set "LIB=%~dp0..\Rockland Radio"

echo.
echo  ===== LeonRadio =====

rem ===== Si ya hay un servidor en ese puerto, solo abrir el navegador =====
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo  Ya hay un servidor en el puerto %PORT%. Abriendo el navegador...
  if not defined LEONRADIO_NO_BROWSER start "" "http://127.0.0.1:%PORT%/"
  ping -n 4 127.0.0.1 >nul
  exit /b 0
)

rem ===== Entorno de Python: solo la primera vez, fuera de OneDrive =====
if not exist "%VENV%\Scripts\python.exe" (
  echo  Primera vez: creando el entorno de Python en %VENV%
  where py >nul 2>nul && py -3 -m venv "%VENV%"
  if not exist "%VENV%\Scripts\python.exe" python -m venv "%VENV%"
  if not exist "%VENV%\Scripts\python.exe" (
    echo.
    echo  ERROR: no se pudo crear el entorno de Python.
    echo  Instala Python 3.12 o superior desde python.org y marca "Add python.exe to PATH".
    pause
    exit /b 1
  )
)

rem ===== Dependencias: rapido si ya estan instaladas =====
echo  Comprobando dependencias...
"%VENV%\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -e "core[api,audio]"
if errorlevel 1 (
  echo.
  echo  ERROR: no se pudieron instalar las dependencias. Revisa tu conexion a internet.
  pause
  exit /b 1
)

rem ===== Abrir el navegador cuando el servidor este listo =====
if not defined LEONRADIO_NO_BROWSER start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep 4; Start-Process 'http://127.0.0.1:%PORT%/'"

echo  Biblioteca: %LIB%
echo  La emision empieza en PAUSA: pulsa Reproducir en el panel Aire.
echo  Para detener LeonRadio cierra esta ventana o pulsa Ctrl+C.
echo.
"%VENV%\Scripts\leonradio.exe" serve --library "%LIB%" --port %PORT% --host %HOST%
echo.
echo  LeonRadio se detuvo.
pause
