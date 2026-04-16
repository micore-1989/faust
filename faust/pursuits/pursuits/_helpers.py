"""
Tiny helpers shared by Pursuit implementations.

Implementations dispatch through the real approver chain (TrustCache →
DisclosureApprover), which returns a DispatchResult dataclass. Mock
dispatchers in tests return plain dicts. `unwrap_result` normalizes both.
"""

from __future__ import annotations

import asyncio
from typing import Any


def unwrap_result(ret: Any) -> dict[str, Any]:
    """Return the payload dict from whatever dispatcher.dispatch yielded.

    - Real Dispatcher returns a `DispatchResult`; pull `.result` (may itself
      be a dict, a string, or None) and stash `.error` / `.executed` next to it.
    - Test fakes return a dict directly — pass it through.
    """
    if hasattr(ret, "executed") and hasattr(ret, "result"):
        payload = ret.result if isinstance(ret.result, dict) else {"value": ret.result}
        payload = dict(payload)
        payload.setdefault("_executed", ret.executed)
        if getattr(ret, "error", None):
            payload["_error"] = ret.error
        return payload
    if isinstance(ret, dict):
        return ret
    return {"value": ret}


async def interruptible_sleep(seconds: float, stop_event: asyncio.Event) -> bool:
    """Sleep for up to `seconds`, returning True if stop_event fired during
    the wait. Lets Pursuits check for stop between progress ticks without
    spin-polling."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False
