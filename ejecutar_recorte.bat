@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

title PADRÓN CROP - Pipeline de Recorte Masivo

echo ============================================================
echo      PADRÓN CROP - PIPELINE DE RECORTE AUTOMATIZADO
echo ============================================================
echo.

:: Detectar Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :PYTHON_OK
)
where py >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto :PYTHON_OK
)

echo [ERROR] No se encontró Python instalado en el sistema.
echo Por favor instale Python 3.10 o superior y marque "Add to PATH".
pause
exit /b 1

:PYTHON_OK
set PYTHONPATH=src

:MENU
cls
echo ============================================================
echo      PADRÓN CROP - PANEL DE CONTROL Y PROCESAMIENTO
echo ============================================================
echo.
echo  [1] Procesar Imagen de Muestra (Prototipo 0aaa2b82... JPG)
echo  [2] Procesar Carpeta Masiva de Fotos (Batch local / disco)
echo  [3] Abrir Galería Visual Interactiva (Ver Antes / Después)
echo  [4] Ejecutar Suite de Pruebas (109 Tests Automatizados)
echo  [5] Iniciar Servidor Micro-API Local (Para servidor remoto / Navicat)
echo  [6] Salir
echo.
set /p OPT="Seleccione una opción [1-6]: "

if "%OPT%"=="1" goto :RUN_SAMPLE
if "%OPT%"=="2" goto :RUN_BATCH
if "%OPT%"=="3" goto :OPEN_GALLERY
if "%OPT%"=="4" goto :RUN_TESTS
if "%OPT%"=="5" goto :RUN_SERVER
if "%OPT%"=="6" exit /b 0

echo Opción no válida.
pause
goto :MENU

:RUN_SAMPLE
echo.
echo [INFO] Procesando imagen de muestra con detección y Face Safety Gate...
%PY_CMD% -m padron_crop crop --in 0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg --out out\prototipos\0aaa2b82_recortada.jpg --deskew
if %errorlevel% equ 0 (
    echo.
    echo [OK] Foto recortada con éxito en: out\prototipos\0aaa2b82_recortada.jpg
    echo [INFO] Generando galería visual...
    %PY_CMD% -m padron_crop gallery --out out\prototipos
    if exist "out\prototipos\gallery.html" (
        start out\prototipos\gallery.html
    )
) else (
    echo [ERROR] Ocurrió un problema al procesar la muestra.
)
echo.
pause
goto :MENU

:RUN_BATCH
echo.
set /p SRC_DIR="Ingrese la ruta de la carpeta con las fotos originales: "
if not exist "!SRC_DIR!" (
    echo [ERROR] La carpeta especificada no existe.
    pause
    goto :MENU
)
set /p OUT_DIR="Ingrese la carpeta de destino [Enter para 'out\lote_procesado']: "
if "!OUT_DIR!"=="" set OUT_DIR=out\lote_procesado
set /p WORKERS="Número de núcleos / workers en paralelo [Enter para 4]: "
if "!WORKERS!"=="" set WORKERS=4

echo.
echo [INFO] Iniciando procesamiento masivo con !WORKERS! workers...
%PY_CMD% -m padron_crop batch --src "!SRC_DIR!" --out "!OUT_DIR!" --workers !WORKERS! --resume --deskew
echo.
echo [INFO] Generando galería de auditoría visual...
%PY_CMD% -m padron_crop gallery --out "!OUT_DIR!"
if exist "!OUT_DIR!\gallery.html" (
    start "!OUT_DIR!\gallery.html"
)
pause
goto :MENU

:OPEN_GALLERY
echo.
if exist "out\prototipos\gallery.html" (
    start out\prototipos\gallery.html
) else if exist "out\sample\gallery.html" (
    start out\sample\gallery.html
) else (
    echo [AVISO] Generando galería de prototipos...
    %PY_CMD% -m padron_crop gallery --out out\sample
    start out\sample\gallery.html
)
goto :MENU

:RUN_TESTS
echo.
echo [INFO] Ejecutando batería completa de pruebas pytest...
%PY_CMD% -m pytest -v
echo.
pause
goto :MENU

:RUN_SERVER
echo.
echo [INFO] Iniciando micro-servicio API para recibir/servir fotos remotas...
echo [INFO] Presione Ctrl+C para detener el servicio.
%PY_CMD% tools\serve_api.py
pause
goto :MENU
