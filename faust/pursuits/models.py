"""
Pursuit domain dataclasses.

- `Pursuit` + `ParamSpec`: static metadata registered once at startup.
- `PursuitRun`: live per-run bookkeeping (progress, activity log).
- `PursuitResult`: terminal record persisted to storage + linked from journal.
- `PursuitYield` / `PursuitResultPartial`: values an implementation yields
  into the runner. See `runner.py` for the async-gen protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: Literal["string", "int", "bool", "enum"]
    default: Any = None
    choices: Optional[list[Any]] = None
    required: bool = False


@dataclass(frozen=True)
class Pursuit:
    id: str
    title: str
    description: str
    duration_hint: str
    tools_used: list[str]
    parameters: list[ParamSpec]
    is_stoppable: bool = True
    is_custom: bool = False


@dataclass
class PursuitRun:
    pursuit_id: str
    run_id: str
    started_at: float
    params: dict[str, Any]
    progress: float = 0.0
    eta_s: Optional[int] = None
    status: Literal["running", "stopped", "complete", "error"] = "running"
    activity: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PursuitResult:
    run_id: str
    pursuit_id: str
    summary: str
    journal_entry_id: str
    artifacts: list[str] = field(default_factory=list)
    completed_at: float = 0.0


# ── Async-generator protocol types ─────────────────────────────

@dataclass(frozen=True)
class PursuitYield:
    """One progress/activity tick emitted by an implementation.

    Either field may be None; the runner only emits corresponding WS events
    for fields that are set. A yield with both fields None is a no-op and
    is still useful as a stop_event checkpoint.
    """
    progress: Optional[float] = None
    eta_s: Optional[int] = None
    activity: Optional[str] = None


@dataclass(frozen=True)
class PursuitResultPartial:
    """Terminal yield produced by an implementation to signal completion.

    Runner treats the *first* PursuitResultPartial it sees as the end of
    the run: emits PursuitComplete, writes the journal entry, persists to
    storage. Anything yielded after is discarded.
    """
    summary: str
    artifacts: list[str] = field(default_factory=list)
