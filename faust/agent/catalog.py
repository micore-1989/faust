"""
Skill catalog — lean skill representation for the Planner.

Mephisto's Pass-1 context contains only the catalog, not the full tool schemas.
Each skill becomes one compact entry: name + short description + category
+ sensitivity. At 19 skills this is ~600 tokens; at 100 skills it's still
~3000 — which is fine for the planning call, while Pass 2 only loads one
schema at a time.

The catalog is deterministic: built from the ToolRegistry. No LLM involvement.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..tools.registry import Sensitivity, ToolRegistry


# Category hints based on skill name prefixes. Used to group the catalog
# for readability in Mephisto's context. Unknown skills go in "misc".
_CATEGORY_PREFIXES: dict[str, str] = {
    # Radio subsystems
    "wifi_": "wifi",
    "ble_": "ble",
    "nfc_": "nfc",
    "rfid_": "rfid",
    "ir_": "ir",
    "subghz_": "subghz",
    "rf_": "rf",
    "hid_": "usb",

    # Network (IP-layer)
    "nmap_": "network",
    "arp_": "network",
    "dns_": "network",
    "http_": "network",
    "responder_": "network",

    # Offline analysis / cracking
    "pcap_": "analysis",
    "wpa_": "analysis",
    "hash_": "analysis",

    # Exact-match entries (no trailing underscore)
    "wardrive": "wifi",
    "deauth_detector": "defense",
    "rogue_ap_detector": "defense",
    "ble_tracker_scan": "defense",
    "probe_request_monitor": "defense",
    "imsi_catcher_detector": "defense",
    "camera_ir_scan": "defense",
    "spectrum_anomaly": "defense",
}


def _categorize(name: str) -> str:
    # Exact-name matches win over prefix matches (e.g. `ble_tracker_scan`
    # is defense, not ble, even though it starts with `ble_`).
    if name in _CATEGORY_PREFIXES:
        return _CATEGORY_PREFIXES[name]
    for prefix, cat in _CATEGORY_PREFIXES.items():
        if prefix.endswith("_") and name.startswith(prefix):
            return cat
    return "misc"


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
    # Sort by category then name for consistent presentation.
    entries.sort(key=lambda e: (e.category, e.name))
    return entries


def render_catalog(entries: list[CatalogEntry]) -> str:
    """Render the catalog as compact markdown for the planner's system prompt.

    Groups by category, one line per skill. Example output:

        ## Available skills

        ### wifi
        - wifi_scan [passive]: Scan nearby WiFi networks and clients
        - wifi_deauth [disruptive]: Deauthenticate a client from an AP

        ### ble
        - ble_scan [passive]: Enumerate nearby BLE devices
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
