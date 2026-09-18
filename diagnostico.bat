@echo off
cd /d "%~dp0"
chcp 65001 >nul <nul
title PADRON CROP - Modo diagnostico (registra todo en diagnostico.log)
echo =================================================================
echo  MODO DIAGNOSTICO: todo lo que pase queda en diagnostico.log
echo  Usa el panel normal. Si se cierra, abre diagnostico.log y
echo  envialo para ver la ultima linea antes del cierre.
echo =================================================================
echo.
if exist diagnostico.log del diagnostico.log
ejecutar_recorte.bat 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath diagnostico.log -Append"
echo.
echo [INFO] Sesion terminada. Revisa diagnostico.log
pause
