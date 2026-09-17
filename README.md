# padron-crop

Deterministic cropper that removes the black **PRM** block (and equivalent black
bars) from padrón photos by **cropping, never painting**. The useful region
(face/photo) is preserved; if a crop would invade it, the cut is reduced or the
image is quarantined.

> Invariant: **NEVER inpaint, NEVER fill, NEVER generate a face.** Output always
> goes to `out/`; the source is opened read-only and never modified.

---

## 1. Requirements

- Python **3.11+** (tested on 3.14)
- `numpy` + `Pillow` (pure CPU, wheels for Windows / macOS / Linux)

```bash
python -m pip install -r requirements.txt
```

Nothing else is required. Optional extras (install only if you need them):

| extra   | install                       | what it adds                                    |
| ------- | ----------------------------- | ----------------------------------------------- |
| `cv`    | `pip install -e ".[cv]"`      | opencv-python-headless — deskew, face safety gate, fast CC |
| `sql`   | `pip install -e ".[sql]"`     | SQLAlchemy — SQL/BLOB ingestion / Navicat DB   |
| `api`   | `pip install -e ".[api]"`     | httpx — API ingestion                           |
| `ocr`   | `pip install -e ".[ocr]"`     | pytesseract (+ Tesseract binary) — OCR anchor   |
| `huge`  | `pip install -e ".[huge]"`    | pyvips — hundreds-of-MP images at low RAM       |
| `dev`   | `pip install -e ".[dev]"`     | pytest                                          |

## 2. Install

```bash
# from the project root
python -m pip install -e .          # provides the `padron-crop` console script
```

Or run it without installing (any OS):

```bash
# Windows: set PYTHONPATH=src
PYTHONPATH=src python -m padron_crop --help
```

## 3. Quickstart — reproduce the anchor crop

```bash
PYTHONPATH=src python -m padron_crop crop \
    --in 0aaa2b82-4607-4f53-8a28-ccafa017104d.jpg \
    --out out/sample/anchor_crop.jpg --side auto
```

Expected: `status=ok`, `crop_box_xywh=[0,0,960,1004]`, `method=projection+glyphs`
(removes the PRM block and the bar below it, keeps the face), and a sidecar
`out/sample/0aaa2b82-4607-4f53-8a28-ccafa017104d.json`.

## 4. CLI

```
padron-crop inspect  --image PATH
padron-crop crop     --in PATH --out PATH --side auto|left|right|top|bottom|all
                     [--deskew] [--no-face-safety] [--quality Q] [--aspect-ratio R]
                     [--dry-run] [--max-mp N] [--allow-remote-ai] [--provider P]
padron-crop batch    --src DIR --out DIR --workers N --limit N --resume
                     [--deskew] [--no-face-safety] [--quality Q] [--aspect-ratio R]
                     [--dry-run] [--max-mp N] [--allow-remote-ai] [--provider P]
padron-crop sql      --query-file FILE --out DIR [--confirm table.column]
padron-crop api      --config FILE --out DIR
padron-crop qa       --out DIR
```

- `batch` is recursive, checkpointed (`state.jsonl`), audited (`audit.csv`) and
  idempotent: `--resume` skips work already recorded.
- `--dry-run` detects and reports but writes nothing (no images, no sidecars, no
  state/audit). Use it to size a job before running it.
- `--max-mp N` sets the decode ceiling in megapixels (RAM guard); above it the
  image fails cleanly instead of OOM-ing.
- `sql` uses `PADRON_DB_URL`; it **introspects** candidate blob/path columns and
  prints them. A full scan only runs after a human confirms `--confirm table.column`.
  `--query-file` overrides the default single-column SELECT; raw BLOBs are staged
  in `out/_blobs/` so `out/` keeps only cropped results.
- `api` reads a JSON config; auth is only ever read from env, never from a file.

### Environment variables

