---
name: massive-image-ingest
description: Use when ingesting huge batches of photos from local folders, MySQL/PostgreSQL BLOBs via PADRON_DB_URL, or HTTP APIs into a processing pipeline, when planning RAM ceilings, streaming, workers, checkpoint/resume, or quarantine folders
---

# massive-image-ingest

## Overview

Three ingestion paths (local / sql / api) feeding **one** shared crop core. Core principle: **stream rows, never load the table or the folder listing into RAM; every artifact is idempotent and resumable; output only under `out/`.**

## When to use

- Batch processing thousands–millions of photos (decades of padrón data)
- Images arrive as files, DB BLOBs (Navicat is the human client, the script connects to the same DB), or API pages
- Need audit trail: sidecar JSON per image + CSV + `failed/` + `quarantine/`

## When NOT to use

- One-off single image → `padron-crop crop` directly
- Writing back to the DB or renaming originals → forbidden; read-only sources

## RAM ceiling rules

| Image size | Backend | Why |
|---|---|---|
| ≤ ~30 MP | Pillow + numpy | simplest, already installed |
| > ~30 MP or > 100 MB file | pyvips (`pip install "pyvips[binary]"`) | streaming, ~95 MB peak on 100 MP test vs ~800 MB for OpenCV (libvips benchmark, opened 2026-09-17) |
| detection pass on huge images | band-limited scans (edges + center strip), downscale grid | never decode full image twice |

- Cap workers by memory: `max_workers ≈ RAM_ceiling / per_image_peak`. Measure, don't assume (benchmark in `out/benchmark.md`).
- Decode once, decide, crop, write, free. No global caches of pixels.

## SQL path

- `PADRON_DB_URL` from env; never hardcode; read-only user expected.
- Schema is NOT assumed: introspect candidate columns (`blob|longblob|mediumblob|bytea|image|photo|foto|path`), list them, **ask confirmation before any full scan**.
- Stream with `yield_per` / `stream_results` / SSCursor; fetchmany batches. `fetchall()` on a BLOB table = OOM.
- Support BLOB columns and path/varchar columns (read file from disk path) with the same core.

## API path

- `PADRON_API_TOKEN` from env. Streaming download, retries with exponential backoff + jitter, pagination cursor, per-page checkpoint.
- Contract documented in `docs/specs/`; response schema validated before decode.

## Checkpoint / resume / idempotency

- State file (JSONL) with per-item status: `ok | noop | quarantine | failed`.
- Resume skips done items; failed items retried into `failed/` with error reason.
- Deterministic output naming from `sha256` (or stable source id) → re-running never duplicates work.
- Dry-run lists actions without writing.

## Common mistakes

| Mistake | Reality |
|---|---|
| `fetchall()` on BLOB table | Loads millions of rows into RAM; stream instead |
| Full scan without confirmation | Brief forbids it; introspect and ask first |
| One worker per file regardless of size | 20 workers × 500 MB decodes = OOM; cap by measured peak |
| Writing processed images next to source | Source is read-only; `out/` only |
| Skipping status ledger | Resume becomes reprocessing; audit becomes impossible |
| Secrets in config files committed | Env vars only (`PADRON_DB_URL`, `PADRON_API_TOKEN`); never echo values |

## Red flags — stop and verify

- About to run a query without a confirmed column list
- RSS climbing linearly with items processed (leak or accumulating list)
- A batch step without checkpoint after it
- PII photo about to leave the machine (remote AI) without explicit `--allow-remote-ai` on test copies
