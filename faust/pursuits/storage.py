"""
JSON-lines storage for completed Pursuit runs.

One line per PursuitResult. Append-only, read in order. Storage is per-
device (like the journal) and lives at ~/.faust/pursuits.jsonl by default.
Tests pass a tmp path.

Intentionally lightweight: this is a record of what ran, not a query
engine. Journal is the authoritative audit log; this is for UI recall.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .models import PursuitResult


DEFAULT_PATH = Path.home() / ".faust" / "pursuits.jsonl"


class PursuitStorage:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, result: PursuitResult) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(result), default=str) + "\n")

    def list_recent(self, limit: int = 50) -> list[PursuitResult]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            lines = [line for line in f.readlines() if line.strip()]
        tail = lines[-limit:] if limit > 0 else lines
        return [self._from_json(line) for line in tail]

    def get(self, run_id: str) -> Optional[PursuitResult]:
        """Linear scan — fine at a few thousand entries, replace with an
        index if we ever get there."""
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                if f'"run_id": "{run_id}"' not in line:
                    continue
                result = self._from_json(line)
                if result.run_id == run_id:
                    return result
        return None

    @staticmethod
    def _from_json(line: str) -> PursuitResult:
        data = json.loads(line)
        return PursuitResult(
            run_id=data["run_id"],
            pursuit_id=data["pursuit_id"],
            summary=data["summary"],
            journal_entry_id=data.get("journal_entry_id", ""),
            artifacts=list(data.get("artifacts", [])),
            completed_at=float(data.get("completed_at", 0.0)),
        )
