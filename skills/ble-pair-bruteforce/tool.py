"""FAKE: synthetic BLE PIN brute force."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    mac = args.get("mac", "00:00:00:00:00:00")
    pin_list = args.get("pin_list", "common")
    delay_ms = int(args.get("delay_ms", 500))

    rng = _rng(f"ble_brute:{mac}:{pin_list}")

    # Weak devices (older Bluetooth speakers, cheap lock) accept common PINs.
    weak = rng.random() < 0.4

    if weak:
        pin = rng.choice(["0000", "1234", "1111", "9999"])
        attempts = rng.randint(1, 8)
        return mark_synthetic({
            "mac": mac,
            "attempts": attempts,
            "success": True,
            "pin": pin,
            "duration_s": attempts * delay_ms // 1000,
        })

    # Device used rate limiting or secure pairing.
    return mark_synthetic({
        "mac": mac,
        "attempts": 20,
        "success": False,
        "reason": "device rate-limited or uses LE Secure Connections (ECDH)",
        "duration_s": 20 * delay_ms // 1000,
    })
