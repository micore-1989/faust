"""FAKE: synthetic NFC tag emulation."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import ago_iso, fake_uid, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action", "emulate_uid")
    uid = args.get("uid") or fake_uid(7, f"nfc_emulate:{action}")
    duration_s = int(args.get("duration_s", 60))

    rng = _rng(f"nfc_emulate:{action}:{uid}:{duration_s}")

    reads = rng.randint(0, 4)
    readers = [
        {
            "timestamp": ago_iso(duration_s - i * 10),
            "command": rng.choice(["GET_UID", "READ_BLOCK_0", "READ_BLOCK_1",
                                   "AUTH_KEY_A", "SELECT"]),
        }
        for i in range(reads)
    ]

    return mark_synthetic({
        "action": action,
        "uid": uid,
        "duration_s": duration_s,
        "reads_detected": reads,
        "readers": readers,
    })
