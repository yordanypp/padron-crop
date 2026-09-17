#!/usr/bin/env bash
# ============================================================
#      PADRÓN CROP - Linux / Remote Server Runner
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=src

PY_CMD=""
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    echo "[ERROR] Python 3.10+ is required but was not found in PATH." >&2
    exit 1
fi

echo "============================================================"
echo "      PADRÓN CROP - PIPELINE DE RECORTE AUTOMATIZADO"
echo "============================================================"
echo "Python binary: $($PY_CMD --version)"
echo ""

case "${1:-menu}" in
    eda)
        if [ $# -lt 2 ]; then
            echo "Usage: ./run.sh eda <src_dir> [sample_size]"
            exit 1
        fi
        SRC="$2"
        SAMPLE="${3:-100}"
        echo "[INFO] Running Exploratory Data Analysis on $SRC (sample: $SAMPLE)..."
        $PY_CMD -m padron_crop eda --src "$SRC" --sample "$SAMPLE"
        ;;
    sample)
        echo "[INFO] Processing sample prototype..."
        $PY_CMD -m padron_crop crop --in 0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg --out out/prototipos/0aaa2b82_recortada.jpg --deskew
        $PY_CMD -m padron_crop gallery --out out/prototipos
        echo "[OK] Result saved to out/prototipos/0aaa2b82_recortada.jpg"
        ;;
    batch)
        if [ $# -lt 3 ]; then
            echo "Usage: ./run.sh batch <src_dir> <out_dir> [workers]"
            exit 1
        fi
        SRC="$2"
        OUT="$3"
        WORKERS="${4:-4}"
        echo "[INFO] Starting batch processing on $SRC -> $OUT with $WORKERS workers..."
        $PY_CMD -m padron_crop batch --src "$SRC" --out "$OUT" --workers "$WORKERS" --resume --deskew
        $PY_CMD -m padron_crop gallery --out "$OUT"
        ;;
    test)
        echo "[INFO] Running full test suite..."
        $PY_CMD -m pytest -v
        ;;
    server)
        echo "[INFO] Launching remote micro-API..."
        $PY_CMD tools/serve_api.py
        ;;
    gallery)
        TARGET="${2:-out/prototipos}"
        echo "[INFO] Generating HTML gallery for $TARGET..."
        $PY_CMD -m padron_crop gallery --out "$TARGET"
        ;;
    *)
        echo "Comandos disponibles:"
        echo "  ./run.sh sample                      Procesa la imagen de muestra"
        echo "  ./run.sh batch <src> <out> [workers] Procesa una carpeta recursivamente"
        echo "  ./run.sh test                        Ejecuta los 109 tests automatizados"
        echo "  ./run.sh server                      Inicia el micro-servicio HTTP API"
        echo "  ./run.sh gallery [out_dir]           Genera la galería visual HTML"
        ;;
esac
