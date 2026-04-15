"""FAKE: synthetic NFC/RFID tag read."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_hash, fake_tag_type, fake_uid, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    timeout_s = int(args.get("timeout_s", 10))
    read_sectors = args.get("read_sectors", False)
    keys = args.get("keys") or []

    rng = _rng(f"nfc_read:{timeout_s}:{'sectors' if read_sectors else 'header'}")

    tag_type = fake_tag_type(f"nfc_read:{timeout_s}")
    uid_len = 7 if "NTAG" in tag_type or "Ultralight" in tag_type else 4
    uid = fake_uid(uid_len, f"nfc_read:{timeout_s}")

    result: dict[str, Any] = {
        "uid": uid,
        "uid_length": uid_len,
        "tag_type": tag_type,
        "atqa": "0044" if "NTAG" in tag_type else "0004",
        "sak": "00" if "NTAG" in tag_type else "08",
        "ndef": None,
        "sectors": None,
    }

    # NTAGs often have NDEF; Classic doesn't by default.
    if "NTAG" in tag_type and rng.random() < 0.6:
        result["ndef"] = [{"type": "uri", "payload": "https://example.com/tag"}]

    # For Classic, maybe return sector data if requested and keys work.
    if read_sectors and "Classic" in tag_type:
        default_keys = ["FFFFFFFFFFFF", "A0A1A2A3A4A5", "B0B1B2B3B4B5"]
        tried = default_keys + list(keys)
        if rng.random() < 0.7:
            # Some sectors read successfully.
            result["sectors"] = [
                {
                    "sector": i,
                    "key_a": tried[0],
                    "blocks": [
                        {"block": i * 4 + j, "data": fake_hash(32, f"blk:{uid}:{i}:{j}")}
                        for j in range(4)
                    ],
                }
                for i in range(rng.randint(2, 8))
            ]

    return mark_synthetic(result)
