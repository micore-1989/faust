"""FAKE: synthetic hash type identification (deterministic)."""
from __future__ import annotations

import re
from typing import Any

from faust.skills.fakes import mark_synthetic


_HEX = re.compile(r"^[0-9a-fA-F]+$")


def execute(args: dict[str, Any]) -> dict[str, Any]:
    h = str(args.get("hash_string", "")).strip()
    candidates = []

    if h.startswith("$2a$") or h.startswith("$2b$") or h.startswith("$2y$"):
        candidates.append({"type": "bcrypt", "hashcat_mode": 3200,
                           "john_format": "bcrypt", "confidence": "high"})
    elif h.startswith("$6$"):
        candidates.append({"type": "sha512crypt", "hashcat_mode": 1800,
                           "john_format": "sha512crypt", "confidence": "high"})
    elif h.startswith("$5$"):
        candidates.append({"type": "sha256crypt", "hashcat_mode": 7400,
                           "john_format": "sha256crypt", "confidence": "high"})
    elif h.startswith("$1$"):
        candidates.append({"type": "md5crypt", "hashcat_mode": 500,
                           "john_format": "md5crypt", "confidence": "high"})
    elif _HEX.match(h):
        # Length-based guesses.
        L = len(h)
        if L == 32:
            candidates.append({"type": "MD5", "hashcat_mode": 0,
                               "john_format": "raw-md5", "confidence": "high"})
            candidates.append({"type": "NTLM", "hashcat_mode": 1000,
                               "confidence": "medium"})
        elif L == 40:
            candidates.append({"type": "SHA1", "hashcat_mode": 100,
                               "confidence": "high"})
        elif L == 64:
            candidates.append({"type": "SHA256", "hashcat_mode": 1400,
                               "confidence": "high"})
        elif L == 128:
            candidates.append({"type": "SHA512", "hashcat_mode": 1700,
                               "confidence": "high"})

    if not candidates:
        candidates.append({"type": "unknown", "confidence": "none",
                           "note": "doesn't match common patterns"})

    return mark_synthetic({
        "hash": h,
        "candidates": candidates,
    })
