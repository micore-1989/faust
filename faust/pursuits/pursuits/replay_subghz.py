"""
Replay Sub-GHz Remote Pursuit implementation.

Spec §10.4:
    "Capture a garage door or keyfob transmission, analyze, and replay."

Three dispatches to `subghz_replay`: action=capture, action=analyze,
action=replay. The skill accepts frequency_mhz, duration_s, and
capture_file; both captures and replays are handled by the same skill
through its `action` param.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..models import PursuitResultPartial, PursuitYield
from ._helpers import unwrap_result


LISTEN_S = 10
ARTIFACT_DIR = Path("/tmp")


async def run(params: dict[str, Any], dispatcher, stop_event: asyncio.Event):
    """Capture a signal at `frequency_mhz` for 10s, analyze the modulation,
    then replay the capture on the same frequency."""
    freq = params.get("frequency_mhz", "433.92")
    try:
        freq_float = float(freq)
    except (TypeError, ValueError):
        freq_float = 433.92

    run_id = params.get("_run_id", "current")
    capture_file = str(ARTIFACT_DIR / f"faust-subghz-{run_id}.iq")

    yield PursuitYield(
        progress=0.05,
        activity=f"Listening on {freq} MHz for {LISTEN_S}s...",
    )

    if stop_event.is_set():
        return

    capture = unwrap_result(await dispatcher.dispatch("subghz_replay", {
        "action": "capture",
        "frequency_mhz": freq_float,
        "duration_s": LISTEN_S,
        "capture_file": capture_file,
    }))

    captured_path = capture.get("capture_file", capture_file)
    capture_duration = capture.get("duration_s", LISTEN_S)
    yield PursuitYield(
        progress=0.45,
        activity=f"Captured {capture_duration}s → {captured_path}",
    )

    if stop_event.is_set():
        return

    analysis = unwrap_result(await dispatcher.dispatch("subghz_replay", {
        "action": "analyze",
        "capture_file": captured_path,
        "frequency_mhz": freq_float,
    }))
    modulation = analysis.get("modulation", "unknown")
    bitrate = analysis.get("bitrate")
    line = f"Analysis: {modulation}"
    if bitrate:
        line += f" · bitrate {bitrate}"
    yield PursuitYield(progress=0.7, activity=line)

    if stop_event.is_set():
        return

    yield PursuitYield(progress=0.8, activity=f"Replaying on {freq} MHz...")

    replay = unwrap_result(await dispatcher.dispatch("subghz_replay", {
        "action": "replay",
        "capture_file": captured_path,
        "frequency_mhz": freq_float,
    }))
    replay_duration = replay.get("duration_s", capture_duration)
    yield PursuitYield(progress=1.0, activity=f"Replayed {replay_duration}s")

    yield PursuitResultPartial(
        summary=f"Captured and replayed on {freq} MHz",
        artifacts=[captured_path],
    )
