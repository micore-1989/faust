"""FAKE: synthetic BLE advertisement spam."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    mode = args.get("mode", "ios_proximity")
    duration_s = int(args.get("duration_s", 30))
    interval_ms = max(10, int(args.get("interval_ms", 20)))

    rng = _rng(f"ble_spam:{mode}")
    ads = (duration_s * 1000) // interval_ms

    return mark_synthetic({
        "mode": mode,
        "duration_s": duration_s,
        "advertisements_sent": ads + rng.randint(-ads // 20, ads // 20),
        "interval_ms": interval_ms,
        "success": True,
    })
