"""
Pursuit events — parallel surface to faust.agent.events, scoped to the
Pursuit runner. Kept separate because agent events (Thinking, PlanProposed,
etc.) and Pursuit events have different consumers and lifecycles.

Wire mapping lives in faust/ui/bridge.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional, Union


@dataclass(frozen=True)
class PursuitStarted:
    """Internal: emitted when the runner picks up a run. The bridge
    suppresses this event (the client learns via the next `state` push)."""
    run_id: str
    pursuit_id: str
    params: dict[str, Any]


@dataclass(frozen=True)
class PursuitProgress:
    run_id: str
    pursuit_id: str
    progress: float
    elapsed_s: int
    eta_s: Optional[int] = None


@dataclass(frozen=True)
class PursuitActivity:
    run_id: str
    pursuit_id: str
    line: str


@dataclass(frozen=True)
class PursuitStopped:
    run_id: str
    pursuit_id: str
    reason: Literal["user", "error", "timeout"]
    error: Optional[str] = None


@dataclass(frozen=True)
class PursuitComplete:
    run_id: str
    pursuit_id: str
    summary: str
    journal_entry_id: str
    artifacts: list[str]


PursuitEvent = Union[
    PursuitStarted,
    PursuitProgress,
    PursuitActivity,
    PursuitStopped,
    PursuitComplete,
]
