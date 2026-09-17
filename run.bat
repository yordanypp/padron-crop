@echo off
cd /d "%~dp0"
chcp 65001 >nul
setlocal EnableDelayedExpansion

title PADRÓN CROP - Panel de Control Automatizado (Windows 10 / 11)

:: =================================================================
:: 1. DETECCIÓN Y VALIDACIÓN DEL ENTORNO PYTHON
:: =================================================================
set PY_CMD=
if exist ".venv\Scripts\python.exe" (
    set PY_CMD=.venv\Scripts\python.exe
    goto :CHECK_DEPS
)
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :CHECK_DEPS
)
where py >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto :CHECK_DEPS
)

cls
echo =================================================================
echo  [ERROR] No se encontró Python en el sistema ni en .venv\
echo =================================================================
echo.
echo Para usar este programa en este servidor o PC se requiere Python.
echo 1. Descargue Python (3.10 o superior) desde: https://www.python.org
echo 2. IMPORTANTE: Marque la casilla "Add Python to PATH" al instalar.
echo.
pause
exit /b 1

:CHECK_DEPS
set PYTHONPATH=src

:: Verificar si las librerías necesarias están instaladas
%PY_CMD% -c "import numpy, PIL, cv2" >nul 2>&1
if %errorlevel% equ 0 goto :MENU

cls
echo =================================================================
echo  [AVISO] Primera ejecución detectada en este equipo
echo =================================================================
echo.
echo Se detectó que faltan las librerías necesarias: NumPy, Pillow, OpenCV
echo Podemos prepararlas automáticamente en 1 solo clic.
echo.
set /p DO_INST="¿Desea instalar las librerías automáticamente ahora? [S/N, default S]: "
if "!DO_INST!"=="" set DO_INST=S
if /i "!DO_INST!"=="S" (
    call instalar_servidor.bat
    exit /b 0
)

:: =================================================================
:: 2. MENÚ PRINCIPAL INTERACTIVO
:: =================================================================
:MENU
cls
echo =================================================================
echo      PADRÓN CROP - PANEL DE CONTROL Y PROCESAMIENTO MASIVO
echo =================================================================
echo.
echo  [1] 📊 Análisis Exploratorio (EDA) - Perfil de fotos, peso y tiempo estimado
echo  [2] ⚡ Procesamiento Masivo - Con checkpoints automáticos y ETA en vivo
echo  [3] 🗄️ Asistente Navicat / SQL - Procesar CSV exportado sin contraseñas
echo  [4] 🖼️ Probar Imagen de Muestra - Ver recorte de '0aaa2b82...jpg'
echo  [5] 🌐 Abrir Galería Visual - Auditoría interactiva antes y después
echo  [6] 🧪 Ejecutar Pruebas Automatizadas - Certificar 129 tests unitarios
echo  [7] 🔌 Iniciar Micro-API Local - Servidor HTTP en puerto 8000
echo  [0] 🔧 Reparar / Reinstalar Entorno - Recrear .venv y dependencias
echo  [8] ❌ Salir
echo.
echo =================================================================
set /p OPT="Seleccione una opción [0-8]: "

if "%OPT%"=="1" goto :RUN_EDA
if "%OPT%"=="2" goto :RUN_BATCH
if "%OPT%"=="3" goto :RUN_NAVICAT
if "%OPT%"=="4" goto :RUN_SAMPLE
if "%OPT%"=="5" goto :OPEN_GALLERY
if "%OPT%"=="6" goto :RUN_TESTS
if "%OPT%"=="7" goto :RUN_SERVER
if "%OPT%"=="0" goto :RUN_INSTALL
if "%OPT%"=="8" exit /b 0

echo Opción no válida.
timeout /t 2 >nul
goto :MENU

:: -------------------------------------------------------------------
:: [0] INSTALADOR AUTOMÁTICO
:: -------------------------------------------------------------------
:RUN_INSTALL
cls
call instalar_servidor.bat
goto :MENU

:: -------------------------------------------------------------------
:: [1] ANÁLISIS EXPLORATORIO DE DATOS (EDA)
:: -------------------------------------------------------------------
:RUN_EDA
cls
echo =================================================================
echo      [1] ANÁLISIS EXPLORATORIO DE DATOS (EDA) PRE-FLIGHT
echo =================================================================
echo.
echo Ingrese la carpeta donde están las fotos originales.
echo (Ejemplo: D:\Fotos_Padron o simplemente arrastre la carpeta aquí)
echo.
set /p SRC_DIR="Carpeta origen > "
set "SRC_DIR=!SRC_DIR:"=!"
if "!SRC_DIR:~-1!"=="\" if not "!SRC_DIR:~-2!"==":\" set "SRC_DIR=!SRC_DIR:~0,-1!"

