"""Flujo remoto: actualiza el codigo y sigue donde iba.

Uso (en el servidor, 1 comando):
    python tools/remote_sync.py --out out/fotos_limpias

Hace, en orden:
1. `git pull origin main` (trae el arreglo hecho aqui; no toca tus fotos
   ni tu progreso: todo lo generado esta en .gitignore).
2. Lee src/out del checkpoint.jsonl de esa carpeta destino.
3. Reanuda el lote con workers AUTOMATICOS (`--resume`, workers=0).

Si no hay git o no hay red, salta el pull y reanuda igual.
Si no hay checkpoint, procesa desde cero con autotune.
Jamas borra ni modifica fotos originales (solo lectura).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def git_pull(repo: Path) -> str:
    """Trae los arreglos. Devuelve mensaje corto; nunca lanza excepcion."""
    try:
        r = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=repo, capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip().splitlines()
        tail = out[-1] if out else "sin salida"
        return f"git pull RC={r.returncode}: {tail[:120]}"
    except FileNotFoundError:
        return "git no instalado: salto actualizacion, sigo con el codigo local"
    except Exception as e:  # sin red, timeout, etc: el resume igual sigue
        return f"pull omitido ({type(e).__name__}): sigo con el codigo local"


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Actualiza y sigue desde checkpoint")
    ap.add_argument("--out", required=True, help="carpeta destino del lote")
    ap.add_argument("--no-pull", action="store_true", help="omitir git pull")
    ap.add_argument("--workers", type=int, default=0,
                    help="0=automatico segun la maquina")
    args = ap.parse_args(argv)

    out = Path(args.out)
    print(f"[1/2] Actualizando codigo desde GitHub...")
    if args.no_pull:
        print("      pull omitido por --no-pull")
    else:
        print(f"      {git_pull(ROOT)}")

    src = None
    ckpt = out / "checkpoint.jsonl"
    if ckpt.exists():
        try:
            data = json.loads(ckpt.read_text(encoding="utf-8"))
            src = data.get("src")
            done = data.get("total_completed", 0)
            print(f"[2/2] Checkpoint: {done} imagenes ya listas. Reanudando...")
        except (json.JSONDecodeError, OSError):
            print("[2/2] Checkpoint ilegible: empiezo desde cero (sin duplicar).")
    if not src:
        print("[ERROR] Sin checkpoint ni --src: usa la opcion [2] del panel e indica la carpeta origen.")
        print(f"        (buscado en: {ckpt})")
        return 2

    from padron_crop.batch import run_batch
    summary = run_batch(Path(src), out, workers=args.workers, resume=True)
    ok = summary.get("ok", 0) + summary.get("noop", 0)
    print(f"[OK] Lote al dia: {ok} utilizables, "
          f"Q:{summary.get('quarantine', 0)} FAIL:{summary.get('failed', 0)} "
          f"(workers: {summary.get('workers_used')}).")
    d = summary.get("delivery") or {}
    if d:
        print(f"     entrega/: {d.get('fotos_entregadas')} fotos + manifest_import.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
