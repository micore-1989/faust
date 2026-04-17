"""
build_catalog end-to-end tests.

Core `_categorize` behavior lives in test_taxonomy.py; this file covers:
  - All seven sigil groups are populated by the current skills/ tree (no
    dead dashboard tiles).
  - build_catalog only emits canonical sigil-group category strings.

Run with: python -m faust.tests.test_catalog
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.catalog import _categorize, build_catalog
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

async def test_all_seven_groups_are_populated():
    """No dashboard tile should be empty — every sigil group gets ≥1 skill."""
    reg = _load_registry()
    counts: dict[str, int] = {g: 0 for g in SIGIL_GROUPS}
    for tool in reg.all():
        counts[_categorize(tool.name)] += 1

    empty = [g for g, n in counts.items() if n == 0]
    assert not empty, f"empty sigil groups (dead tiles): {empty}. counts={counts}"
    print(f"✓ all 7 sigil groups populated: {counts}")


async def test_build_catalog_emits_only_sigil_groups():
    """End-to-end: build_catalog emits one of the 7 group strings per entry."""
    reg = _load_registry()
    entries = build_catalog(reg)
    for e in entries:
        assert e.category in SIGIL_GROUPS, (
            f"{e.name} got category={e.category!r}, expected one of {SIGIL_GROUPS}"
        )
    seen = {e.category for e in entries}
    assert seen <= SIGIL_GROUPS
    print(f"✓ build_catalog emits only sigil-group categories ({len(seen)} distinct)")


async def main():
    await test_all_seven_groups_are_populated()
    await test_build_catalog_emits_only_sigil_groups()
    print("\nall catalog tests passed")


if __name__ == "__main__":
    asyncio.run(main())
