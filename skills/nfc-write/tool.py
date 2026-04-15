"""FAKE: synthetic NFC write."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_tag_type, fake_uid, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    mode = args.get("mode", "ndef_uri")
    uri = args.get("uri")
    text = args.get("text")
    sector = args.get("sector")
    data_hex = args.get("data_hex")

    rng = _rng(f"nfc_write:{mode}:{uri or text or data_hex}")

    tag_type = "NTAG215" if mode.startswith("ndef") else fake_tag_type(f"nfc_write:{mode}")
    uid = fake_uid(7 if "NTAG" in tag_type else 4, f"nfc_write:{mode}")

    # Estimate bytes written.
    if mode == "ndef_uri" and uri:
        bytes_written = len(uri) + 5
    elif mode == "ndef_text" and text:
        bytes_written = len(text) + 6
    elif mode == "ndef_wifi":
        bytes_written = 60
    elif mode == "mifare_sector":
        bytes_written = 48  # 3 data blocks * 16 bytes
    else:
        bytes_written = 16

    # Writes usually succeed unless tag is locked.
    locked = rng.random() < 0.05
    if locked:
        return mark_synthetic({
            "mode": mode,
            "tag_uid": uid,
            "tag_type": tag_type,
            "bytes_written": 0,
            "verified": False,
            "error": "tag is locked / write-protected",
        })

    return mark_synthetic({
        "mode": mode,
        "tag_uid": uid,
        "tag_type": tag_type,
        "bytes_written": bytes_written,
        "verified": True,
    })
