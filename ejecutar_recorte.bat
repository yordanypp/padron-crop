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
set "DO_INST=S"
set /p DO_INST="Desea instalar las librerias automaticamente ahora? [S/N, default S]: "
if "!DO_INST!"=="" set DO_INST=S
if /i not "!DO_INST!"=="S" goto :MENU
call instalar_servidor.bat
exit /b 0

:: =================================================================
:: 2. MENÚ PRINCIPAL INTERACTIVO
:: =================================================================
:MENU
cls
echo =================================================================
echo      PADRÓN CROP - PANEL DE CONTROL Y PROCESAMIENTO MASIVO
echo =================================================================
echo.
echo  [1] Análisis Exploratorio (EDA) - Perfil de fotos, peso y tiempo estimado
echo  [2] Procesamiento Masivo - Con checkpoints automáticos y ETA en vivo
echo  [3] Asistente Navicat / SQL - Procesar CSV o carpeta sin contraseñas
echo  [4] Probar Imagen de Muestra - Ver recorte de '0aaa2b82...jpg'
echo  [5] Abrir Galería Visual - Auditoría interactiva antes y después
echo  [6] Ejecutar Pruebas Automatizadas - Certificar tests unitarios
echo  [7] Iniciar Micro-API Local - Servidor HTTP en puerto 8000
echo  [8] Probar Variantes de Estrés - 50 fotos: PRM arriba, lados, marcos
echo  [0] Reparar / Reinstalar Entorno - Recrear .venv y dependencias
echo  [9] Prueba 300 Fotos Sinteticas - Genera lote y lo procesa end-to-end
echo  [X] Salir
echo.
echo  Si algo falla alla: avisa aqui, se arregla, y en el remoto abres
echo  actualizar_y_seguir.bat (trae el arreglo y sigue solo).
echo.
echo =================================================================
set "OPT="
set /p OPT="Seleccione una opción [0-9, X]: "

if "%OPT%"=="1" goto :RUN_EDA
if "%OPT%"=="2" goto :RUN_BATCH
if "%OPT%"=="3" goto :RUN_NAVICAT
if "%OPT%"=="4" goto :RUN_SAMPLE
if "%OPT%"=="5" goto :OPEN_GALLERY
if "%OPT%"=="6" goto :RUN_TESTS
if "%OPT%"=="7" goto :RUN_SERVER
if "%OPT%"=="8" goto :RUN_VARIANTS
if "%OPT%"=="0" goto :RUN_INSTALL
if "%OPT%"=="9" goto :RUN_LOTE300
if /i "%OPT%"=="X" exit /b 0

:: Si no hay entrada disponible (EOF / consola cerrada) salir limpiamente
if "!OPT!"=="" (
    echo.
    echo [INFO] Sesión finalizada.
    exit /b 0
)

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
set "SRC_DIR="
set /p SRC_DIR="Carpeta origen > "
if "!SRC_DIR!"=="" (
    echo.
    echo [ERROR] No ingresó ninguna ruta.
    pause
    goto :MENU
)
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
echo Desea iniciar el procesamiento masivo sobre esta carpeta ahora mismo?
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
set "SRC_DIR="
set /p SRC_DIR="Carpeta origen > "
if "!SRC_DIR!"=="" (
    echo.
    echo [ERROR] No ingresó ninguna ruta.
    pause
    goto :MENU
)
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
set "OUT_DIR="
set /p OUT_DIR="Carpeta destino > "
if "!OUT_DIR!"=="" set OUT_DIR=out\fotos_limpias
set "OUT_DIR=!OUT_DIR:"=!"
if "!OUT_DIR:~-1!"=="\" if not "!OUT_DIR:~-2!"==":\" set "OUT_DIR=!OUT_DIR:~0,-1!"

set RESUME_FLAG=
if not exist "!OUT_DIR!\state.jsonl" goto :NO_CHECKPOINT_FOUND
echo.
echo -----------------------------------------------------------------
echo [CHECKPOINT DETECTADO] Se encontró progreso previo en:
echo   !OUT_DIR!\state.jsonl
echo Desea reanudar desde donde se quedó [R] o empezar de cero [N]?
set /p RES_CHOICE="[R/N, default R]: "
if "!RES_CHOICE!"=="" set RES_CHOICE=R
if /i not "!RES_CHOICE!"=="N" set RESUME_FLAG=--resume
:NO_CHECKPOINT_FOUND

