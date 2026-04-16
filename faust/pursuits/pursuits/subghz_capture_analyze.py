"""
Sub-GHz Capture + Analyze Pursuit implementation.

Spec §10.4:
    "Capture IQ data on a chosen frequency, demodulate, and extract
    recognizable signal patterns."

Two phases:
    0.0 → 0.7  capture via `subghz_replay` action=capture
    0.7 → 1.0  analyze via `subghz_decode` (known-protocol decoder)

Artifact is the IQ capture file plus a text dump of the decoder's output.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..models import PursuitResultPartial, PursuitYield
from ._helpers import interruptible_sleep, unwrap_result


ARTIFACT_DIR = Path("/tmp")


async def run(params: dict[str, Any], dispatcher, stop_event: asyncio.Event):
    """Capture IQ for `capture_seconds`, then decode with subghz_decode."""
    freq = params.get("frequency_mhz", "433.92")
    try:
        freq_float = float(freq)
    except (TypeError, ValueError):
        freq_float = 433.92

    capture_seconds = int(params.get("capture_seconds", 120))
    run_id = params.get("_run_id", "current")
    iq_path = ARTIFACT_DIR / f"faust-subghz-ca-{run_id}.iq"
    analysis_path = ARTIFACT_DIR / f"faust-subghz-ca-{run_id}.analysis.json"

    yield PursuitYield(
        progress=0.05,
        activity=f"Starting capture @ {freq} MHz · {capture_seconds}s",
    )

    # Phase 1 — capture (0.0 → 0.7). The capture is synchronous from the
    # skill's perspective; update progress in-place so the UI doesn't go
    # silent for two minutes.
    capture_task = asyncio.create_task(dispatcher.dispatch("subghz_replay", {
        "action": "capture",
        "frequency_mhz": freq_float,
        "duration_s": capture_seconds,
        "capture_file": str(iq_path),
    }))
    ticks = max(3, min(12, capture_seconds // 5))
    tick_s = capture_seconds / ticks
    for i in range(ticks):
        if capture_task.done():
            break
        if await interruptible_sleep(tick_s, stop_event):
            capture_task.cancel()
            return
        yield PursuitYield(
            progress=min(0.7, 0.05 + (i + 1) * (0.65 / ticks)),
            eta_s=int(max(0, capture_seconds - (i + 1) * tick_s)),
            activity=f"Capturing... {int((i + 1) * tick_s)}s / {capture_seconds}s",
        )
    capture_result = unwrap_result(await capture_task)
    iq_actual = capture_result.get("capture_file", str(iq_path))
    yield PursuitYield(progress=0.72, activity=f"Capture complete → {iq_actual}")

    if stop_event.is_set():
        return

    # Phase 2 — analyze (0.7 → 1.0).
    yield PursuitYield(progress=0.8, activity="Decoding known protocols...")
    decode = unwrap_result(await dispatcher.dispatch("subghz_decode", {
        "capture_file": iq_actual,
        "frequency_mhz": freq_float,
    }))
    protocol_family = (
        decode.get("protocol_family")
        or decode.get("protocol")
        or (decode.get("detected") or ["unknown"])[0]
    )

    try:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(
            json.dumps(decode, indent=2, default=str),
            encoding="utf-8",
        )
        analysis_artifact = str(analysis_path)
    except Exception:
        analysis_artifact = ""

    yield PursuitYield(progress=1.0, activity=f"Detected: {protocol_family}")
    summary = (
        f"Captured {capture_seconds}s @ {freq} MHz, "
        f"detected {protocol_family}"
    )
    artifacts = [iq_actual]
    if analysis_artifact:
        artifacts.append(analysis_artifact)
    yield PursuitResultPartial(summary=summary, artifacts=artifacts)
