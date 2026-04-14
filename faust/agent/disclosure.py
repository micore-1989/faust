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