set WORKERS=0
set DESKEW_FLAG=--deskew
set ASPECT_FLAG=

echo.
echo Presione ENTER para iniciar ya con configuración AUTOMATICA:
echo (detecta nucleos y RAM de ESTA maquina, enderezado inteligente, maxima calidad)
echo O escriba 'A' para configuración avanzada:
set /p ADV_OPT="[ENTER = Iniciar Ya / A = Avanzado]: "
if /i not "!ADV_OPT!"=="A" goto :SKIP_ADV_SETTINGS

echo.
echo 1. Cantidad de núcleos de CPU para procesar en paralelo [0=AUTO]:
set /p WORKERS="Workers [0]: "
if "!WORKERS!"=="" set WORKERS=0

echo.
echo 2. Corrección de fotos inclinadas (Deskew):
set /p DESKEW_CHOICE="Enderezar fotos? [S/N, default S]: "
if "!DESKEW_CHOICE!"=="" set DESKEW_CHOICE=S
if /i "!DESKEW_CHOICE!"=="N" set DESKEW_FLAG=

echo.
echo 3. Formato de proporción del recorte final:
echo    [1] Mantener recorte limpio original (Recomendado)
echo    [2] Cédula / Retrato 3:4 (Centrado en el rostro)
echo    [3] Cuadrado 1:1 (Para avatares y credenciales)
set /p ASPECT_CHOICE="Seleccione formato [1-3, default 1]: "
if "!ASPECT_CHOICE!"=="2" set ASPECT_FLAG=--aspect-ratio 3:4
if "!ASPECT_CHOICE!"=="3" set ASPECT_FLAG=--aspect-ratio 1:1

:SKIP_ADV_SETTINGS

echo.
echo =================================================================
echo [INICIANDO PROCESAMIENTO DETERMINISTA]
echo - Carpeta origen  : "!SRC_DIR!"
echo - Carpeta destino : "!OUT_DIR!"
if "!WORKERS!"=="0" (
    echo - Nucleos (CPU)   : AUTO segun esta maquina
) else (
    echo - Nucleos (CPU)   : !WORKERS! workers
)
echo - Estado          : Ejecutando... (Presione Ctrl+C si desea pausar)
echo =================================================================
echo.

%PY_CMD% -m padron_crop batch --src "!SRC_DIR!" --out "!OUT_DIR!" --workers !WORKERS! !RESUME_FLAG! !DESKEW_FLAG! !ASPECT_FLAG!

echo.
echo [INFO] Generando galería de auditoría visual interactiva...
%PY_CMD% -m padron_crop gallery --out "!OUT_DIR!"
if exist "!OUT_DIR!\gallery.html" start "" "!OUT_DIR!\gallery.html"
echo.
echo =================================================================
echo  ¡LOTE COMPLETADO! Checkpoints guardados en "!OUT_DIR!".
echo =================================================================
pause
goto :MENU

:: -------------------------------------------------------------------
:: [3] ASISTENTE NAVICAT / SQL
:: -------------------------------------------------------------------
:RUN_NAVICAT
cls
echo =================================================================
echo      [3] ASISTENTE DE EXTRACCIÓN Y RECORTE PARA NAVICAT / SQL
echo =================================================================
echo.
echo Instrucciones:
echo 1. Puede arrastrar un archivo CSV exportado desde Navicat.
echo 2. O puede arrastrar una CARPETA con fotos exportadas de Navicat.
echo.
echo Ingrese la ruta del archivo CSV o carpeta con fotos:
echo (Ejemplo: C:\export_padron.csv o arrastre el archivo/carpeta aquí)
set "CSV_PATH="
set /p CSV_PATH="Ruta CSV o Carpeta > "
if "!CSV_PATH!"=="" (
    echo.
    echo [ERROR] No ingresó ninguna ruta.
    pause
    goto :MENU
)
set "CSV_PATH=!CSV_PATH:"=!"
if "!CSV_PATH:~-1!"=="\" if not "!CSV_PATH:~-2!"==":\" set "CSV_PATH=!CSV_PATH:~0,-1!"

