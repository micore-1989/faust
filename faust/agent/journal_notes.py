"""
Operator notes sidecar for the journal.

The main journal (faust/agent/journal.py) is a tamper-evident hash-chained
SQLite log — immutable by design. Operator notes are mutable free-form text
and have no place inside the audit chain. They live here, in a trivial
JSON file keyed by journal seq.

Path convention: put the sidecar next to the journal db itself, e.g.
`journal.db` → `journal.db.notes.json`. The caller decides the path so
tests can point at a temp dir.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class JournalNotes:
    """Thread-unsafe, single-process notes sidecar. Server is single-process."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._cache: dict[str, str] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text() or "{}")
                if isinstance(raw, dict):
                    self._cache = {str(k): str(v) for k, v in raw.items()}
            except (OSError, json.JSONDecodeError):
                # Corrupted sidecar: ignore and start fresh. The main
                # journal is the source of truth; notes are lossy.
                self._cache = {}

    def get(self, entry_id: str | int) -> str:
        return self._cache.get(str(entry_id), "")

    def set(self, entry_id: str | int, notes: str) -> None:
        self._cache[str(entry_id)] = notes
        self._flush()

    def all(self) -> dict[str, str]:
        return dict(self._cache)

    def _flush(self) -> None:
        """Atomic write via tempfile-rename so a crash mid-write can't
        leave a partial JSON document on disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._cache, f, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
