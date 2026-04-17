"""
Catalog taxonomy tests — the 7-sigil grouping.

Verifies:
  - Every SKILL.md in skills/ maps to one of the 7 sigil groups.
  - Specific critical mappings are stable (regression guard).
  - Unknown skill names fall back to `meta`, never a new bucket.
  - New skills picked up by prefix work even when not in _EXACT.
  - build_catalog() sorts by the canonical sigil order, then by name.

Run with: python -m faust.tests.test_taxonomy
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.catalog import (
    _CATEGORY_ORDER,
    _EXACT,
    _PREFIX,
    _categorize,
    build_catalog,
)
from faust.skills.loader import load_skills_into_registry
from faust.tools.registry import Tool, ToolRegistry


SIGIL_GROUPS: set[str] = {
    "wifi_ble", "sub_ghz", "nfc", "lf_rfid", "ir", "vision", "meta",
}


# ── Tests ───────────────────────────────────────────────────────

async def test_categorize_every_existing_skill_hits_one_of_seven():
    """Every real SKILL.md categorizes to one of the 7 sigil groups."""
    reg = ToolRegistry()
    skills_dir = Path(__file__).resolve().parents[2] / "skills"
    load_skills_into_registry(skills_dir, reg)
    assert len(reg.all()) >= 41, f"expected ≥41 skills, got {len(reg.all())}"

    bad: list[tuple[str, str]] = []
    for tool in reg.all():
        group = _categorize(tool.name)
        if group not in SIGIL_GROUPS:
            bad.append((tool.name, group))
    assert not bad, f"skills not in the 7 groups: {bad}"
    print(f"✓ all {len(reg.all())} skills map into the 7 sigil groups")


async def test_categorize_specific_mappings():
    """Pin the high-value mappings so a future prefix change can't silently
    drift a skill into the wrong dashboard tile."""
    assert _categorize("wifi_scan") == "wifi_ble"
    assert _categorize("nfc_read") == "nfc"
    assert _categorize("rfid_clone") == "lf_rfid"
    assert _categorize("subghz_decode") == "sub_ghz"
    assert _categorize("camera_ir_scan") == "vision"
    assert _categorize("pcap_inspect") == "wifi_ble"
    assert _categorize("imsi_catcher_detector") == "sub_ghz"
    assert _categorize("hash_identify") == "meta"
    print("✓ specific skill→sigil mappings held")


async def test_categorize_unknown_falls_back_to_meta():
    """Unknown skill names land in meta, never in a new misc bucket."""
    assert _categorize("some_future_skill") == "meta"
    assert _categorize("zzz_gibberish_name") == "meta"
    assert _categorize("add") == "meta"
    assert _categorize("echo") == "meta"
    print("✓ unknown skills default to meta")


async def test_prefix_fallback_for_new_skills():
    """Skills not in _EXACT but matching a _PREFIX still route correctly.
    Guarantees new skills can be added without touching catalog.py."""
    assert "wifi_beacon_hunter" not in _EXACT
    assert _categorize("wifi_beacon_hunter") == "wifi_ble"
    assert _categorize("ble_new_thing") == "wifi_ble"
    assert _categorize("nfc_future_skill") == "nfc"
    assert _categorize("subghz_future") == "sub_ghz"
    assert _categorize("camera_future") == "vision"
    assert _categorize("journal_audit") == "meta"
    print("✓ prefix fallback covers new skills without _EXACT entry")


async def test_catalog_sort_order():
    """build_catalog output is sorted by canonical sigil order, then by name."""
    reg = ToolRegistry()
    samples = [
        ("wifi_scan", "wifi_ble"),       # wifi_ble
        ("nfc_read", "nfc"),             # nfc
        ("rfid_clone", "lf_rfid"),       # lf_rfid
        ("subghz_decode", "sub_ghz"),    # sub_ghz
        ("ir_capture", "ir"),            # ir
        ("camera_ir_scan", "vision"),    # vision
        ("hash_identify", "meta"),       # meta
    ]
    for name, _ in samples:
        reg.register(Tool(
            name=name, description=f"d_{name}",
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda a: None, sensitivity="passive",
        ))

    entries = build_catalog(reg)
    got_order = [e.category for e in entries]
    expected_order = list(_CATEGORY_ORDER)
    assert got_order == expected_order, (
        f"category order wrong:\n  got={got_order}\n  want={expected_order}"
    )
    # Within-category: names sorted ascending (trivial here, one each).
    assert [e.name for e in entries] == [n for n, _ in
        sorted(samples, key=lambda s: (_CATEGORY_ORDER.index(s[1]), s[0]))]
    print("✓ build_catalog sorts by sigil order, then by name")


# ── Runner ─────────────────────────────────────────────────────

async def main():
    await test_categorize_every_existing_skill_hits_one_of_seven()
    await test_categorize_specific_mappings()
    await test_categorize_unknown_falls_back_to_meta()
    await test_prefix_fallback_for_new_skills()
    await test_catalog_sort_order()
    print("\nall taxonomy tests passed")


if __name__ == "__main__":
    asyncio.run(main())
