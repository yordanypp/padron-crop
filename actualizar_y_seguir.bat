@echo off
cd /d "%~dp0"
chcp 65001 >nul
setlocal EnableDelayedExpansion
title PADRON CROP - Actualizar y seguir

set PY_CMD=
if exist ".venv\Scripts\python.exe" (
    set PY_CMD=.venv\Scripts\python.exe
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 ( set PY_CMD=python ) else ( set PY_CMD=py )
)
set PYTHONPATH=src

cls
echo =================================================================
echo      ACTUALIZAR CODIGO Y SEGUIR DESDE EL CHECKPOINT
echo =================================================================
echo.
echo 1. Trae los arreglos de GitHub (git pull) - no toca tus fotos.
echo 2. Sigue el lote donde se quedo (--resume, workers AUTO).
echo.
echo Carpeta destino del lote [ENTER = out\fotos_limpias]:
set "OUT_DIR="
set /p OUT_DIR="Carpeta destino > "
if "!OUT_DIR!"=="" set OUT_DIR=out\fotos_limpias
set "OUT_DIR=!OUT_DIR:"=!"

%PY_CMD% tools\remote_sync.py --out "!OUT_DIR!"
echo.
pause
