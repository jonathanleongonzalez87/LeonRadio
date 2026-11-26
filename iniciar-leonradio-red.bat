@echo off
rem Inicia LeonRadio visible en tu red local: otros equipos abren http://<IP de esta PC>:8765/
rem La primera vez Windows pregunta por el Firewall: permite el acceso en redes privadas.
set "LEONRADIO_HOST=0.0.0.0"
call "%~dp0iniciar-leonradio.bat" %*
