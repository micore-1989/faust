"""FAKE: synthetic MIFARE Classic key recovery."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_hash, fake_uid, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    attack = args.get("attack", "auto")
    known_key = args.get("known_key")
    known_sector = args.get("known_sector")
    target_sector = args.get("target_sector", -1)

    rng = _rng(f"mifare_crack:{attack}:{known_key or 'none'}:{target_sector}")
    uid = fake_uid(4, f"mifare_crack:{attack}")

    # MIFARE Classic is broken; attacks usually succeed against default-keyed cards.
    # Hardnested without known key tends to fail on PN532 (too slow).
    if attack == "hardnested" and not known_key:
        return mark_synthetic({
            "uid": uid,
            "attack_used": "hardnested",
            "success": False,
            "reason": "hardnested requires Proxmark3-class hardware; PN532 too slow",
        })

    attack_used = "darkside" if attack == "auto" else attack
    sectors_to_recover = 16 if target_sector == -1 else 1
    keys_recovered: dict[str, dict[str, str]] = {}
    for i in range(sectors_to_recover):
        sec = i if target_sector == -1 else int(target_sector)
        sec_seed = f"mifare_crack:{uid}:sec{sec}"
        keys_recovered[str(sec)] = {
            "key_a": fake_hash(12, f"{sec_seed}:a").upper(),
            "key_b": fake_hash(12, f"{sec_seed}:b").upper(),
        }

    return mark_synthetic({
        "uid": uid,
        "attack_used": attack_used,
        "keys_recovered": keys_recovered,
        "duration_s": 47 + rng.randint(-10, 20),
    })