if not exist "!SRC_DIR!" (
    echo.
    echo [ERROR] La carpeta especificada no existe: "!SRC_DIR!"
    pause
    goto :MENU
)

echo.
echo [INFO] Analizando imágenes, resoluciones, formato y tiempo estimado...
%PY_CMD% -m padron_crop eda --src "!SRC_DIR!" --sample 100
echo.
echo =================================================================
echo ¿Desea iniciar el procesamiento masivo sobre esta carpeta ahora mismo?
set /p START_NOW="Iniciar procesamiento? [S/N, default S]: "
if "!START_NOW!"=="" set START_NOW=S
if /i "!START_NOW!"=="S" goto :DO_BATCH_FROM_EDA
goto :MENU

:: -------------------------------------------------------------------
:: [2] PROCESAMIENTO MASIVO BATCH
:: -------------------------------------------------------------------
:RUN_BATCH
cls
echo =================================================================
echo      [2] PROCESAMIENTO MASIVO CON CHECKPOINTS Y ETA EN VIVO
echo =================================================================
echo.
echo Ingrese la carpeta donde están las fotos originales.
echo (Ejemplo: D:\Fotos_Padron o arrastre la carpeta a esta ventana)
echo.
set /p SRC_DIR="Carpeta origen > "
set "SRC_DIR=!SRC_DIR:"=!"
if "!SRC_DIR:~-1!"=="\" if not "!SRC_DIR:~-2!"==":\" set "SRC_DIR=!SRC_DIR:~0,-1!"

if not exist "!SRC_DIR!" (
    echo.
    echo [ERROR] La carpeta origen no existe: "!SRC_DIR!"
    pause
    goto :MENU
)

:DO_BATCH_FROM_EDA
echo.
echo Ingrese la carpeta de destino donde se guardarán las fotos limpias:
echo [Presione ENTER para usar: out\fotos_limpias]
set /p OUT_DIR="Carpeta destino > "
set "OUT_DIR=!OUT_DIR:"=!"
if "!OUT_DIR!"=="" set OUT_DIR=out\fotos_limpias
if "!OUT_DIR:~-1!"=="\" if not "!OUT_DIR:~-2!"==":\" set "OUT_DIR=!OUT_DIR:~0,-1!"

set RESUME_FLAG=
if exist "!OUT_DIR!\state.jsonl" (
    echo.
    echo -----------------------------------------------------------------
    echo [CHECKPOINT DETECTADO] Se encontró un progreso previo en:
    echo   !OUT_DIR!\state.jsonl
    echo ¿Desea reanudar desde donde se quedó (R) o empezar de cero (N)?
    set /p RES_CHOICE="[R/N, default R]: "
    if "!RES_CHOICE!"=="" set RES_CHOICE=R
    if /i not "!RES_CHOICE!"=="N" set RESUME_FLAG=--resume
)

echo.
echo Configuración de procesamiento:
echo.
echo 1. Cantidad de núcleos de CPU para procesar en paralelo:
echo    [Recomendado: 4 u 8. Presione ENTER para usar 4 núcleos]
set /p WORKERS="Workers [4]: "
if "!WORKERS!"=="" set WORKERS=4

echo.
echo 2. Corrección de fotos inclinadas o escaneadas torcidas (Deskew):
echo    [Presione ENTER para SÍ (Recomendado)]
set /p DESKEW_CHOICE="¿Enderezar fotos? [S/N, default S]: "
if "!DESKEW_CHOICE!"=="" set DESKEW_CHOICE=S
set DESKEW_FLAG=--deskew
if /i "!DESKEW_CHOICE!"=="N" set DESKEW_FLAG=

echo.
echo 3. Formato de proporción del recorte final:
echo    [1] Mantener recorte limpio original (Recomendado)
echo    [2] Cédula / Retrato 3:4 (Centrado automáticamente en el rostro)
echo    [3] Cuadrado 1:1 (Ideal para avatares y credenciales)
set /p ASPECT_CHOICE="Seleccione formato [1-3, default 1]: "
set ASPECT_FLAG=
if "!ASPECT_CHOICE!"=="2" set ASPECT_FLAG=--aspect-ratio 3:4
if "!ASPECT_CHOICE!"=="3" set ASPECT_FLAG=--aspect-ratio 1:1

