"""padron-crop CLI: inspect | crop | batch | sql | api | qa."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from padron_crop.batch import run_batch
from padron_crop.crop import crop_image


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_inspect(args) -> int:
    from padron_crop.inspect import inspect_summary

    _print(inspect_summary(Path(args.image)))
    return 0


SIDE_MAP = {
    "auto": None,
    "all": ["top", "bottom", "left", "right"],
    "left": ["left"],
    "right": ["right"],
    "top": ["top"],
    "bottom": ["bottom"],
}


def _apply_max_px(args) -> None:
    if getattr(args, "max_mp", None):
        from padron_crop.crop import set_max_pixels

        set_max_pixels(int(args.max_mp * 1_000_000))


def _vision_client(args):
    """D4 is only built when the operator passes --allow-remote-ai."""
    if not getattr(args, "allow_remote_ai", False):
        return None
    from padron_crop.vision import VisionClient

    return VisionClient(provider=getattr(args, "provider", "openai"),
                        allow_remote=True)


def cmd_crop(args) -> int:
    _apply_max_px(args)
    out = Path(args.out)
    face_safety = not getattr(args, "no_face_safety", False)
    rec = crop_image(Path(args.in_path), out.parent, out_name=out.name,
                     allowed_sides=SIDE_MAP[args.side],
                     vision=_vision_client(args), dry_run=args.dry_run,
                     deskew=getattr(args, "deskew", False),
                     face_safety=face_safety,
                     quality=getattr(args, "quality", 95),
                     aspect_ratio=getattr(args, "aspect_ratio", None))
    _print(rec)
    return 0 if rec["status"] in ("ok", "noop", "quarantine") else 1


def cmd_batch(args) -> int:
    from padron_crop.safeio import InsufficientSpace, Stop

    _apply_max_px(args)
    stop = Stop().install()          # Ctrl-C finishes the chunk, then stops
    face_safety = not getattr(args, "no_face_safety", False)
    try:
        summary = run_batch(Path(args.src), Path(args.out),
                            workers=max(1, args.workers), limit=args.limit,
                            resume=args.resume, dry_run=args.dry_run,
                            vision=_vision_client(args), stop=stop,
                            deskew=getattr(args, "deskew", False),
                            face_safety=face_safety,
                            quality=getattr(args, "quality", 95),
                            aspect_ratio=getattr(args, "aspect_ratio", None))
    except InsufficientSpace as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    _print(summary)
    if summary.get("interrupted"):
        print(f"interrupted: {summary.get('stop_reason')}; re-run with "
              f"--resume to continue", file=sys.stderr)
        return 130
    return 0


def cmd_sql(args) -> int:
    from padron_crop.ingest.sql import SqlIngest, decode_db_image

    try:
        ing = SqlIngest()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if not args.confirm:
        # never start a full scan without a human confirming table.column
        try:
            cands = ing.introspect_candidates()
        except Exception as e:  # noqa: BLE001 — DB unreachable is a clean error
            print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
            return 2
        _print({"message": "candidate columns found; review and re-run with "
                           "--confirm table.column to stream",
                "candidates": cands})
        return 0
    table, _, col = args.confirm.partition(".")
    if not table or not col:
        print("ERROR: --confirm expects table.column", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    qf = Path(args.query_file)
    statement = qf.read_text(encoding="utf-8").strip() if qf.exists() else None
    # raw BLOBs go to an isolated work dir so out/ keeps only cropped results
    work = out_dir / "_blobs"
    work.mkdir(parents=True, exist_ok=True)
    summary = {"ok": 0, "noop": 0, "quarantine": 0, "failed": 0}
    n = 0
    deskew = getattr(args, "deskew", False)
    face_safety = not getattr(args, "no_face_safety", False)
    quality = getattr(args, "quality", 95)
    aspect_ratio = getattr(args, "aspect_ratio", None)
    keep_blobs = getattr(args, "keep_blobs", False)

    for i, raw_val in enumerate(ing.iter_images(table, col, statement=statement)):
        raw_bytes, file_path, ext = decode_db_image(raw_val)
        temp_written = False
        if file_path is not None:
            target_p = file_path
        elif raw_bytes is not None:
            target_p = work / f"row_{i:08d}{ext}"
            target_p.write_bytes(raw_bytes)
            temp_written = True
        else:
            summary["failed"] = summary.get("failed", 0) + 1
            n += 1
            continue

        rec = crop_image(target_p, out_dir, deskew=deskew,
                         face_safety=face_safety, quality=quality,
                         aspect_ratio=aspect_ratio)
        summary[rec["status"]] = summary.get(rec["status"], 0) + 1
        n += 1

        if temp_written and not keep_blobs:
            try:
                target_p.unlink(missing_ok=True)
            except OSError:
                pass

    _print({"processed": n, "confirm": args.confirm,
            "query_file": str(qf) if statement else None, "summary": summary})
    return 0


def cmd_gallery(args) -> int:
    from padron_crop.gallery import build_gallery

    out_dir = Path(args.out)
    target = Path(args.html) if getattr(args, "html", None) else out_dir / "gallery.html"
    limit = getattr(args, "limit", None)
    res = build_gallery(out_dir, target, limit=limit)
    _print({"gallery": str(res), "message": "HTML visual QA gallery generated successfully"})
    return 0


def cmd_api(args) -> int:
    from padron_crop.ingest.api import iter_api_images, load_api_config

    cfg = load_api_config(Path(args.config))
    summary: dict = {"ok": 0, "noop": 0, "quarantine": 0, "failed": 0}
    for p in iter_api_images(cfg, Path(args.out)):
        rec = crop_image(p, Path(args.out))
        summary[rec["status"]] = summary.get(rec["status"], 0) + 1
    _print(summary)
    return 0


def cmd_qa(args) -> int:
    out = Path(args.out)
    report: dict = {"total": 0, "ok": 0, "noop": 0, "quarantine": 0, "failed": 0,
                    "quarantine_items": []}
    for sc in out.rglob("*.json"):
        try:
            rec = json.loads(sc.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        st = rec.get("status")
        if isinstance(st, str) and st in report:
            report[st] += 1
            report["total"] += 1
    qdir = out / "quarantine"
    if qdir.exists():
        report["quarantine_items"] = sorted(str(p) for p in qdir.glob("*.json"))
    _print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="padron-crop", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("inspect", help="measure bar geometry of one image")
    sp.add_argument("--image", required=True)
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("crop", help="crop one image")
    sp.add_argument("--in", dest="in_path", required=True)
    sp.add_argument("--out", required=True, help="output image path")
    sp.add_argument("--side", choices=list(SIDE_MAP), default="auto",
                    help="restrict detection to one/all side(s); default auto")
    sp.add_argument("--dry-run", action="store_true",
                    help="compute the record without writing anything")
    sp.add_argument("--max-mp", type=float, default=None,
                    help="decode ceiling in megapixels (RAM guard)")
    sp.add_argument("--deskew", action="store_true",
                    help="automatically detect and correct tilt/skew before cropping")
    sp.add_argument("--no-face-safety", action="store_true",
                    help="disable mathematical face & chin safety protection gate")
    sp.add_argument("--quality", type=int, default=95,
                    help="JPEG output quality (1-100, default 95)")
    sp.add_argument("--aspect-ratio", default=None,
                    help="optional target aspect ratio (e.g. 3:4, 1:1, 4:5)")
    sp.add_argument("--allow-remote-ai", action="store_true",
                    help="ENABLE D4 vision on TEST COPIES only (off by default)")
    sp.add_argument("--provider", choices=["openai", "gemini", "grok"],
                    default="openai")
    sp.set_defaults(func=cmd_crop)

    sp = sub.add_parser("batch", help="process a folder recursively")
    sp.add_argument("--src", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--workers", type=int, default=1)
    sp.add_argument("--limit", type=int, default=None)
    sp.add_argument("--resume", action="store_true")
    sp.add_argument("--dry-run", action="store_true",
                    help="detect and report only; write nothing")
    sp.add_argument("--max-mp", type=float, default=None,
                    help="decode ceiling in megapixels (RAM guard)")
    sp.add_argument("--deskew", action="store_true",
                    help="automatically detect and correct tilt/skew before cropping")
    sp.add_argument("--no-face-safety", action="store_true",
                    help="disable mathematical face & chin safety protection gate")
    sp.add_argument("--quality", type=int, default=95,
                    help="JPEG output quality (1-100, default 95)")
    sp.add_argument("--aspect-ratio", default=None,
                    help="optional target aspect ratio (e.g. 3:4, 1:1, 4:5)")
    sp.add_argument("--allow-remote-ai", action="store_true",
                    help="ENABLE D4 vision on TEST COPIES only (off by default)")
    sp.add_argument("--provider", choices=["openai", "gemini", "grok"],
                    default="openai")
    sp.set_defaults(func=cmd_batch)

    sp = sub.add_parser("sql", help="DB ingestion via PADRON_DB_URL")
    sp.add_argument("--query-file", required=True, help="query spec file")
    sp.add_argument("--out", required=True)
    sp.add_argument("--confirm", default=None,
                    help="table.column confirmed by a human after introspection")
    sp.add_argument("--keep-blobs", action="store_true",
                    help="keep raw extracted DB blobs in _blobs/ instead of cleaning up")
    sp.add_argument("--deskew", action="store_true",
                    help="automatically detect and correct tilt/skew before cropping")
    sp.add_argument("--no-face-safety", action="store_true",
                    help="disable mathematical face & chin safety protection gate")
    sp.add_argument("--quality", type=int, default=95,
                    help="JPEG output quality (1-100, default 95)")
    sp.add_argument("--aspect-ratio", default=None,
                    help="optional target aspect ratio (e.g. 3:4, 1:1, 4:5)")
    sp.set_defaults(func=cmd_sql)

    sp = sub.add_parser("api", help="API ingestion from a JSON config file")
    sp.add_argument("--config", required=True)
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_api)

    sp = sub.add_parser("qa", help="QA report of an out/ directory")
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_qa)

    sp = sub.add_parser("gallery", help="generate interactive HTML visual QA gallery")
    sp.add_argument("--out", required=True, help="out directory with JSON sidecars")
    sp.add_argument("--html", default=None, help="target HTML file path (default out/gallery.html)")
    sp.add_argument("--limit", type=int, default=None, help="maximum items to include in gallery")
    sp.set_defaults(func=cmd_gallery)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


def main_entry() -> None:
    sys.exit(main())


if __name__ == "__main__":
    main_entry()
