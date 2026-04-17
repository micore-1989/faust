"""
Stage-1 keyword router — runs BEFORE the embedding scoper.

When the prompt unambiguously names a radio domain (e.g. "MIFARE",
"HID Prox", "sub-GHz"), the candidate pool is restricted to that category
plus `meta` skills (journal/audit utilities always apply). When no keyword
fires, all skills pass through and the embedding scoper handles ranking as
before. Strictly additive: ambiguous prompts behave identically to today.

See chunk 3 "two-stage routing" and faust-sigil-spec.md for the taxonomy.
"""

from __future__ import annotations

import re

from ..agent.catalog import _categorize


# Each entry: (compiled regex, category). Regex must be word-boundary aware
# so "wifi" doesn't fire on "wifiplaceholder". Plural/stem forms for common
# vocabulary use `?` or `(es)?` / `\w*` as noted in the spec.
_CATEGORY_CUES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b("
            r"wifi|wi-fi|802\.11|ssid|bssid|wpa|wpa2|handshakes?|deauth\w*|"
            r"rogue ap|evil twins?|evil portal|karma|pmkid|airodump|"
            r"beacons?|alfa|probe requests?|ble|bluetooth|gatt|"
            r"trackers?|airtags?|tiles?|arp|nmap|port scan|dns|"
            r"responder|ntlm|captive portal"
            r")\b",
            re.IGNORECASE,
        ),
        "wifi_ble",
    ),
    (
        re.compile(
            r"\b("
            r"nfc|13\.?56|mifare|ntag|iso ?14443|pn532|ndef"
            r")\b",
            re.IGNORECASE,
        ),
        "nfc",
    ),
    (
        re.compile(
            r"\b("
            r"rfid|125 ?khz|hid prox|em4100|em4305|t5577|rdm6300|ibutton|dallas key"
            r")\b",
            re.IGNORECASE,
        ),
        "lf_rfid",
    ),
    (
        re.compile(
            r"\b("
            r"sub-?ghz|315 ?mhz|433 ?mhz|868 ?mhz|915 ?mhz|"
            r"hackrf|cc1101|garage|keyfobs?|key fobs?|ook|ask|fsk|"
            r"imsi|spectrums?|jammers?"
            r")\b",
            re.IGNORECASE,
        ),
        "sub_ghz",
    ),
    (
        re.compile(
            r"\b("
            r"infrared|ir remote|ir code|tsop|38 ?khz|tv remote"
            r")\b",
            re.IGNORECASE,
        ),
        "ir",
    ),
    (
        re.compile(
            r"\b("
            r"cameras?|lens(es)?|photographs?|hidden cam\w*|"
            r"ocr|images?|pictures?|vlm"
            r")\b",
            re.IGNORECASE,
        ),
        "vision",
    ),
]


# Matches generic card-domain language. Used only when no specific NFC or
# LF-RFID cue fired — then both card categories pin (user probably doesn't
# know which frequency the card uses).
_AMBIGUOUS_CARD: re.Pattern[str] = re.compile(
    r"\b(card|tag|clone|copy|badge|access|fob)\b",
    re.IGNORECASE,
)


def skill_category(name: str) -> str:
    """Re-export the 7-sigil taxonomy so callers don't depend on catalog
    internals. Unknown names return 'meta' — same contract as _categorize."""
    return _categorize(name)


def prompt_categories(prompt: str) -> list[str]:
    """Return the categories pinned by keywords in `prompt`.

    Empty list means "no pin fired" — the caller should not filter.

    Behavior:
      - Each `_CATEGORY_CUES` regex contributes its category to the set
        when it matches.
      - The ambiguous-card rule adds BOTH nfc and lf_rfid when a generic
        card word appears AND neither nfc nor lf_rfid was already pinned
        by a specific cue.
    """
    cats: set[str] = set()
    for pattern, cat in _CATEGORY_CUES:
        if pattern.search(prompt):
            cats.add(cat)

    if "nfc" not in cats and "lf_rfid" not in cats:
        if _AMBIGUOUS_CARD.search(prompt):
            cats.add("nfc")
            cats.add("lf_rfid")

    return sorted(cats)


def filter_by_prompt_categories(
    skill_names: list[str],
    prompt: str,
) -> list[str]:
    """Restrict `skill_names` to skills in the pinned categories ∪ {meta}.

    When no cues fire, returns `skill_names` unchanged — the embedding
    scoper takes over. When cues fire, meta skills always survive.
    Preserves input order so the embedding stage downstream can still
    rank meaningfully.
    """
    pinned = prompt_categories(prompt)
    if not pinned:
        return list(skill_names)

    allowed = set(pinned) | {"meta"}
    return [n for n in skill_names if skill_category(n) in allowed]
