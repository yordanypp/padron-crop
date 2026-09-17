@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

title PADRÓN CROP - Pipeline de Recorte Masivo

:: Detectar entorno virtual local o Python global
if exist ".venv\Scripts\python.exe" (
    set PY_CMD=.venv\Scripts\python.exe
    goto :PYTHON_OK
)
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

echo ============================================================
echo [ERROR] No se encontró Python en el sistema ni en .venv\
echo ============================================================
echo Por favor instale Python 3.10 o superior (marcando "Add to PATH").
pause
exit /b 1

:PYTHON_OK
set PYTHONPATH=src

:MENU
cls
echo =================================================================
echo      PADRÓN CROP - PANEL DE CONTROL Y PROCESAMIENTO MASIVO
echo =================================================================
echo.
echo  [1] Análisis Exploratorio (EDA) de Dataset (Volumen, Barras y ETA)
echo  [2] Procesamiento Masivo con Checkpoints y ETA en Vivo
echo  [3] Asistente Navicat (Procesar CSV / Blobs sin Contraseña)
echo  [4] Procesar Imagen de Muestra (Prototipo 0aaa2b82... JPG)
echo  [5] Abrir Galería Visual Interactiva (Auditoría QA Antes / Después)
echo  [6] Ejecutar Suite Completa de Pruebas (129 Tests Automatizados)
echo  [7] Iniciar Servidor Micro-API Local (Para Integraciones / Red)
echo  [8] Salir
echo.
set /p OPT="Seleccione una opción [1-8]: "

if "%OPT%"=="1" goto :RUN_EDA
if "%OPT%"=="2" goto :RUN_BATCH
if "%OPT%"=="3" goto :RUN_NAVICAT
if "%OPT%"=="4" goto :RUN_SAMPLE
if "%OPT%"=="5" goto :OPEN_GALLERY
if "%OPT%"=="6" goto :RUN_TESTS
if "%OPT%"=="7" goto :RUN_SERVER
if "%OPT%"=="8" exit /b 0

echo Opción no válida.
timeout /t 2 >nul
goto :MENU

:: -------------------------------------------------------------------
:: [1] ANÁLISIS EXPLORATORIO (EDA)
:: -------------------------------------------------------------------
:RUN_EDA
cls
echo =================================================================
echo      [1] ANÁLISIS EXPLORATORIO DE DATOS (EDA) PRE-FLIGHT
echo =================================================================
echo.
echo Ingrese la carpeta con las fotos (puede arrastrarla aquí):
set /p SRC_DIR="> "
set "SRC_DIR=!SRC_DIR:"=!"

if not exist "!SRC_DIR!" (
    echo.
    echo [ERROR] La carpeta especificada no existe: "!SRC_DIR!"
    pause
    goto :MENU
)

echo.
echo [INFO] Analizando dataset, resoluciones y patrones...
%PY_CMD% -m padron_crop eda --src "!SRC_DIR!" --sample 100
echo.
echo ¿Desea iniciar el procesamiento masivo sobre esta carpeta ahora?
set /p START_NOW="[S/N, default S]: "
if /i "!START_NOW!"=="N" goto :MENU
goto :DO_BATCH_FROM_EDA

:: -------------------------------------------------------------------
:: [2] PROCESAMIENTO MASIVO BATCH
:: -------------------------------------------------------------------
:RUN_BATCH
cls
echo =================================================================
echo      [2] PROCESAMIENTO MASIVO DE IMÁGENES CON CHECKPOINTS
echo =================================================================
echo.
echo Ingrese la carpeta de entrada con las fotos:
set /p SRC_DIR="> "
set "SRC_DIR=!SRC_DIR:"=!"

if not exist "!SRC_DIR!" (
    echo.
    echo [ERROR] La carpeta no existe: "!SRC_DIR!"
    pause
    goto :MENU
)

:DO_BATCH_FROM_EDA
echo.
echo Ingrese la carpeta de salida [Enter para 'out\lote_procesado']:
set /p OUT_DIR="> "
set "OUT_DIR=!OUT_DIR:"=!"
if "!OUT_DIR!"=="" set OUT_DIR=out\lote_procesado

set RESUME_FLAG=
if exist "!OUT_DIR!\state.jsonl" (
    echo.
    echo -----------------------------------------------------------------
    echo [AVISO] Se detectó un checkpoint de una ejecución previa en:
    echo "!OUT_DIR!\state.jsonl"
    echo ¿Desea reanudar desde donde se quedó (R) o empezar de cero (N)?
    set /p RES_CHOICE="[R/N, default R]: "
    if /i not "!RES_CHOICE!"=="N" set RESUME_FLAG=--resume
)

echo.
echo Configuración de procesamiento:
set /p WORKERS="Número de núcleos / workers en paralelo [Enter para 4]: "
if "!WORKERS!"=="" set WORKERS=4

set /p DESKEW_CHOICE="¿Corregir fotos inclinadas / torcidas? [S/N, default S]: "
set DESKEW_FLAG=--deskew
if /i "!DESKEW_CHOICE!"=="N" set DESKEW_FLAG=

set /p ASPECT_CHOICE="Formato de salida (1: Original, 2: Cédula 3:4, 3: Cuadrado 1:1) [Enter para 1]: "
set ASPECT_FLAG=
if "!ASPECT_CHOICE!"=="2" set ASPECT_FLAG=--aspect-ratio 3:4
if "!ASPECT_CHOICE!"=="3" set ASPECT_FLAG=--aspect-ratio 1:1

echo.
echo =================================================================
echo [INICIANDO PROCESO]
echo Carpeta origen : !SRC_DIR!
echo Carpeta salida : !OUT_DIR!
echo Workers        : !WORKERS!
echo =================================================================
echo.