| variable                 | used by        | meaning                                          |
| ------------------------ | -------------- | ------------------------------------------------ |
| `PADRON_DB_URL`          | `sql`          | SQLAlchemy DSN (MySQL/MariaDB/PostgreSQL/SQLite) |
| `PADRON_API_TOKEN`       | `api`, `gemini`, `grok` | bearer token for the HTTP ingestion   |
| `OPENAI_API_KEY`         | `--provider openai` | D4 vision token (off by default)            |
| `PADRON_MAX_PIXELS`      | all            | decode ceiling in pixels (default 512 MP)        |
| `PADRON_MIN_FREE_MB`     | `batch`        | free-space reserve; below it the run stops cleanly (default 200) |
| `PADRON_DISK_CHECK_EVERY`| `batch`        | re-check free space every N chunks (default 20)  |
| `PADRON_CHUNK`           | `batch`        | images per parallel chunk (default 25)           |
| `PADRON_FREEZE_N`        | `batch`        | samples before freezing the D0 pattern (default 5) |
| `PADRON_RECALIBRATE_K`   | `batch`        | re-verify the frozen pattern every K images (default 25) |
| `PADRON_PATTERN_TOL`     | `batch`        | relative thickness tolerance for a matching pattern (default 0.15) |
| `PADRON_SQL_BATCH`       | `sql`          | rows per streamed batch (default 50)             |
| `PADRON_SQL_RETRIES`     | `sql`          | reconnect attempts on a dropped connection (default 3) |
| `PADRON_API_TIMEOUT`     | `api`          | per-request timeout in seconds (default 30)      |
| `PADRON_API_RETRIES`     | `api`          | attempts per request/download (default 3)        |
| `PADRON_API_BACKOFF`     | `api`          | base backoff in seconds, jittered (default 0.5)  |
| `PADRON_NORM_HIGH`       | detection      | under-exposure trigger; `0` disables it (default 0.55) |

### Exit codes

| code | meaning |
| ---- | ------- |
| 0 | success (including `noop`/`quarantine`) |
| 1 | the single `crop` failed |
| 2 | bad usage / missing DSN or unreadable image |
| 3 | not enough free disk space |
| 130 | interrupted (SIGINT); re-run with `--resume` |

Copy `.env.example` and fill it locally. **Never commit real credentials.**

## 5. Sidecar contract

One JSON per photo, plus a CSV audit line:

```json
{ "source": "...", "sha256": "...", "orig_wh": [960, 1280],
  "crop_box_xywh": [0, 0, 960, 1004], "sides": ["bottom"],
  "method": "projection+glyphs", "confidence": 0.903,
  "face_safety_ok": true, "elapsed_ms": 329, "status": "ok" }
```

`status` ∈ `ok` | `noop` | `quarantine` | `failed`.
`quarantine/` holds images that must not be cropped (uniform dark, crop would
remove the majority); `failed/` holds corrupt/0-byte/non-image inputs.

## 6. How detection works

Cascade, in order, each contributing confidence; the crop is chosen by score and
disagreement above the threshold goes to quarantine instead of guessing:

1. **D0 — batch geometry cache (fast path).** If `FREEZE_N` samples share
   side + relative thickness, geometry is frozen and re-verified (dark zones +
   uniform-dark + removal-area safety gates) instead of re-detected.
   Recalibrates every `RECALIBRATE_K` hits or on any verification failure.
2. **D1 — projection profiles** of dark line fractions from each border.
3. **D2 — connected components** of the edge dark mask (run-length + union-find)
   to reject dark clothing/shadows and to find the text block.
4. **D3 — glyph anchoring.** Bright glyph-like components ("PRM") inside the dark
   band fix the exact cut line: topmost glyph row − margin.
5. **D4 — optional vision API** (`src/padron_crop/vision.py`), disconnected by
   default. Enabled only with `--allow-remote-ai` **and** an env token, and only
   for images that pass the test-copy guard (`assert_test_copy`) — real padrón
   photos are refused before any request is built. It receives a ≤512 px JPEG
   thumbnail, must answer a strict schema (`bbox_xywh`/`kind`/`confidence`,
   extra fields rejected), and **can only veto**: agreement keeps the
   deterministic box, a disagreement above `DISAGREE_TOL` sends the image to
   quarantine. It never substitutes D0–D2.

Covered cases (each has a test): single-side bars, 2–4 side frames, L/C shapes,
variable thickness, non-pure black / vignette, PRM glyphs, fixed vs per-image
pattern, already-clean no-op, uniform-dark quarantine, EXIF rotation, formats
jpg/jpeg/png/webp/bmp/tif and extension-less BLOBs, corrupt files, and huge
synthetic images.

## 7. Resilience (unattended runs)

Everything that can stop a multi-day job is handled explicitly:

