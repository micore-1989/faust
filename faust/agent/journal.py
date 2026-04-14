"""
Tamper-evident disclosure journal.

Every tool call — approved or rejected — gets an append-only record in SQLite.
Each row includes a sha-256 hash of (prev_hash ‖ row_data), forming a hash
chain. If any row is modified or deleted after the fact, the chain breaks and
`verify_chain()` returns the first corrupted sequence number.

The journal is per-device (gitignored as `journal.db`). It exists so that:
  - An operator can audit what the device did and when
  - A reviewer can verify no entries were retroactively altered
  - The disclosure layer has a durable log independent of the event stream

Schema is intentionally flat — one table, no JOINs, fast appends.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal


GENESIS_HASH = "0" * 64  # First entry chains from this.


@dataclass
class JournalEntry:
    """A single journal record. Mirrors the DB row."""

    seq: int
    timestamp: float
    tool_name: str
    arguments: dict[str, Any]
    sensitivity: str
    decision: Literal["approved", "rejected", "auto"]
    result_summary: str | None = None
    error: str | None = None
    duration_ms: int = 0
    prev_hash: str = ""
    row_hash: str = ""


def _compute_hash(prev_hash: str, data: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{data}".encode()).hexdigest()


def _row_data(
    timestamp: float,
    tool_name: str,
    arguments: str,
    sensitivity: str,
    decision: str,
    result_summary: str | None,
    error: str | None,
    duration_ms: int,
) -> str:
    """Deterministic serialization of the mutable fields for hashing."""
    return json.dumps(
        [timestamp, tool_name, arguments, sensitivity, decision,
         result_summary, error, duration_ms],
        sort_keys=True,
        separators=(",", ":"),
    )


class Journal:
    """Append-only, hash-chained disclosure log backed by SQLite."""

    def __init__(self, db_path: str = "journal.db") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS journal (
                seq          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    REAL    NOT NULL,
                tool_name    TEXT    NOT NULL,
                arguments    TEXT    NOT NULL,
                sensitivity  TEXT    NOT NULL,
                decision     TEXT    NOT NULL,
                result_summary TEXT,
                error        TEXT,
                duration_ms  INTEGER NOT NULL DEFAULT 0,
                prev_hash    TEXT    NOT NULL,
                row_hash     TEXT    NOT NULL
            )
        """)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT row_hash FROM journal ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS_HASH

    def record(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        sensitivity: str,
        decision: Literal["approved", "rejected", "auto"],
        result_summary: str | None = None,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> JournalEntry:
        """Append an entry. Returns the new JournalEntry with hash."""
        ts = time.time()
        args_json = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        prev = self._last_hash()
        data = _row_data(ts, tool_name, args_json, sensitivity, decision,
                         result_summary, error, duration_ms)
        row_hash = _compute_hash(prev, data)

        cur = self._conn.execute(
            """INSERT INTO journal
               (timestamp, tool_name, arguments, sensitivity, decision,
                result_summary, error, duration_ms, prev_hash, row_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, tool_name, args_json, sensitivity, decision,
             result_summary, error, duration_ms, prev, row_hash),
        )
        self._conn.commit()

        return JournalEntry(
            seq=cur.lastrowid,  # type: ignore[arg-type]
            timestamp=ts,
            tool_name=tool_name,
            arguments=arguments,
            sensitivity=sensitivity,
            decision=decision,
            result_summary=result_summary,
            error=error,
            duration_ms=duration_ms,
            prev_hash=prev,
            row_hash=row_hash,
        )

    def entries(self) -> list[JournalEntry]:
        """Return all entries in chain order."""
        rows = self._conn.execute(
            "SELECT * FROM journal ORDER BY seq ASC"
        ).fetchall()
        return [
            JournalEntry(
                seq=r[0], timestamp=r[1], tool_name=r[2],
                arguments=json.loads(r[3]), sensitivity=r[4],
                decision=r[5], result_summary=r[6], error=r[7],
                duration_ms=r[8], prev_hash=r[9], row_hash=r[10],
            )
            for r in rows
        ]

    def verify_chain(self) -> int | None:
        """Verify hash chain integrity.

        Returns None if chain is intact, or the seq number of the first
        corrupted entry.
        """
        prev = GENESIS_HASH
        for row in self._conn.execute(
            "SELECT seq, timestamp, tool_name, arguments, sensitivity, "
            "decision, result_summary, error, duration_ms, prev_hash, row_hash "
            "FROM journal ORDER BY seq ASC"
        ):
            seq, ts, tool_name, args_json, sens, dec, res, err, dur, stored_prev, stored_hash = row

            if stored_prev != prev:
                return seq

            data = _row_data(ts, tool_name, args_json, sens, dec, res, err, dur)
            expected = _compute_hash(prev, data)
            if stored_hash != expected:
                return seq

            prev = stored_hash

        return None

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM journal").fetchone()
        return row[0]
