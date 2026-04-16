"""
Journal query + serialization helpers for the Stage 11 UI.

Why this module exists:
  - The UI needs JSON-shaped entries it can filter on the wire — the raw
    SQLite rows via Journal.entries() expose typed dataclasses that don't
    match the dashboard's grouping requirements (sigil category, derived
    entry "type") without post-processing.
  - Operator notes are stored in a sidecar JSON file (see
    faust.agent.journal_notes), outside the tamper-evident hash chain.
    `serialize_entries` merges them in.

Filter semantics: AND across all provided keys. Unknown keys are ignored
so the client can send forward-compatible filter payloads without the
server 400'ing.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

from ..agent.catalog import _categorize


_CATEGORY_KEY = "category"


def _derive_type(tool_name: str) -> str:
    """Map the journal row's tool_name back to one of the UI's logical
    entry types. The SQLite column is a string; the UI needs the coarser
    grouping (`scope_set` / `pact_activated` / `pursuit_complete` /
    `tool_invocation`)."""
    if tool_name == "scope.set":
        return "scope_set"
    if tool_name == "pact.activated":
        return "pact_activated"
    if tool_name.startswith("pursuit."):
        return "pursuit_complete"
    return "tool_invocation"


def _derive_category(tool_name: str, entry_type: str) -> str | None:
    if entry_type != "tool_invocation":
        return None
    return _categorize(tool_name)


def serialize_entry(entry: Any, notes: str | None = None) -> dict[str, Any]:
    """Convert a JournalEntry dataclass into the wire-shape dict the UI
    consumes. `notes` is merged in from the sidecar (empty string when
    the operator hasn't written anything yet)."""
    etype = _derive_type(entry.tool_name)
    return {
        "id": str(entry.seq),
        "seq": entry.seq,
        "timestamp": entry.timestamp,
        "type": etype,
        "tool_name": entry.tool_name,
        "arguments": entry.arguments,
        "sensitivity": entry.sensitivity,
        "decision": entry.decision,
        "result_summary": entry.result_summary,
        "error": entry.error,
        "duration_ms": entry.duration_ms,
        "category": _derive_category(entry.tool_name, etype),
        "notes": notes or "",
        "prev_hash": entry.prev_hash,
        "row_hash": entry.row_hash,
    }


def _time_range_bounds(time_range: str, now: float | None = None) -> tuple[float, float] | None:
    """Map a UI time-range token to (min_ts, max_ts). None means no bound."""
    if not time_range:
        return None
    t = now if now is not None else time.time()
    if time_range == "today":
        # Local midnight; cheap version — subtract seconds-since-local-midnight.
        local = time.localtime(t)
        start = t - (local.tm_hour * 3600 + local.tm_min * 60 + local.tm_sec)
        return (start, t + 1)
    if time_range == "24h":
        return (t - 24 * 3600, t + 1)
    if time_range == "7d":
        return (t - 7 * 24 * 3600, t + 1)
    if time_range == "session":
        # "Session" is client-relative (boot timestamp). Server can't
        # know the client's session without state; fall back to "24h"
        # as a pragmatic approximation — the client can further trim.
        return (t - 24 * 3600, t + 1)
    return None


def query_journal(
    entries: Iterable[dict[str, Any]],
    filters: dict[str, Any] | None,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Filter already-serialized entries. Filters (all optional, AND'd):
      group        — sigil category (wifi_ble | sub_ghz | ...)
      tool         — exact tool_name match
      sensitivity  — passive | active | disruptive
      time_range   — today | 24h | 7d | session
      scope        — exact scope template match in scope.set entries
      id           — single-entry lookup by seq-as-string
      limit        — slice the result tail (newest N)
    """
    filters = filters or {}
    results = list(entries)

    if filters.get("id"):
        want = str(filters["id"])
        results = [e for e in results if str(e.get("id")) == want]

    if filters.get("group"):
        g = filters["group"]
        results = [e for e in results if e.get(_CATEGORY_KEY) == g]

    if filters.get("tool"):
        tool = filters["tool"]
        results = [e for e in results if e.get("tool_name") == tool]

    if filters.get("sensitivity"):
        s = filters["sensitivity"]
        results = [e for e in results if e.get("sensitivity") == s]

    tr = _time_range_bounds(filters.get("time_range") or "", now=now)
    if tr is not None:
        lo, hi = tr
        results = [e for e in results if lo <= (e.get("timestamp") or 0) < hi]

    # Newest-first display order; slice after sorting so limit is meaningful.
    results.sort(key=lambda e: e.get("timestamp") or 0, reverse=True)

    limit = filters.get("limit")
    if isinstance(limit, int) and limit > 0:
        results = results[:limit]

    return results
