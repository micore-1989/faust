"""
Pursuit runner — shepherds an implementation's async-gen yields into
PursuitEvent broadcasts, a journal entry, and a persisted PursuitResult.

Async-generator protocol
------------------------
An implementation is:

    async def impl(params, dispatcher, stop_event) -> AsyncGenerator[
        PursuitYield | PursuitResultPartial, None
    ]:
        yield PursuitYield(progress=0.1, activity="started")
        await dispatcher.dispatch("wifi_scan", {...})
        yield PursuitYield(progress=0.8, activity="done scanning")
        yield PursuitResultPartial(summary="found 42 networks")

Rationale — PursuitResultPartial as a final yield (rather than
`return value` from an async generator, which cannot carry a value): it
keeps the iteration protocol simple (one `async for`) and the runner can
reason about completion by type rather than by catching StopAsyncIteration.

Runner responsibilities
-----------------------
- Emit PursuitStarted up front.
- Translate each PursuitYield into PursuitProgress and/or PursuitActivity
  events (both may fire from one yield). Elapsed time is monotonic.
- Swap the implementation's yield value for PursuitComplete when a
  PursuitResultPartial lands, then journal + persist.
- Convert stop_event trips into PursuitStopped(reason="user").
- Convert unhandled exceptions into PursuitStopped(reason="error").

The runner NEVER calls dispatcher.dispatch itself — that's the
implementation's job, and it's how destructive steps inside a Pursuit
still hit the existing Approver chain.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Optional

from .events import (
    PursuitActivity,
    PursuitComplete,
    PursuitProgress,
    PursuitStarted,
    PursuitStopped,
)
from .models import (
    Pursuit,
    PursuitResult,
    PursuitResultPartial,
    PursuitYield,
)
from .registry import IMPLEMENTATIONS


async def run_pursuit(
    pursuit: Pursuit,
    params: dict[str, Any],
    dispatcher: Any,
    bridge: Any,
    stop_event: asyncio.Event,
    *,
    run_id: Optional[str] = None,
    implementations: Optional[dict[str, Callable]] = None,
    journal: Any = None,
    storage: Any = None,
    time_source: Callable[[], float] = time.monotonic,
) -> Optional[PursuitResult]:
    """Run one Pursuit. Returns the PursuitResult on success, else None.

    Events are broadcast through `bridge.push_event(...)`. Mutates nothing
    on the dispatcher or state — callers own active_pursuits bookkeeping.
    """
    run_id = run_id or uuid.uuid4().hex
    impls = implementations if implementations is not None else IMPLEMENTATIONS
    started_monotonic = time_source()

    # 1. Announce the run. Bridge suppresses the WS emission; this event
    #    is consumed internally (or by future state-aware bridges).
    await bridge.push_event(
        PursuitStarted(run_id=run_id, pursuit_id=pursuit.id, params=dict(params))
    )

    # 2. Resolve implementation.
    impl = impls.get(pursuit.id)
    if impl is None:
        err = f"no implementation registered for pursuit {pursuit.id!r}"
        await _emit_error(bridge, journal, run_id, pursuit, err)
        return None

    # 3. Iterate. `PursuitResultPartial` is the terminal yield; everything
    #    else is a PursuitYield.
    terminal: Optional[PursuitResultPartial] = None
    try:
        agen = impl(params, dispatcher, stop_event)
        try:
            async for item in agen:
                if stop_event.is_set():
                    # Give the generator a chance to clean up.
                    await agen.aclose()
                    await bridge.push_event(
                        PursuitStopped(
                            run_id=run_id,
                            pursuit_id=pursuit.id,
                            reason="user",
                        )
                    )
                    return None

                if isinstance(item, PursuitResultPartial):
                    terminal = item
                    break  # drain any further yields
                elif isinstance(item, PursuitYield):
                    elapsed_s = int(time_source() - started_monotonic)
                    if item.progress is not None or item.eta_s is not None:
                        await bridge.push_event(
                            PursuitProgress(
                                run_id=run_id,
                                pursuit_id=pursuit.id,
                                progress=(
                                    float(item.progress)
                                    if item.progress is not None
                                    else 0.0
                                ),
                                elapsed_s=elapsed_s,
                                eta_s=item.eta_s,
                            )
                        )
                    if item.activity is not None:
                        await bridge.push_event(
                            PursuitActivity(
                                run_id=run_id,
                                pursuit_id=pursuit.id,
                                line=item.activity,
                            )
                        )
                # other yield types are ignored silently — implementations
                # that misuse the protocol shouldn't crash the runner
        finally:
            # Ensure the async generator is closed even on early break.
            await agen.aclose()

    except asyncio.CancelledError:
        # Propagated stop (e.g. via task.cancel()). Treat as user-initiated.
        await bridge.push_event(
            PursuitStopped(run_id=run_id, pursuit_id=pursuit.id, reason="user")
        )
        raise
    except Exception as e:  # noqa: BLE001 — runner must not crash the server
        err = f"{type(e).__name__}: {e}"
        await _emit_error(bridge, journal, run_id, pursuit, err)
        return None

    # 4. No terminal yield → synthesize one so the UI still gets a poster.
    if terminal is None:
        terminal = PursuitResultPartial(summary=f"{pursuit.title} completed")

    # 5. Journal the completion (so auditors see the Pursuit ran even
    #    though individual tool calls journaled themselves via Approver).
    journal_entry_id = ""
    if journal is not None:
        entry = journal.record(
            tool_name=f"pursuit.{pursuit.id}",
            arguments={"params": params, "run_id": run_id},
            sensitivity="passive",
            decision="auto",
            result_summary=terminal.summary,
        )
        # Journal returns either an object with .seq or nothing. Stamp whichever.
        seq = getattr(entry, "seq", None)
        journal_entry_id = str(seq) if seq is not None else ""

    # 6. Build and persist the result.
    completed_at = time.time()
    result = PursuitResult(
        run_id=run_id,
        pursuit_id=pursuit.id,
        summary=terminal.summary,
        journal_entry_id=journal_entry_id,
        artifacts=list(terminal.artifacts),
        completed_at=completed_at,
    )
    if storage is not None:
        try:
            storage.append(result)
        except Exception as e:  # noqa: BLE001
            # Storage failure is non-fatal — the run succeeded, we just
            # lose the durable record. Emit an activity line for ops.
            await bridge.push_event(
                PursuitActivity(
                    run_id=run_id,
                    pursuit_id=pursuit.id,
                    line=f"[warn] storage append failed: {e}",
                )
            )

    await bridge.push_event(
        PursuitComplete(
            run_id=run_id,
            pursuit_id=pursuit.id,
            summary=result.summary,
            journal_entry_id=journal_entry_id,
            artifacts=list(result.artifacts),
        )
    )
    return result


async def _emit_error(
    bridge: Any,
    journal: Any,
    run_id: str,
    pursuit: Pursuit,
    message: str,
) -> None:
    """Shared error-emission path: journal the failure (if possible) and
    broadcast PursuitStopped(reason='error')."""
    if journal is not None:
        try:
            journal.record(
                tool_name=f"pursuit.{pursuit.id}",
                arguments={"run_id": run_id},
                sensitivity="passive",
                decision="auto",
                error=message,
            )
        except Exception:
            pass
    await bridge.push_event(
        PursuitStopped(
            run_id=run_id,
            pursuit_id=pursuit.id,
            reason="error",
            error=message,
        )
    )
