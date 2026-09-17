# loadtest.md — massive-lot evidence (measured 2026-09-17)
## Large-scale load test

- lot: `lot-big` — 2500 files, 0.98 GB on disk

### Phase 1 — full run

- workers: 4
- summary: `{"ok": 2179, "noop": 219, "quarantine": 90, "failed": 12, "skipped": 0, "interrupted": false, "stop_reason": null}`
- wall time: 274.3 s -> 9.1 files/s, 4 MB/s
- peak RSS process tree: 267 MB | this process: 42 MB

### Phase 2 — interrupt and resume

- run 1: interrupted=True reason=`SIGINT` after 8.1 s
- records completed before the stop: **70**
- run 2 (`--resume`): skipped=70 processed=2430 in 241.1 s
- resume skipped exactly what was done: **True**

### Phase 3 — integrity

- ledger records: 2500 (unique sources: 2500)
- every source processed exactly once: **True**
- status tally in the final ledger: `{"ok": 2179, "noop": 219, "quarantine": 90, "failed": 12}`
- sidecars written: 2179
- orphan temp files left behind: **0**

### Extrapolation

- measured 9.1 files/s and 4 MB/s with 4 workers on this machine
- linear projection: **33k files/hour**, 13 GB/hour
- memory is per-image bounded (~17 B/pixel), so image *size* does not accumulate across the run; only worker count does


### Worker scaling (200 files, same lot)

| workers | wall s | files/s | speedup |
| --- | --- | --- | --- |
| 1 | 35.4 | 5.7 | 1.00x |
| 2 | 28.0 | 7.1 | 1.26x |
| 4 | 25.2 | 7.9 | 1.40x |
| 8 | 21.2 | 9.5 | 1.67x |

Per-worker memory is bounded by the single-image profile (phase 1);
scaling is sub-linear here because this lot is I/O-bound (400 KB-
4 MB files) and deliberately mixes patterns, which keeps re-triggering
per-image detection instead of the D0 fast path.

