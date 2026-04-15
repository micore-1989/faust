"""FAKE: synthetic LF RFID clone (EM4100 / HID Prox onto T5577)."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action", "read")
    source_id = args.get("source_id")
    card_type = args.get("card_type", "auto")

    rng = _rng(f"rfid_clone:{action}:{source_id}:{card_type}")

    detected_type = card_type if card_type != "auto" else rng.choice(["em4100", "hid_prox"])

    # Fake ID derived from input seed.
    card_id = source_id or f"{rng.randint(0, 0xFF):02X}{rng.randint(0, 0xFFFFFFFF):08X}"

    if action == "read":
        return mark_synthetic({
            "action": "read",
            "card_type": detected_type,
            "card_id": card_id,
            "facility_code": card_id[:2] if detected_type == "em4100" else None,
            "card_number": int(card_id[2:], 16) if len(card_id) > 2 else None,
            "raw_bits": "".join(rng.choice("01") for _ in range(64)),
            "signal_strength": rng.choice(["strong", "moderate", "weak"]),
        })

    # clone action
    write_ok = rng.random() < 0.92
    return mark_synthetic({
        "action": "clone",
        "source_id": card_id,
        "card_type": detected_type,
        "write_success": write_ok,
        "verify_match": write_ok,
    })