if not exist "!CSV_PATH!" (
    echo.
    echo [ERROR] La ruta especificada no existe: "!CSV_PATH!"
    pause
    goto :MENU
)

:: Si ingresó una carpeta de imágenes en lugar de un CSV, procesar directamente
if not exist "!CSV_PATH!\*" goto :PROCESS_AS_FILE
dir /b "!CSV_PATH!\*.csv" >nul 2>&1
if not errorlevel 1 goto :PROCESS_AS_FILE
echo.
echo [INFO] Detectada una CARPETA con imágenes directas (no CSV).
echo [INFO] Redirigiendo automáticamente a Procesamiento Masivo...
set "SRC_DIR=!CSV_PATH!"
goto :DO_BATCH_FROM_EDA

:PROCESS_AS_FILE
echo.
echo Ingrese la carpeta donde se guardarán las fotos recortadas:
echo [Presione ENTER para usar: out\navicat_procesado]
set "OUT_DIR="
set /p OUT_DIR="Carpeta destino > "
if "!OUT_DIR!"=="" set OUT_DIR=out\navicat_procesado
set "OUT_DIR=!OUT_DIR:"=!"
if "!OUT_DIR:~-1!"=="\" if not "!OUT_DIR:~-2!"==":\" set "OUT_DIR=!OUT_DIR:~0,-1!"

echo.
echo Columna con la foto en el CSV [ENTER=foto]:
set "COL_FOTO="
set /p COL_FOTO="Columna foto > "
if "!COL_FOTO!"=="" set COL_FOTO=foto
echo.
echo Columna ID para nombrar la entrega (cedula, id, codigo...) [ENTER=cedula]:
set "COL_ID="
set /p COL_ID="Columna ID > "
if "!COL_ID!"=="" set COL_ID=cedula

echo.
echo =================================================================
echo [INFO] Procesando con Navicat Helper...
echo - Entrada : "!CSV_PATH!"
echo - Destino : "!OUT_DIR!"
echo =================================================================
echo.

%PY_CMD% tools\navicat_helper.py csv --csv "!CSV_PATH!" --out "!OUT_DIR!" --col "!COL_FOTO!" --id-col "!COL_ID!" --deskew
if errorlevel 1 (
    echo.
    echo [AVISO] Se detectó una advertencia durante el proceso de Navicat.
)

if exist "!OUT_DIR!\gallery.html" start "" "!OUT_DIR!\gallery.html"
echo.
echo =================================================================
echo [COMPLETADO] Proceso de Navicat finalizado con éxito.
echo =================================================================
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

if %errorlevel% neq 0 goto :SAMPLE_ERROR
echo.
echo [OK] Foto recortada con éxito en: out\prototipos\0aaa2b82_recortada.jpg
echo [INFO] Abriendo comparador visual interactivo...
if exist "prototipos\05_visualizador_comparativo.html" (
    start "" "prototipos\05_visualizador_comparativo.html"
    goto :SAMPLE_DONE
)
%PY_CMD% -m padron_crop gallery --out out\prototipos
if exist "out\prototipos\gallery.html" start "" "out\prototipos\gallery.html"
goto :SAMPLE_DONE

:SAMPLE_ERROR
echo.
echo [ERROR] Ocurrió un problema al procesar la muestra.

:SAMPLE_DONE
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
    start "" "prototipos\05_visualizador_comparativo.html"
    goto :MENU
)
if exist "out\fotos_limpias\gallery.html" (
    start "" "out\fotos_limpias\gallery.html"
    goto :MENU
)
if exist "out\navicat_procesado\gallery.html" (
    start "" "out\navicat_procesado\gallery.html"
    goto :MENU
)
if exist "pruebas_variantes\00_visualizador_antes_despues.html" (
    start "" "pruebas_variantes\00_visualizador_antes_despues.html"
    goto :MENU
)
if exist "out\gallery.html" (
    start "" "out\gallery.html"
    goto :MENU
)
echo [AVISO] Generando galería a partir de los últimos resultados...
%PY_CMD% -m padron_crop gallery --out out\sample
if exist "out\sample\gallery.html" start "" "out\sample\gallery.html"
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