| failure | behaviour |
| ------- | --------- |
| process crash mid-run | every ledger write is atomic or fsynced, and the state reader ignores a torn last line → `--resume` continues with **no work lost or repeated** |
| crash while writing an image/sidecar | written to `.tmp-*` in the same directory then `os.replace`d, so a truncated file is never mistaken for finished work |
| full disk | free space is checked before the run and every `PADRON_DISK_CHECK_EVERY` chunks; the run stops cleanly with exit code 3 instead of filling the volume |
| Ctrl-C / SIGTERM | the current chunk finishes, ledgers are flushed, the pool is shut down and the run exits with 130; `--resume` picks up exactly where it stopped |
| not enough RAM | decoding is bounded by `--max-mp`/`PADRON_MAX_PIXELS`, profiles are chunked, and peak usage is ~17 B/pixel regardless of lot size |
| unsafe multiprocessing | with `workers>1` from stdin/`-c`/a REPL the spawn start method cannot re-import the entry point; instead of a `BrokenProcessPool` crash it **downgrades to 1 worker with a warning** |
| flaky network (`api`) | per-request timeouts, jittered exponential backoff, `Retry-After` respected, only transient HTTP statuses retried, and downloads resume from a `.part` file via HTTP Range |
| a permanently bad item | isolated and recorded (not fatal), so one bad row cannot kill the run |
| dropped DB connection | `pool_pre_ping` recycles stale connections; the stream retries and never yields a row twice; only `SELECT`/`WITH` are accepted |
| over/under-exposed photos | under-exposed images get an adaptive luma stretch so the bar is still detected; a clean photo is never rescaled (guarded by test) |
| corrupt / 0-byte / non-image | `failed` queue + audit row, never a crash |

## 8. Portability & Acceleration

- Core engine is pure `numpy`/`Pillow` (CPU-first, zero GPU required).
- Optional OpenCV acceleration (`[cv]`) provides C++ morphological and connected components, Hough deskewing, and mathematical face & chin safety protection.
- Paths are `pathlib`-based and relative to the working directory; nothing is
  hardcoded to one machine.
- Peak memory is bounded (~17 bytes/pixel; 80 MP ≈ 0.8 GB) by chunked profiles
  and a single RGB buffer; see [`out/benchmark.md`](out/benchmark.md).
- Windows/macOS/Linux: the only Windows-specific code is the optional peak-RSS
  probe in `tools/benchmark.py`, which degrades to `n/a` elsewhere.

## 9. Tests

```bash
python -m pytest -q          # 100 tests, ~4-6 s
```

Verified from a completely clean environment:

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev,cv]"
.venv/Scripts/python -m pytest -q      # 100 passed
.venv/Scripts/padron-crop crop --in 0aaa2b82-....jpg --out out/sample/anchor_crop.jpg
```

Heavy paths are kept fast: synthetic JPEGs are encoded once and memoized per
pixel buffer, the huge-image case is ~6 MP (the 80 MP worst case lives in
`out/benchmark.md`), and the local HTTP server used for the retry test skips
`socket.getfqdn()`, which otherwise stalls for hundreds of ms on Windows.

## 10. Layout

```
src/padron_crop/    geometry.py (cascade)  crop.py (core)  batch.py  cli.py
                    opencv_ext.py (acceleration & face safety)
                    ingest/ local.py sql.py api.py
docs/               research/ specs/ plans/ ai-workflows.md
.agents/skills/     project skills (see AGENTS.md)
tools/              inspect_sample.py make_lot.py loadtest.py scale_test.py
                    sql_integration_test.py benchmark.py
out/                sample/ (anchor crop + sidecar), benchmark.md,
                    loadtest.md, sqltest.md
```

## 11. Measured evidence

| evidence | file | result |
| -------- | ---- | ------ |
| anchor geometry | `docs/research/sample-geometry.md` | glyphs at y≈1010-1084, solid black 1085-1280 |
| single 80 MP worst case | `out/benchmark.md` | 5.2 s median (16.7 MP/s), 802 MB peak |
| mixed lot | `out/benchmark.md` | 1000 files, 21.4 files/s, 4 workers |
| **0.98 GB / 2500-file lot** | `out/loadtest.md` | 9.1 files/s, 267 MB process-tree peak, interrupt+resume exact, 0 orphan temp files |
| worker scaling | `out/loadtest.md` | 1→8 workers on an I/O-bound mixed lot: 1.67x |
| **real MySQL ingest** | `out/sqltest.md` | 240 rows of real bytes via the CLI: ok=180 noop=40 quarantine=20, temp table dropped |
