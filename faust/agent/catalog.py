"""
Skill catalog — lean skill representation for the Planner.

Mephisto's Pass-1 context contains only the catalog, not the full tool schemas.
Each skill becomes one compact entry: name + short description + category
+ sensitivity. At 19 skills this is ~600 tokens; at 100 skills it's still
~3000 — which is fine for the planning call, while Pass 2 only loads one
schema at a time.

The catalog is deterministic: built from the ToolRegistry. No LLM involvement.

Taxonomy: every skill maps to one of exactly seven dashboard sigil groups
(see faust-sigil-spec.md §1): wifi_ble | sub_ghz | nfc | lf_rfid | ir |
vision | meta. Categorization is a two-tier lookup — `_EXACT` pins every
current skill explicitly, `_PREFIX` handles stem-based matches for future
skills that follow the naming convention. Unknown skills fall through to
`meta` (the journal/audit tile) rather than a new bucket.

`_EXACT` and `_PREFIX` are module-level constants; import them when you need
to mirror this taxonomy elsewhere (e.g. scoper routing).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..tools.registry import Sensitivity, ToolRegistry


# Canonical order the dashboard renders sigils. build_catalog() sorts by
# this so the planner sees skills in the same order the operator does.
_CATEGORY_ORDER: list[str] = [
    "wifi_ble", "nfc", "lf_rfid", "sub_ghz", "ir", "vision", "meta",
]


# Every current skill (as of the skills/ directory at commit time). When a
# name appears both here and via a _PREFIX match, _EXACT wins. Defense-style
# skills route to the category whose hardware they drive — rogue_ap_detector
# is WiFi, imsi_catcher_detector is sub-GHz, camera_ir_scan is vision, etc.
_EXACT: dict[str, str] = {
    # wifi_ble — WiFi radios
    "wifi_scan": "wifi_ble",
    "wifi_deauth": "wifi_ble",
    "wifi_beacon_spam": "wifi_ble",
    "wifi_channel_analyze": "wifi_ble",
    "wifi_evil_portal": "wifi_ble",
    "wifi_handshake_capture": "wifi_ble",
    "wifi_karma": "wifi_ble",
    "wifi_pmkid_capture": "wifi_ble",
    "wardrive": "wifi_ble",
    # wifi_ble — BLE radio (same antenna stack)
    "ble_scan": "wifi_ble",
    "ble_service_enum": "wifi_ble",
    "ble_pair_bruteforce": "wifi_ble",
    "ble_spam": "wifi_ble",
    "ble_tracker_scan": "wifi_ble",
    # wifi_ble — IP-layer skills (the WiFi radio gets you on a network)
    "arp_scan": "wifi_ble",
    "arp_spoof": "wifi_ble",
    "dns_hijack": "wifi_ble",
    "http_recon": "wifi_ble",
    "nmap_scan": "wifi_ble",
    "responder_poison": "wifi_ble",
    "pcap_inspect": "wifi_ble",
    "wpa_crack": "wifi_ble",
    "hid_payload": "wifi_ble",
    # wifi_ble — defense-flavored skills driven by WiFi/BLE radios
    "deauth_detector": "wifi_ble",
    "rogue_ap_detector": "wifi_ble",
    "probe_request_monitor": "wifi_ble",

    # sub_ghz — HackRF / CC1101 skills
    "subghz_decode": "sub_ghz",
    "subghz_replay": "sub_ghz",
    "rf_spectrum_scan": "sub_ghz",
    "spectrum_anomaly": "sub_ghz",
    "imsi_catcher_detector": "sub_ghz",

    # nfc — PN532 / 13.56 MHz
    "nfc_read": "nfc",
    "nfc_write": "nfc",
    "nfc_emulate": "nfc",
    "nfc_crack_mifare": "nfc",

    # lf_rfid — 125 kHz T5577 / RDM6300
    "rfid_clone": "lf_rfid",

    # ir — TSOP / IR LED
    "ir_capture": "ir",

    # vision — picamera2 / ML image pipeline
    "camera_ir_scan": "vision",

    # meta — journaling, ID-lookup, test utilities
    "hash_identify": "meta",
    "add": "meta",
    "echo": "meta",
}


# Stem-prefix fallback for skills not in _EXACT. Checked in iteration order;
# on Python 3.7+ that matches insertion order, so put more-specific prefixes
# first if two would otherwise both match.
_PREFIX: dict[str, str] = {
    # wifi_ble
    "wifi_":     "wifi_ble",
    "ble_":      "wifi_ble",
    "arp_":      "wifi_ble",
    "dns_":      "wifi_ble",
    "http_":     "wifi_ble",
    "nmap_":     "wifi_ble",
    "responder_": "wifi_ble",
    "pcap_":     "wifi_ble",
    "wpa_":      "wifi_ble",
    "hid_":      "wifi_ble",
    # nfc
    "nfc_":      "nfc",
    # lf_rfid
    "rfid_":     "lf_rfid",
    # sub_ghz
    "subghz_":   "sub_ghz",
    "rf_":       "sub_ghz",
    "spectrum_": "sub_ghz",
    # ir
    "ir_":       "ir",
    # vision
    "camera_":   "vision",
    "image_":    "vision",
    "ocr_":      "vision",
    # meta
    "hash_":     "meta",
    "journal_":  "meta",
}


def _categorize(name: str) -> str:
    """Return one of the 7 sigil groups for `name`.

    Priority: _EXACT → _PREFIX → `meta` fallback. Never returns any string
    outside the 7 canonical groups.
    """
    if name in _EXACT:
        return _EXACT[name]
    for prefix, cat in _PREFIX.items():
        if name.startswith(prefix):
            return cat
    return "meta"


@dataclass
class CatalogEntry:
    name: str
    description: str
    category: str
    sensitivity: Sensitivity
    typical_duration_s: int | None = None


def build_catalog(
    registry: ToolRegistry,
    allowed_names: list[str] | None = None,
) -> list[CatalogEntry]:
    """Build a catalog from the registry.

    If `allowed_names` is given (e.g. from the scoper), only those skills
    appear. Use this to further trim the planning context.

    Sorted by the canonical sigil order (wifi_ble first, meta last), then
    by skill name within each group — same order the operator sees on the
    dashboard.
    """
    entries: list[CatalogEntry] = []
    for tool in registry.all():
        if allowed_names is not None and tool.name not in allowed_names:
            continue
        entries.append(CatalogEntry(
            name=tool.name,
            description=tool.description,
            category=_categorize(tool.name),
            sensitivity=tool.sensitivity,
            typical_duration_s=tool.typical_duration_s,
        ))
    cat_rank = {cat: i for i, cat in enumerate(_CATEGORY_ORDER)}
    entries.sort(key=lambda e: (cat_rank.get(e.category, len(cat_rank)), e.name))
    return entries


def render_catalog(entries: list[CatalogEntry]) -> str:
    """Render the catalog as compact markdown for the planner's system prompt.

    Groups by category, one line per skill. Example output:

        ## Available skills

        ### wifi_ble
        - wifi_scan [passive ~15s]: Scan nearby WiFi networks and clients
        - wifi_deauth [disruptive ~10s]: Deauthenticate a client from an AP

        ### nfc
        - nfc_read [passive ~5s]: Read a 13.56 MHz NFC tag
    """
    if not entries:
        return "## Available skills\n\n(none)"

    lines: list[str] = ["## Available skills", ""]
    current_cat: str | None = None

    for e in entries:
        if e.category != current_cat:
            if current_cat is not None:
                lines.append("")  # blank line between categories
            lines.append(f"### {e.category}")
            current_cat = e.category
        # Truncate to the first sentence or 120 chars — whichever is shorter.
        # Keeps the catalog compact as the registry grows.
        desc = e.description.strip().replace("\n", " ")
        period = desc.find(".")
        if 0 < period < 120:
            desc = desc[:period + 1]
        elif len(desc) > 120:
            desc = desc[:117] + "..."
        duration = f" ~{e.typical_duration_s}s" if e.typical_duration_s else ""
        lines.append(f"- {e.name} [{e.sensitivity}{duration}]: {desc}")

    return "\n".join(lines)
