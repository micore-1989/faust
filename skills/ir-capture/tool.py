"""FAKE: synthetic IR capture/replay."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_hash, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action", "capture")
    protocol = args.get("protocol", "auto")
    code = args.get("code")
    repeat = int(args.get("repeat", 3))
    timeout_s = int(args.get("timeout_s", 15))

    rng = _rng(f"ir:{action}:{protocol}:{code}")

    if action == "capture":
        detected_protocol = protocol if protocol != "auto" else rng.choice(
            ["nec", "rc5", "sony", "samsung"]
        )
        # Generate a plausible code.
        code_hex = fake_hash(8, f"ir:{detected_protocol}").upper()
        timings = [9000, 4500] + [560 if rng.random() > 0.5 else 1690
                                   for _ in range(32)]
        return mark_synthetic({
            "action": "capture",
            "protocol": detected_protocol,
            "address": code_hex[:2],
            "command": code_hex[2:4],
            "code_hex": code_hex,
            "raw_timings_us": timings,
            "confidence": round(rng.uniform(0.85, 0.99), 2),
        })

    # replay
    return mark_synthetic({
        "action": "replay",
        "protocol": protocol,
        "code_hex": code or fake_hash(8, f"ir:replay:{protocol}").upper(),
        "repeats_sent": repeat,
        "success": True,
    })
