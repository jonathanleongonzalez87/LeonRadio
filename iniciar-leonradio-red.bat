@echo off
rem Inicia LeonRadio visible en tu red local: otros equipos abren http://<IP de esta PC>:8765/
rem La primera vez Windows pregunta por el Firewall: permite el acceso en redes privadas.
rem ACCESO CON CLAVE: los demas equipos de la red necesitan una clave de acceso. La primera vez se crea y se
rem muestra UNA sola vez en esta ventana: anotala. Este PC entra sin clave por http://127.0.0.1:8765/.
rem Si la pierdes: abre una ventana de comandos en este PC, escribe  leonradio clave  y pulsa Enter.
rem Crea una nueva y la anterior deja de valer en todos los dispositivos.
rem El trafico va sin cifrar: usalo solo en una red de confianza.
rem NO uses un proxy o tunel local (ngrok, Caddy, etc.) con este modo: si reescribe el Host a localhost,
rem el trafico de fuera pasaria por el PC local y entraria sin clave.
set "LEONRADIO_HOST=0.0.0.0"
call "%~dp0iniciar-leonradio.bat" %*
