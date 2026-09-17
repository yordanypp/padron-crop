# sqltest.md — SQL ingestion evidence (2026-09-17)
## SQL ingestion against a real database

- server: `127.0.0.1:3306/bd_pruebas_pep` (driver `mysql+pymysql`)
- temporary table created for the test: `padron_crop_test_blobs`
- rows inserted: 240 of real image bytes (12 distinct photos)

- existing BLOB/path candidates found by introspection: 2

- rows verified in the table: 240

### CLI run

```
$ padron_crop sql --query-file C:\Users\daryf\Downloads\proyecto padron quitar negros\out\sql-run\query.sql --out C:\Users\daryf\Downloads\proyecto padron quitar negros\out\sql-run --confirm padron_crop_test_blobs.foto
```

- wall time: 40.6 s for 240 rows (5.9 rows/s)
- CLI summary: `{"processed": 240, "confirm": "padron_crop_test_blobs.foto", "summary": {"ok": 180, "noop": 40, "quarantine": 20, "failed": 0}}`
- cropped images written: 180
- sidecars written: 180

### Dialect-correct default statement

- `SELECT foto FROM padron_crop_test_blobs`

- streamed 240 rows with the default plan

### Cleanup

- temporary table `padron_crop_test_blobs` dropped: True

