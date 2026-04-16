"""
Tool dispatch.

This is THE seam where the disclosure layer wedges in. The loop never calls
registry.invoke() directly — it goes through Dispatcher.dispatch().

In v0 the disclosure hook is a no-op pass-through that logs the sensitivity
class. The real implementation (next session) will:
  - passive: execute immediately, log to journal
  - active: surface confirmation banner, block on confirm
  - disruptive: surface banner with hold-to-confirm gesture, block

The dispatch contract is what disclosure plugs into:
  approve(tool_name, args, sensitivity) -> bool

Default approver returns True for everything. Real disclosure layer replaces it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .events import ToolCallExecuted
from ..tools.registry import ToolRegistry, Sensitivity, ToolResult

# Approver callback. Returning False means the user rejected the call.
# May be sync or async; dispatcher will await if needed.
Approver = Callable[[str, dict[str, Any], Sensitivity], Awaitable[bool] | bool]


async def _always_approve(name: str, args: dict[str, Any], sens: Sensitivity) -> bool:
    """Default approver. Real disclosure layer replaces this."""
    return True


@dataclass
class DispatchResult:
    executed: bool      # False if approver rejected
    result: Any = None
    error: str | None = None
    duration_ms: int = 0
    # Compact structured summary of the result for agent feedforward.
    # Set when the skill returns a ToolResult(result=..., summary=...);
    # None for legacy skills that return a bare dict.
    summary: dict[str, Any] | None = None


class Dispatcher:
    def __init__(
        self,
        registry: ToolRegistry,
        approver: Approver | None = None,
    ) -> None:
        self.registry = registry
        self.approver = approver or _always_approve

    async def dispatch(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> DispatchResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            return DispatchResult(
                executed=False,
                error=f"unknown tool: {tool_name}",
            )

        # --- DISCLOSURE HOOK ---
        # Real implementation: surface UI banner, await user confirmation.
        # v0: always approves.
        approval = self.approver(tool_name, arguments, tool.sensitivity)
        if hasattr(approval, "__await__"):
            approval = await approval  # type: ignore[assignment]
        if not approval:
            return DispatchResult(
                executed=False,
                error="user_rejected",
            )

        start = time.monotonic()
        try:
            raw = await self.registry.invoke(tool_name, arguments)
            duration_ms = int((time.monotonic() - start) * 1000)
            # Skills can opt into the summary channel by returning a
            # ToolResult. Bare returns (dict, str, etc.) stay untouched.
            if isinstance(raw, ToolResult):
                result, summary = raw.result, raw.summary
            else:
                result, summary = raw, None
            return DispatchResult(
                executed=True,
                result=result,
                summary=summary,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return DispatchResult(
                executed=True,  # we tried; the tool itself errored
                error=f"{type(e).__name__}: {e}",
                duration_ms=duration_ms,
            )

    def make_executed_event(
        self,
        call_id: str,
        tool_name: str,
        result: DispatchResult,
    ) -> ToolCallExecuted:
        return ToolCallExecuted(
            call_id=call_id,
            tool_name=tool_name,
            result=result.result,
            error=result.error,
            duration_ms=result.duration_ms,
        )
