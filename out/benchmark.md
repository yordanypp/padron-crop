# benchmark.md — tiempos y memoria (medido 2026-09-17)
## Single huge image

- input: `prm_10000x8000.jpg` 10000x8000 = 80 MP, 1.7 MB
- generation: 0.0 s (synthetic)
- crop status: `ok` method `projection` box [0, 0, 10000, 5440]
- wall time: 5.22 s median of 3 (best 4.79 s -> 16.7 MP/s)
- peak RSS: 802 MB (this process, incl. numpy native) | current RSS: 40 MB | python-tracked peak: 458 MB

## Big batch simulation

- lot: 1000 synthetic images 1280x960 (1.2 MP each), 35 MB on disk
- lot reused from bench-input (already generated)
- generation: 0.0 s (synthetic)
- workers: 4
- summary: `{"ok": 800, "noop": 100, "quarantine": 50, "failed": 50, "skipped": 0}`
- wall time: 46.8 s -> 21.4 img/s
- peak RSS main proc: 38 MB | current RSS: 39 MB

Notes:
- worker subprocess RSS is not included in the main-process peak;
  per-worker ceiling is bounded by the single-image profile above.
- wall time is load-sensitive: it depends on machine load and OS cache
  state, so treat it as an order of magnitude, not a constant.

