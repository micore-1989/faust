"""
Clone Access Credential Pursuit implementation.

Spec §10.4:
    "Read an LF RFID card (T5577/EM4100/HID Prox) and write its data to
    a blank card."

Two dispatches through `rfid_clone`: first action=read to read the source,
then action=clone to write the captured ID to a blank T5577. Short,
linear Pursuit — ~2 minutes wall clock with two card-present waits.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..models import PursuitResultPartial, PursuitYield
from ._helpers import unwrap_result


READ_TIMEOUT_S = 30
WRITE_TIMEOUT_S = 30


async def run(params: dict[str, Any], dispatcher, stop_event: asyncio.Event):
    """Read the source credential, yield its UID, then write to a blank
    T5577 with a second card-present wait."""
    yield PursuitYield(progress=0.05, activity="Present source card — waiting up to 30s...")

    if stop_event.is_set():
        return

    read = unwrap_result(await dispatcher.dispatch(
        "rfid_clone",
        {"action": "read", "card_type": "auto", "timeout_s": READ_TIMEOUT_S},
    ))

    if read.get("_error") or not read.get("uid"):
        err = read.get("_error") or read.get("error") or "no card detected"
        yield PursuitYield(progress=0.5, activity=f"Read failed: {err}")
        yield PursuitResultPartial(summary=f"Clone failed at read step: {err}", artifacts=[])
        return

    uid = read.get("uid", "<unknown>")
    facility = read.get("facility_code")
    card_type = read.get("card_type", "auto")
    activity = f"Source read · UID {uid}"
    if facility is not None:
        activity += f" · facility {facility}"
    yield PursuitYield(progress=0.45, activity=activity)

    if stop_event.is_set():
        return

    yield PursuitYield(progress=0.5, activity="Present BLANK T5577 — waiting up to 30s...")

    write = unwrap_result(await dispatcher.dispatch(
        "rfid_clone",
        {
            "action": "clone",
            "card_type": card_type,
            "source_id": uid,
            "timeout_s": WRITE_TIMEOUT_S,
        },
    ))

    if write.get("_error") or write.get("error"):
        err = write.get("_error") or write.get("error")
        yield PursuitYield(progress=0.95, activity=f"Write failed: {err}")
        yield PursuitResultPartial(
            summary=f"Cloned {uid} read OK but write failed: {err}",
            artifacts=[],
        )
        return

    yield PursuitYield(progress=1.0, activity=f"Cloned {uid} to blank card")
    yield PursuitResultPartial(
        summary=f"Cloned {uid} to blank card",
        artifacts=[],
    )
