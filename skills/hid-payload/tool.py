"""FAKE: synthetic BadUSB HID payload execution."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    payload_file = args.get("payload_file")
    raw_script = args.get("raw_script")
    target_os = args.get("target_os", "auto")
    typing_speed_wpm = int(args.get("typing_speed_wpm", 400))

    rng = _rng(f"hid_payload:{payload_file}:{target_os}")

    if target_os == "auto":
        target_os = rng.choice(["macos", "windows", "linux"])

    # Estimate keystrokes from payload length.
    if raw_script:
        keystrokes = len(raw_script)
    elif payload_file:
        keystrokes = rng.randint(200, 800)
    else:
        keystrokes = 0

    duration_ms = int(keystrokes / (typing_speed_wpm * 5 / 60) * 1000) if keystrokes else 0

    return mark_synthetic({
        "payload_file": payload_file or "<inline>",
        "target_os": target_os,
        "executed": keystrokes > 0,
        "keystrokes_sent": keystrokes,
        "duration_ms": duration_ms,
        "detected_usb_host": {
            "macos": "Darwin 23.6.0",
            "windows": "Windows 11 Build 22631",
            "linux": "Linux 6.5.0",
        }.get(target_os, "unknown"),
    })