echo.
echo =================================================================
echo [INICIANDO PROCESAMIENTO DETERMINISTA]
echo - Carpeta origen  : "!SRC_DIR!"
echo - Carpeta destino : "!OUT_DIR!"
echo - Núcleos (CPU)   : !WORKERS! workers
echo - Estado          : Ejecutando... (Presione Ctrl+C si desea pausar)
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
echo =================================================================
echo  ¡LOTE COMPLETADO! Checkpoints guardados en "!OUT_DIR!".
echo =================================================================
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
echo Instrucciones:
echo 1. En Navicat, haga clic derecho en la tabla y elija:
echo    "Export Wizard" -^> formato "CSV".
echo 2. El CSV puede contener fotos en Base64, Hexadecimal o rutas.
echo.
echo Ingrese la ruta del archivo CSV exportado:
echo (Ejemplo: C:\export_padron.csv o arrastre el archivo aquí)
set /p CSV_PATH="Archivo CSV > "
set "CSV_PATH=!CSV_PATH:"=!"

if not exist "!CSV_PATH!" (
    echo.
    echo [ERROR] El archivo no existe: "!CSV_PATH!"
    pause
    goto :MENU
)

echo.
echo Ingrese la carpeta donde se guardarán las fotos extraídas y recortadas:
echo [Presione ENTER para usar: out\navicat_procesado]
set /p OUT_DIR="Carpeta destino > "
set "OUT_DIR=!OUT_DIR:"=!"
if "!OUT_DIR!"=="" set OUT_DIR=out\navicat_procesado
if "!OUT_DIR:~-1!"=="\" if not "!OUT_DIR:~-2!"==":\" set "OUT_DIR=!OUT_DIR:~0,-1!"

echo.
echo Ingrese el nombre de la columna que contiene la foto en el CSV:
echo [Presione ENTER para usar 'foto']:
set /p COL_FOTO="Columna foto [foto]: "
if "!COL_FOTO!"=="" set COL_FOTO=foto

echo.
echo Ingrese el nombre de la columna para nombrar cada archivo (ID o Cédula):
echo [Presione ENTER para usar 'cedula']:
set /p COL_ID="Columna ID [cedula]: "
if "!COL_ID!"=="" set COL_ID=cedula

echo.
echo =================================================================
echo [INFO] Procesando CSV de Navicat y recortando imágenes...
echo =================================================================
%PY_CMD% tools\navicat_helper.py csv --csv "!CSV_PATH!" --out "!OUT_DIR!" --col "!COL_FOTO!" --id-col "!COL_ID!" --deskew

if exist "!OUT_DIR!\gallery.html" (
    start "" "!OUT_DIR!\gallery.html"
)
echo.
echo [COMPLETADO] Proceso de Navicat finalizado.
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
echo [INFO] Procesando muestra real '0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg'...
%PY_CMD% -m padron_crop crop --in 0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg --out out\prototipos\0aaa2b82_recortada.jpg --deskew

if %errorlevel% equ 0 (
    echo.
    echo [OK] Foto recortada con éxito en: out\prototipos\0aaa2b82_recortada.jpg
    echo [INFO] Abriendo comparador visual interactivo...
    if exist "prototipos\05_visualizador_comparativo.html" (
        start "" "prototipos\05_visualizador_comparativo.html"
    ) else (
        %PY_CMD% -m padron_crop gallery --out out\prototipos
        if exist "out\prototipos\gallery.html" start "" "out\prototipos\gallery.html"
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
    echo Abriendo comparador de prototipos...
    start "" "prototipos\05_visualizador_comparativo.html"
) else if exist "out\fotos_limpias\gallery.html" (
    echo Abriendo galería de fotos limpias...
    start "" "out\fotos_limpias\gallery.html"
) else if exist "out\gallery.html" (
    echo Abriendo galería general...
    start "" "out\gallery.html"
) else if exist "out\prototipos\gallery.html" (
    start "" "out\prototipos\gallery.html"
) else (
    echo [AVISO] Generando galería a partir de los últimos resultados...
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
echo Ejecutando 129 pruebas unitarias de regresión y seguridad...
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
echo Endpoints disponibles:
echo   - GET  http://localhost:8000/health
echo   - GET  http://localhost:8000/gallery
echo   - POST http://localhost:8000/crop      (Envío de imagen raw)
echo   - POST http://localhost:8000/crop/json (Envío en Base64 con JSON)
echo.
echo Presione Ctrl+C en cualquier momento para detener el servidor.
echo.
%PY_CMD% tools\serve_api.py --port 8000
pause
goto :MENU
