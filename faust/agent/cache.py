"""
Short-TTL result cache for passive/active skills.

Follow-up prompts like "deauth that AP" should not trigger another wifi_scan
if one ran 30 seconds ago. The cache stores each successful skill's summary
(not the full result — summaries are small and opinion-bearing) under a key
derived from (skill_name, sorted(args)).

TTLs are sensitivity-indexed:
  - passive:    300 s  (scans go stale slowly)
  -  active:     60 s  (network state changes faster)
  - disruptive: never  (cached attacks make no sense)

The cache is read-only to the planner: it receives a "Known recent results"
section injected into Pass 1's system prompt. If the planner decides to
re-scan anyway (operator pressure, explicit "rescan" verb), it emits the
skill normally and the fresh result overwrites the cache entry.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..tools.registry import Sensitivity


# Default TTLs per sensitivity class, in seconds.
_DEFAULT_TTL: dict[Sensitivity, int] = {
    "passive": 300,
    "active": 60,
    "disruptive": 0,  # never cache
}


@dataclass
class CacheEntry:
    skill: str
    args_digest: str
    summary: dict[str, Any]
    stored_at: float  # time.monotonic()
    ttl_s: int


@dataclass
class ResultCache:
    """Simple in-memory TTL cache. Single instance lives for the session.

    Not thread-safe — the agent loop is single-threaded async. If that
    changes, wrap store/lookup in a lock.
    """
    entries: dict[str, CacheEntry] = field(default_factory=dict)
    ttl_override: dict[Sensitivity, int] | None = None

    def _ttl_for(self, sensitivity: Sensitivity) -> int:
        if self.ttl_override and sensitivity in self.ttl_override:
            return self.ttl_override[sensitivity]
        return _DEFAULT_TTL.get(sensitivity, 0)

    def _key(self, skill: str, args: dict[str, Any]) -> str:
        # Canonical args → stable digest, independent of dict insertion order.
        canonical = json.dumps(args, sort_keys=True, default=str)
        digest = hashlib.sha1(canonical.encode()).hexdigest()[:12]
        return f"{skill}:{digest}"

    def store(
        self,
        skill: str,
        args: dict[str, Any],
        summary: dict[str, Any] | None,
        sensitivity: Sensitivity,
    ) -> None:
        """Store a skill's summary. No-op if summary missing or TTL is 0."""
        if summary is None:
            return
        ttl = self._ttl_for(sensitivity)
        if ttl <= 0:
            return
        key = self._key(skill, args)
        self.entries[key] = CacheEntry(
            skill=skill,
            args_digest=key.split(":", 1)[1],
            summary=summary,
            stored_at=time.monotonic(),
            ttl_s=ttl,
        )

    def fresh_entries(self) -> list[CacheEntry]:
        """Return non-expired entries, newest first. Evicts stale entries lazily."""
        now = time.monotonic()
        alive: list[CacheEntry] = []
        expired: list[str] = []
        for key, e in self.entries.items():
            if now - e.stored_at > e.ttl_s:
                expired.append(key)
            else:
                alive.append(e)
        for key in expired:
            del self.entries[key]
        alive.sort(key=lambda e: -e.stored_at)
        return alive

    def render_prompt_section(self, max_entries: int = 6) -> str:
        """Render the 'Known recent results' section for the planner prompt.

        Returns empty string when the cache has no fresh entries.
        """
        fresh = self.fresh_entries()[:max_entries]
        if not fresh:
            return ""
        now = time.monotonic()
        lines = ["## Known recent results",
                 "You already have these outcomes cached. If the user's request "
                 "can be served from them, reference the facts directly in your "
                 "plan reasoning INSTEAD of re-invoking the skill. Re-run only "
                 "when staleness matters or the user asked for a fresh scan."]
        for e in fresh:
            age_s = int(now - e.stored_at)
            # Compact summary: prefer JSON so the planner can pattern-match.
            lines.append(
                f"- {e.skill} [{age_s}s ago]: {json.dumps(e.summary, default=str)}"
            )
        return "\n".join(lines)

    def clear(self) -> None:
        self.entries.clear()