%PY_CMD% -m padron_crop batch --src "!SRC_DIR!" --out "!OUT_DIR!" --workers !WORKERS! !RESUME_FLAG! !DESKEW_FLAG! !ASPECT_FLAG!

echo.
echo [INFO] Generando galería de auditoría visual interactiva...
%PY_CMD% -m padron_crop gallery --out "!OUT_DIR!"
if exist "!OUT_DIR!\gallery.html" (
    start "" "!OUT_DIR!\gallery.html"
)
echo.
echo [COMPLETADO] Proceso finalizado. Checkpoints guardados en "!OUT_DIR!\checkpoint.jsonl".
pause
goto :MENU

:: -------------------------------------------------------------------
:: [3] ASISTENTE NAVICAT
:: -------------------------------------------------------------------
:RUN_NAVICAT
cls
echo =================================================================
echo      [3] ASISTENTE DE EXTRACCIÓN Y RECORTE PARA NAVICAT
echo =================================================================
echo.
echo Este asistente procesa un archivo CSV exportado desde Navicat
echo (con fotos en Base64, Hexadecimal o rutas) SIN requerir contraseña.
echo.
echo Ingrese la ruta del archivo CSV exportado de Navicat:
set /p CSV_PATH="> "
set "CSV_PATH=!CSV_PATH:"=!"

if not exist "!CSV_PATH!" (
    echo.
    echo [ERROR] El archivo no existe: "!CSV_PATH!"
    pause
    goto :MENU
)

echo Ingrese la carpeta de salida [Enter para 'out\navicat_procesado']:
set /p OUT_DIR="> "
set "OUT_DIR=!OUT_DIR:"=!"
if "!OUT_DIR!"=="" set OUT_DIR=out\navicat_procesado

set /p COL_FOTO="Nombre de la columna de la FOTO en el CSV [Enter para 'foto']: "
if "!COL_FOTO!"=="" set COL_FOTO=foto

set /p COL_ID="Nombre de la columna del ID / Cédula [Enter para 'cedula']: "
if "!COL_ID!"=="" set COL_ID=cedula

echo.
echo [INFO] Procesando CSV de Navicat y decodificando imágenes...
%PY_CMD% tools\navicat_helper.py csv --csv "!CSV_PATH!" --out "!OUT_DIR!" --col "!COL_FOTO!" --id-col "!COL_ID!" --deskew

echo.
pause
goto :MENU

:: -------------------------------------------------------------------
:: [4] PROCESAR IMAGEN DE MUESTRA
:: -------------------------------------------------------------------
:RUN_SAMPLE
cls
echo =================================================================
echo      [4] PROCESAR IMAGEN DE MUESTRA / PROTOTIPO
echo =================================================================
echo.
echo [INFO] Procesando muestra '0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg'...
%PY_CMD% -m padron_crop crop --in 0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg --out out\prototipos\0aaa2b82_recortada.jpg --deskew

if %errorlevel% equ 0 (
    echo.
    echo [OK] Foto recortada con éxito en: out\prototipos\0aaa2b82_recortada.jpg
    echo [INFO] Generando galería visual...
    %PY_CMD% -m padron_crop gallery --out out\prototipos
    if exist "prototipos\05_visualizador_comparativo.html" (
        start "" "prototipos\05_visualizador_comparativo.html"
    ) else if exist "out\prototipos\gallery.html" (
        start "" "out\prototipos\gallery.html"
    )
) else (
    echo.
    echo [ERROR] Ocurrió un problema al procesar la muestra.
)
echo.
pause
goto :MENU

:: -------------------------------------------------------------------
:: [5] GALERÍA VISUAL INTERACTIVA
:: -------------------------------------------------------------------
:OPEN_GALLERY
cls
echo =================================================================
echo      [5] ABRIENDO GALERÍA VISUAL INTERACTIVA
echo =================================================================
echo.
if exist "prototipos\05_visualizador_comparativo.html" (
    echo Abriendo visualizador de prototipos...
    start "" "prototipos\05_visualizador_comparativo.html"
) else if exist "out\gallery.html" (
    start "" "out\gallery.html"
) else if exist "out\prototipos\gallery.html" (
    start "" "out\prototipos\gallery.html"
) else (
    echo [AVISO] No se encontró una galería previa. Generando...
    %PY_CMD% -m padron_crop gallery --out out\sample
    if exist "out\sample\gallery.html" start "" "out\sample\gallery.html"
)
goto :MENU

:: -------------------------------------------------------------------
:: [6] SUITE DE PRUEBAS
:: -------------------------------------------------------------------
:RUN_TESTS
cls
echo =================================================================
echo      [6] EJECUTANDO SUITE COMPLETA DE PRUEBAS AUTOMATIZADAS
echo =================================================================
echo.
%PY_CMD% -m pytest -v
echo.
echo =================================================================
pause
goto :MENU

:: -------------------------------------------------------------------
:: [7] SERVIDOR MICRO-API LOCAL
:: -------------------------------------------------------------------
:RUN_SERVER
cls
echo =================================================================
echo      [7] MICRO-SERVICIO API REST LOCAL (PUERTO 8000)
echo =================================================================
echo.
echo El servidor permite enviar fotos por HTTP desde Navicat o clientes remotos.
echo Rutas disponibles:
echo   - GET  http://localhost:8000/health
echo   - GET  http://localhost:8000/gallery
echo   - POST http://localhost:8000/crop  (Multipart file upload)
echo.
echo Presione Ctrl+C en cualquier momento para detener el servidor.
echo.
%PY_CMD% tools\serve_api.py --port 8000
pause
goto :MENU
