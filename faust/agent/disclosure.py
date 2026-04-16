"""
Disclosure layer — the real Approver implementation.

Routes tool calls by sensitivity class:
  - passive:    auto-approve, log to journal
  - active:     request confirmation via ConfirmationUI, log decision
  - disruptive: request confirmation via ConfirmationUI (with elevated flag), log decision

The ConfirmationUI protocol is the pluggable seam between the disclosure logic
and whatever surface renders it (CLI stdin, touchscreen banner, etc.). It
receives the tool name, arguments, and sensitivity, and returns True/False.

Journal integration: every tool call — approved, rejected, or auto-approved —
is recorded in the hash-chained journal BEFORE execution begins. After
execution completes, the result/error is recorded in a second entry so the
journal captures both the decision and the outcome.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Protocol

from .journal import Journal
from ..tools.registry import Sensitivity


class ConfirmationUI(Protocol):
    """Interface for surfaces that present confirmation prompts.

    Implementations:
      - CLIConfirmation: blocks on stdin (dev)
      - TouchConfirmation: renders banner on DSI display (production)

    May be sync or async — the approver awaits if needed.
    """

    def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        sensitivity: Sensitivity,
    ) -> Awaitable[bool] | bool: ...


async def _auto_confirm(
    tool_name: str,
    arguments: dict[str, Any],
    sensitivity: Sensitivity,
) -> bool:
    """Default no-op confirmation that approves everything. Used in tests."""
    return True


class DisclosureApprover:
    """Real Approver implementation wired to journal + confirmation UI.

    Drop-in replacement for the v0 _always_approve callback.

    Usage:
        journal = Journal("journal.db")
        approver = DisclosureApprover(journal, confirm=my_ui_callback)
        dispatcher = Dispatcher(registry, approver=approver)
    """

    def __init__(
        self,
        journal: Journal,
        confirm: ConfirmationUI | None = None,
    ) -> None:
        self.journal = journal
        self._confirm = confirm or _auto_confirm

    async def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        sensitivity: Sensitivity,
    ) -> bool:
        """The Approver contract: (tool_name, args, sensitivity) -> bool.

        Passive tools auto-approve. Active/disruptive tools go through the
        confirmation UI. Everything gets journaled.
        """
        if sensitivity == "passive":
            # Auto-approve, journal as "auto".
            self.journal.record(
                tool_name=tool_name,
                arguments=arguments,
                sensitivity=sensitivity,
                decision="auto",
            )
            return True

        # Active or disruptive: ask the confirmation UI.
        result = self._confirm(tool_name, arguments, sensitivity)
        if hasattr(result, "__await__"):
            approved = await result  # type: ignore[misc]
        else:
            approved = result

        self.journal.record(
            tool_name=tool_name,
            arguments=arguments,
            sensitivity=sensitivity,
            decision="approved" if approved else "rejected",
        )
        return approved

    def record_outcome(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        sensitivity: str,
        result_summary: str | None = None,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        """Record the execution outcome in the journal (post-dispatch).

        Called by the dispatch layer after a tool finishes, so the journal
        has both the approval decision AND the result.
        """
        decision = "approved" if error is None else "approved"
        self.journal.record(
            tool_name=tool_name,
            arguments=arguments,
            sensitivity=sensitivity,
            decision=decision,
            result_summary=result_summary,
            error=error,
            duration_ms=duration_ms,
        )


# ── TrustCache middleware ──────────────────────────────────────
# Sits above DisclosureApprover in the approver chain (spec §16.4). A
# successful approval under scope X silences subsequent confirmations for
# `window_s` seconds as long as the scope doesn't change. Scope changes
# explicitly invalidate the cache — see UIServer.scope_change handler.
#
# The journal still fires; the downstream consumer can stamp entries
# `confirmed: remembered` vs `confirmed: fresh` by reading
# `last_decision_was_cached` after each call.

Approver = Callable[
    [str, dict[str, Any], Sensitivity],
    Awaitable[bool] | bool,
]


def _default_scope_key() -> str:
    """Fallback scope key when no source is wired (pre-scope tests, CLI mode)."""
    return "none"


class TrustCache:
    """Wraps an Approver. Auto-approves if same scope within `window_s`.

    On cache hit: returns True without invoking the inner approver (no modal,
    no journal entry from the disclosure layer — the caller is responsible
    for stamping `confirmed: remembered` if it wants that distinction).
    On cache miss: delegates to inner; stores (scope_key, timestamp) only on
    successful approval. Rejections do not populate the cache, so a rejected
    call doesn't later auto-approve via a stale entry.
    """

    def __init__(
        self,
        inner: Approver,
        window_s: int = 600,
        scope_key_source: Callable[[], str] | None = None,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._window_s = window_s
        self._scope_key_source = scope_key_source or _default_scope_key
        self._time_source = time_source
        self._last_ok: tuple[str, float] | None = None
        # Read by the caller after each __call__ to tag the journal entry.
        self.last_decision_was_cached: bool = False

    async def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        sensitivity: Sensitivity,
    ) -> bool:
        scope_key = self._scope_key_source()
        now = self._time_source()

        if (
            self._last_ok is not None
            and self._last_ok[0] == scope_key
            and now - self._last_ok[1] < self._window_s
        ):
            self.last_decision_was_cached = True
            return True

        self.last_decision_was_cached = False
        result = self._inner(tool_name, arguments, sensitivity)
        if hasattr(result, "__await__"):
            approved = await result  # type: ignore[misc]
        else:
            approved = bool(result)

        if approved:
            self._last_ok = (scope_key, now)
        return approved

    def invalidate(self) -> None:
        """Drop the cache — next call goes through the inner approver."""
        self._last_ok = None


def scope_key_from_state(scope) -> str:
    """Derive the TrustCache scope key from a ScopeState.

    - template=None         → "none"
    - template="recon"      → "recon"
    - template="self-test"  → "self-test"
    - template="pentesting" → f"pentesting:{description}" so engagements don't
      share cached trust across different descriptions.
    """
    template = getattr(scope, "template", None)
    if template is None:
        return "none"
    if template == "pentesting":
        desc = getattr(scope, "description", None) or ""
        return f"pentesting:{desc}"
    return str(template)