:: -------------------------------------------------------------------
:: [8] VARIANTES DE ESTRÉS (PRM EN DISTINTAS POSICIONES)
:: -------------------------------------------------------------------
:RUN_VARIANTS
cls
echo =================================================================
echo      [8] BANCO DE VARIANTES DE ESTRÉS (50 FOTOS)
echo =================================================================
echo.
echo Este test toma la foto real del padrón y le genera 50 variantes:
echo   - PRM arriba (izq, centro, der)
echo   - PRM abajo (izq, centro, der, fino, grueso)
echo   - PRM lateral (izq, der) y marcos perimetrales
echo   - Controles limpios sin PRM
echo.
echo Desea regenerar las 50 fotos y procesarlas ahora mismo?
set /p DO_VAR="Ejecutar prueba de variantes? [S/N, default S]: "
if "!DO_VAR!"=="" set DO_VAR=S
if /i not "!DO_VAR!"=="S" goto :MENU

echo.
echo [1/3] Generando banco de fotos variantes en: pruebas_variantes\antes...
%PY_CMD% tools\generar_variantes_estres.py

echo.
echo [2/3] Procesando variantes con el motor actual (padron_crop batch)...
%PY_CMD% -m padron_crop batch --src pruebas_variantes\antes --out pruebas_variantes\despues --workers 0

echo.
echo [3/3] Generando comparador visual antes/después...
%PY_CMD% tools\generar_galeria_variantes.py

echo.
echo =================================================================
echo [EXITO] Prueba completada. Abriendo comparador visual en el navegador...
if exist "pruebas_variantes\00_visualizador_antes_despues.html" (
    start "" "pruebas_variantes\00_visualizador_antes_despues.html"
)
pause
goto :MENU

:: -------------------------------------------------------------------
:: [9] PRUEBA DE 300 FOTOS SINTÉTICAS (ensayo general del remoto)
:: -------------------------------------------------------------------
:RUN_LOTE300
cls
echo =================================================================
echo      [9] PRUEBA DE 300 FOTOS SINTETICAS (ensayo del remoto)
echo =================================================================
echo.
echo Genera 300 fotos realistas desde la foto real del padron
echo (clones + variantes PRM + casos corruptos) y las procesa
echo end-to-end con workers AUTOMATICOS de ESTA maquina.
echo.
echo Desea ejecutar la prueba de 300 fotos ahora mismo?
set /p DO_LOTE="Ejecutar prueba? [S/N, default S]: "
if "!DO_LOTE!"=="" set DO_LOTE=S
if /i not "!DO_LOTE!"=="S" goto :MENU

echo.
echo [1/3] Generando lote de 300 fotos en: pruebas_variantes\lote300...
if exist "pruebas_variantes\lote300" rmdir /s /q "pruebas_variantes\lote300"
%PY_CMD% tools\make_lot.py --out pruebas_variantes\lote300 --n 300 --seed 7
if errorlevel 1 (
    echo [ERROR] No se pudo generar el lote de prueba.
    pause
    goto :MENU
)

echo.
echo [2/3] Procesando lote con workers AUTOMATICOS (padron_crop batch)...
if exist "out\lote300_limpias" rmdir /s /q "out\lote300_limpias"
%PY_CMD% -m padron_crop batch --src pruebas_variantes\lote300 --out out\lote300_limpias --workers 0

echo.
echo [3/3] Generando galeria de auditoria...
%PY_CMD% -m padron_crop gallery --out out\lote300_limpias
if exist "out\lote300_limpias\gallery.html" start "" "out\lote300_limpias\gallery.html"
echo.
echo [INFO] Entrega ordenada en: out\lote300_limpias\entrega\
echo [INFO] Control para Excel/Navicat: out\lote300_limpias\manifest_import.csv
pause
goto :MENU
