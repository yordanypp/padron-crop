"""SQL ingest: PADRON_DB_URL, introspection, confirm-gate, streaming.

Production hardening:

* connections are pooled with ``pool_pre_ping`` so a dropped/idle-killed
  connection is transparently replaced instead of failing a long run
* only ``SELECT``/``WITH`` statements are accepted (read-only by construction)
* transient DB errors (connection reset, deadlock, server gone away) are
  retried with backoff; the iterator never yields a row twice
"""
from __future__ import annotations

import os
import re

from padron_crop import safeio

CANDIDATE_COL_HINTS = ("blob", "longblob", "mediumblob", "bytea", "image",
                       "photo", "foto", "path", "file", "data")
CANDIDATE_TYPE_HINTS = ("blob", "bytea", "largebinary", "varbinary")

SQL_BATCH = int(os.environ.get("PADRON_SQL_BATCH", 50))
SQL_RETRIES = int(os.environ.get("PADRON_SQL_RETRIES", 3))

_READ_ONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def assert_read_only(statement: str) -> str:
    """Reject anything that is not a read-only query (no writes, ever)."""
    if not _READ_ONLY_RE.match(statement or ""):
        raise ValueError(
            "refusing to run a non read-only statement; only SELECT/WITH are allowed"
        )
    return statement


class SqlIngest:
    """Read-only SQL ingestion. Schema is never assumed: introspect first,
    then ask for confirmation before any full scan."""

    def __init__(self, dsn: str | None = None, retries: int = SQL_RETRIES):
        self.dsn = dsn or os.environ.get("PADRON_DB_URL")
        if not self.dsn:
            raise RuntimeError(
                "PADRON_DB_URL not set; refusing to guess connection parameters"
            )
        try:
            from sqlalchemy import create_engine
        except ImportError as e:
            raise RuntimeError(
                "sqlalchemy not installed; `pip install sqlalchemy` to use sql ingest"
            ) from e
        self.retries = retries
        # pool_pre_ping: a stale connection is recycled instead of erroring
        self.engine = create_engine(self.dsn, pool_pre_ping=True)

    def _retry(self, fn):
        return safeio.retry_call(fn, attempts=self.retries)

    def introspect_candidates(self) -> list[dict]:
        """List (table, column) candidates for image blobs/paths. No data read."""
        from sqlalchemy import inspect

        def run():
            insp = inspect(self.engine)
            found: list[dict] = []
            for t in insp.get_table_names():
                for c in insp.get_columns(t):
                    name = (c.get("name") or "").lower()
                    typ = str(c.get("type", "")).lower()
                    if any(h in name for h in CANDIDATE_COL_HINTS) or any(
                        h in typ for h in CANDIDATE_TYPE_HINTS
                    ):
                        found.append({"table": t, "column": c["name"], "type": typ})
            return found

        return self._retry(run)

    def plan_scan(self, table: str, column: str, batch: int = SQL_BATCH) -> dict:
        """Return the scan plan; caller must show it and get human confirmation.

        Identifiers are quoted with the dialect's own preparer, so MySQL gets
        backticks and PostgreSQL double quotes instead of one hardcoded style.
        """
        prep = self.engine.dialect.identifier_preparer
        return {
            "table": table,
            "column": column,
            "statement": f"SELECT {prep.quote(column)} FROM {prep.quote(table)}",
            "streaming": "yield_per",
            "batch": batch,
            "mode": "read-only",
        }

    def iter_images(self, table: str, column: str, batch: int = SQL_BATCH,
                    statement: str | None = None):
        """Stream rows in batches. Requires prior plan_scan() confirmation.

        ``statement`` (e.g. from the CLI ``--query-file``) replaces the default
        single-column SELECT and must be read-only. If the connection drops
        mid-stream, the query is retried and rows already yielded are skipped,
        so no row is ever emitted twice.
        """
        from sqlalchemy import text

        plan = self.plan_scan(table, column, batch)
        sql = assert_read_only(statement or plan["statement"])
        yielded = 0
        attempt = 0
        while True:
            try:
                with self.engine.connect().execution_options(
                    stream_results=True, yield_per=batch
                ) as conn:
                    result = conn.execute(text(sql))
                    seen = 0
                    for row in result:
                        if seen < yielded:      # skip rows from the previous try
                            seen += 1
                            continue
                        seen += 1
                        yielded += 1
                        yield row[0]
                return
            except Exception:  # noqa: BLE001 — transient DB/network failure
                attempt += 1
                if attempt > self.retries:
                    raise
