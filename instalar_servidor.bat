@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

title INSTALADOR AUTOMÁTICO - PADRÓN CROP (WINDOWS 10 / 11)

echo =================================================================
echo       PADRÓN CROP - INSTALADOR DE ENTORNO EN 1 SOLO CLIC
echo =================================================================
echo.
echo Este asistente preparará el entorno virtual local (.venv)
echo e instalará todas las librerías necesarias (NumPy, Pillow, OpenCV).
echo.

:: 1. Detectar Python del sistema
set PYTHON_BIN=
where python >nul 2>&1
if %errorlevel% equ 0 set PYTHON_BIN=python
if not defined PYTHON_BIN (
    where py >nul 2>&1
    if %errorlevel% equ 0 set PYTHON_BIN=py
)

if not defined PYTHON_BIN (
    echo [ERROR CRÍTICO] No se encontró Python en el sistema.
    echo.
    echo Por favor descargue e instale Python desde:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: Durante la instalación marque la casilla:
    echo   [x] "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

echo [1/4] Python detectado en el sistema:
%PYTHON_BIN% --version
echo.

:: 2. Crear entorno virtual si no existe
echo [2/4] Creando entorno virtual local (.venv)...
if not exist ".venv\Scripts\python.exe" (
    %PYTHON_BIN% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo       Entorno virtual .venv creado con éxito.
) else (
    echo       Entorno virtual .venv ya existe. Omitiendo creación.
)
echo.

:: 3. Actualizar pip e instalar dependencias
echo [3/4] Instalando librerías requeridas y registrando paquete (pip install -e .)...
echo       Esto puede tomar 1 o 2 minutos la primera vez...
.venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
.venv\Scripts\python.exe -m pip install -r requirements.txt pytest -e .
if %errorlevel% neq 0 (
    echo [ADVERTENCIA] Ocurrió un detalle al instalar las librerías.
)
echo.

:: 4. Verificación rápida del motor
echo [4/4] Verificando motor de visión y geometría...
set PYTHONPATH=src
.venv\Scripts\python.exe -c "import numpy, PIL, cv2; from padron_crop import crop, opencv_ext; print('      [OK] Motor verificado. OpenCV:', opencv_ext.is_opencv_available())"
if %errorlevel% neq 0 (
    echo [ERROR] Falló la verificación de las librerías.
    pause
    exit /b 1
)
echo.

echo =================================================================
echo        ¡INSTALACIÓN COMPLETADA EXITOSAMENTE!
echo =================================================================
echo El sistema está 100%% listo para procesar fotos masivas.
echo.
echo A continuación se abrirá el panel interactivo de procesamiento.
echo.
pause
start ejecutar_recorte.bat
exit /b 0
