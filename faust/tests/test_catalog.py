"""
Catalog + category-remap tests.

Verifies:
  - Every loaded skill categorizes to one of the 7 sigil groups.
  - Each of the 7 groups has at least one skill (no dead dashboard tiles).
  - _raw_categorize preserves the legacy 11-category behavior.
  - SIGIL_GROUP_MAP covers every raw category the prefix table can emit.
  - Vision detection takes precedence over the exact-match defense entry.

Run with: python -m faust.tests.test_catalog
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.catalog import (
    SIGIL_GROUP_MAP,
    _categorize,
    _raw_categorize,
    build_catalog,
)
from faust.skills.loader import load_skills_into_registry
from faust.tools.registry import ToolRegistry


SIGIL_GROUPS: set[str] = {
    "wifi_ble", "sub_ghz", "nfc", "lf_rfid", "ir", "vision", "meta",
}


def _load_registry() -> ToolRegistry:
    reg = ToolRegistry()
    skills_dir = Path(__file__).resolve().parents[2] / "skills"
    load_skills_into_registry(skills_dir, reg)
    return reg


# ── Tests ───────────────────────────────────────────────────────

async def test_every_skill_maps_to_a_sigil_group():
    """Each of the 41 skills must land in exactly one of the 7 groups."""
    reg = _load_registry()
    assert len(reg.all()) >= 41, f"expected ≥41 skills, found {len(reg.all())}"

    bad: list[tuple[str, str]] = []
    for tool in reg.all():
        group = _categorize(tool.name)
        if group not in SIGIL_GROUPS:
            bad.append((tool.name, group))

    assert not bad, f"skills categorized outside the 7 groups: {bad}"
    print(f"✓ all {len(reg.all())} skills categorize to one of the 7 sigil groups")


async def test_all_seven_groups_are_populated():
    """No dashboard tile should be empty — every sigil group gets ≥1 skill."""
    reg = _load_registry()
    counts: dict[str, int] = {g: 0 for g in SIGIL_GROUPS}
    for tool in reg.all():
        counts[_categorize(tool.name)] += 1

    empty = [g for g, n in counts.items() if n == 0]
    assert not empty, f"empty sigil groups (dead tiles): {empty}. counts={counts}"
    print(f"✓ all 7 sigil groups populated: {counts}")


async def test_sigil_group_map_covers_all_raw_categories():
    """Every raw category the prefix table can emit must have a sigil mapping.
    Otherwise _categorize would silently drop skills into `meta` by accident."""
    from faust.agent.catalog import _CATEGORY_PREFIXES

    raw_categories = set(_CATEGORY_PREFIXES.values()) | {"vision"}
    missing = raw_categories - set(SIGIL_GROUP_MAP.keys())
    assert not missing, f"raw categories without SIGIL_GROUP_MAP entry: {missing}"
    print(f"✓ SIGIL_GROUP_MAP covers all {len(raw_categories)} raw categories")


async def test_raw_categorize_preserves_legacy_eleven_classes():
    """_raw_categorize is the old 11-category logic plus vision detection."""
    # Radio subsystems.
    assert _raw_categorize("wifi_scan") == "wifi"
    assert _raw_categorize("ble_scan") == "ble"
    assert _raw_categorize("nfc_read") == "nfc"
    assert _raw_categorize("rfid_clone") == "rfid"
    assert _raw_categorize("ir_capture") == "ir"
    assert _raw_categorize("subghz_decode") == "subghz"
    assert _raw_categorize("rf_spectrum_scan") == "rf"
    assert _raw_categorize("hid_payload") == "usb"
    # Network.
    assert _raw_categorize("nmap_scan") == "network"
    assert _raw_categorize("arp_scan") == "network"
    # Analysis.
    assert _raw_categorize("pcap_inspect") == "analysis"
    assert _raw_categorize("wpa_crack") == "analysis"
    assert _raw_categorize("hash_identify") == "analysis"
    # Defense (exact-match).
    assert _raw_categorize("deauth_detector") == "defense"
    assert _raw_categorize("rogue_ap_detector") == "defense"
    # Unknown → misc.
    assert _raw_categorize("add") == "misc"
    assert _raw_categorize("echo") == "misc"
    print("✓ _raw_categorize preserves legacy 11-class prefix/exact logic")


async def test_vision_detection_wins_over_exact_match():
    """`camera_ir_scan` used to be classified `defense` via the exact-match
    table. Vision detection must now take precedence so the skill lands in
    the `vision` sigil group, not `meta`."""
    assert _raw_categorize("camera_ir_scan") == "vision"
    assert _categorize("camera_ir_scan") == "vision"
    # Hypothetical future skill names.
    assert _categorize("vision_ocr") == "vision"
    assert _categorize("camera_qr_decode") == "vision"
    print("✓ vision detection overrides the exact-match table")


async def test_unknown_raw_category_falls_back_to_meta():
    """If _raw_categorize ever returns something outside SIGIL_GROUP_MAP,
    _categorize must not crash — it falls through to meta."""
    # `misc` is what _raw_categorize returns for unrecognized names and it
    # is intentionally NOT in SIGIL_GROUP_MAP, so `add` and `echo` (test
    # utility skills) land in meta via the fallback.
    assert _raw_categorize("add") == "misc"
    assert _categorize("add") == "meta"
    assert _categorize("echo") == "meta"
    # A total gibberish name still lands in meta, not a crash.
    assert _categorize("zzz_nonsense") == "meta"
    print("✓ unmapped raw categories fall back to meta")


async def test_build_catalog_emits_only_sigil_groups():
    """End-to-end: build_catalog uses the new _categorize and the resulting
    entries all carry one of the 7 group strings."""
    reg = _load_registry()
    entries = build_catalog(reg)
    for e in entries:
        assert e.category in SIGIL_GROUPS, (
            f"{e.name} got category={e.category!r}, expected one of {SIGIL_GROUPS}"
        )
    # Distinct category strings seen in output must be a subset of the 7.
    seen = {e.category for e in entries}
    assert seen <= SIGIL_GROUPS
    print(f"✓ build_catalog emits only sigil-group categories ({len(seen)} distinct)")


async def main():
    await test_every_skill_maps_to_a_sigil_group()
    await test_all_seven_groups_are_populated()
    await test_sigil_group_map_covers_all_raw_categories()
    await test_raw_categorize_preserves_legacy_eleven_classes()
    await test_vision_detection_wins_over_exact_match()
    await test_unknown_raw_category_falls_back_to_meta()
    await test_build_catalog_emits_only_sigil_groups()
    print("\nall catalog tests passed")


if __name__ == "__main__":
    asyncio.run(main())
