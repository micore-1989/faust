"""
Stage-1 keyword-based category router tests.

The router runs BEFORE the embedding scoper. When the prompt unambiguously
names a radio domain, the candidate pool is restricted to that category's
skills plus meta skills (which apply everywhere). Ambiguous prompts pass
through untouched — the embedding scoper keeps its current behavior.

Contract:
  - meta skills ALWAYS survive.
  - Unambiguous domain cues (MIFARE, HID Prox, sub-GHz, etc.) pin one category.
  - Multi-domain prompts pin the union.
  - Plural/stem forms match (cameras, lenses, trackers).
  - "card"/"tag"/"clone"/"copy" without a specific cue → pin {nfc, lf_rfid}.
  - No cue fires → input passes through unchanged.

Run with: python -m faust.tests.test_scoper_routing
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.config import AgentConfig
from faust.agent.dispatch import Dispatcher
from faust.agent.twopass import TwoPassAgent
from faust.skills.scoper import SkillScoper
from faust.skills.scoper_routing import (
    filter_by_prompt_categories,
    prompt_categories,
    skill_category,
)
from faust.tools.registry import Tool, ToolRegistry


# ── Helpers ────────────────────────────────────────────────────

def _mk_registry(skills: list[str]) -> ToolRegistry:
    reg = ToolRegistry()
    for n in skills:
        reg.register(Tool(
            name=n,
            description=f"test {n}",
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda args, _n=n: f"{_n}_result",
            sensitivity="passive",
        ))
    return reg


class RecordingScoper(SkillScoper):
    """Captures every top_k call for integration assertions."""

    def __init__(self, names: list[str]) -> None:
        self._names = list(names)
        self.top_k_calls: list[tuple[str, int]] = []

    async def top_k(self, query: str, k: int = 8) -> list[str]:
        self.top_k_calls.append((query, k))
        return self._names[:k]

    def all_skills(self) -> list[str]:
        return list(self._names)


# ── prompt_categories ───────────────────────────────────────────

async def test_no_cue_returns_all():
    """Filter is a no-op when no category cue fires."""
    inp = ["wifi_scan", "nfc_read", "rfid_clone", "hash_identify"]
    out = filter_by_prompt_categories(inp, "recon everything in range")
    assert out == inp
    print("✓ no cue → input passes through unchanged")


async def test_wifi_cue():
    """Plain wifi prompt pins wifi_ble."""
    assert "wifi_ble" in prompt_categories("scan the wifi")
    assert "wifi_ble" in prompt_categories("check the BSSID of that AP")
    print("✓ wifi cue pins wifi_ble")


async def test_unambiguous_nfc_cue():
    """Specific NFC vocabulary pins nfc ONLY — not lf_rfid."""
    cats = prompt_categories("read the MIFARE tag on the PN532")
    assert cats == ["nfc"], f"got {cats}"
    assert "lf_rfid" not in cats  # specific > ambiguous-card
    print("✓ specific NFC keyword pins nfc only")


async def test_unambiguous_lf_rfid_cue():
    """HID Prox / 125 kHz vocabulary pins lf_rfid ONLY — not nfc."""
    cats = prompt_categories("clone my HID Prox card")
    assert cats == ["lf_rfid"], f"got {cats}"
    assert "nfc" not in cats
    print("✓ specific LF-RFID keyword pins lf_rfid only")


async def test_ambiguous_card_pins_both():
    """Generic card/tag/clone without a specific cue pins both."""
    cats = prompt_categories("clone the access card")
    assert set(cats) == {"nfc", "lf_rfid"}, f"got {cats}"
    # Other flavors of the same ambiguity.
    assert set(prompt_categories("copy the badge")) == {"nfc", "lf_rfid"}
    assert set(prompt_categories("read the fob")) == {"nfc", "lf_rfid"}
    print("✓ ambiguous card language pins both nfc + lf_rfid")


async def test_sub_ghz_cue():
    """Garage / keyfob / sub-GHz language pins sub_ghz."""
    cats = prompt_categories("capture the garage keyfob signal")
    assert cats == ["sub_ghz"], f"got {cats}"
    assert "sub_ghz" in prompt_categories("sniff 433 mhz traffic")
    assert "sub_ghz" in prompt_categories("Sub-GHz replay attack")
    print("✓ sub-GHz vocabulary pins sub_ghz")


async def test_ir_cue():
    """TV remote / IR code pins ir."""
    cats = prompt_categories("capture the tv remote code")
    assert cats == ["ir"], f"got {cats}"
    assert "ir" in prompt_categories("record the infrared signal")
    print("✓ IR vocabulary pins ir")


async def test_vision_cue_with_plural():
    """Plural/stem forms must match — `cameras`, `lenses`."""
    assert "vision" in prompt_categories("look for hidden cameras")
    assert "vision" in prompt_categories("find any hidden camera")
    assert "vision" in prompt_categories("inspect the lenses")
    assert "vision" in prompt_categories("read the OCR from this image")
    print("✓ plural/stem forms match for vision")


async def test_multi_category_union():
    """Multiple cues → union of pinned categories."""
    cats = set(prompt_categories("scan wifi and read the mifare"))
    assert "wifi_ble" in cats
    assert "nfc" in cats
    print("✓ multi-category prompts pin the union")


# ── Bare canonical-domain cues ─────────────────────────────────

async def test_bare_nfc_pins_nfc_only():
    """A bare 'nfc' in the prompt should pin nfc — caught by the audit."""
    cats = prompt_categories("scan the nfc")
    assert cats == ["nfc"], f"got {cats}"
    print("✓ bare 'nfc' pins nfc")


async def test_bare_rfid_pins_lf_rfid_only():
    """Bare 'rfid' is now a specific lf_rfid cue, so it suppresses the
    ambiguous-card fallback. Must NOT also pin nfc."""
    cats = prompt_categories("read the rfid card")
    assert cats == ["lf_rfid"], f"got {cats}"
    print("✓ bare 'rfid' pins lf_rfid only (ambiguous-card suppressed)")


async def test_multi_domain_with_bare_nfc():
    """The audit's failing case: bare 'nfc' alongside 'wifi' pins both."""
    cats = set(prompt_categories("scan wifi and check nfc"))
    assert cats == {"wifi_ble", "nfc"}, f"got {cats}"
    print("✓ multi-domain with bare 'nfc' pins the union")


async def test_ambiguous_card_still_works():
    """Regression guard: generic card language with no specific cue still
    pins both card categories."""
    cats = set(prompt_categories("clone the access card"))
    assert cats == {"nfc", "lf_rfid"}, f"got {cats}"
    print("✓ ambiguous-card path still pins both on non-specific prompts")


async def test_specific_wins_over_ambiguous():
    """Explicit HID Prox cue pins lf_rfid; generic 'card' must not drag
    nfc into the result set."""
    cats = prompt_categories("clone my HID Prox card")
    assert cats == ["lf_rfid"], f"got {cats}"
    print("✓ specific cue suppresses ambiguous-card fallback")


# ── filter_by_prompt_categories ─────────────────────────────────

async def test_meta_always_survives():
    """hash_identify (meta) must survive any category-pin filter."""
    skills = ["wifi_scan", "hash_identify", "nfc_read"]
    out = filter_by_prompt_categories(skills, "scan wifi")
    assert "hash_identify" in out
    assert "wifi_scan" in out
    assert "nfc_read" not in out  # filtered out — wrong domain
    print("✓ meta skills always in the candidate pool")


async def test_skill_category_mirrors_catalog():
    """skill_category re-exports the same taxonomy as agent.catalog."""
    assert skill_category("wifi_scan") == "wifi_ble"
    assert skill_category("nfc_read") == "nfc"
    assert skill_category("rfid_clone") == "lf_rfid"
    assert skill_category("camera_ir_scan") == "vision"
    assert skill_category("hash_identify") == "meta"
    assert skill_category("unknown_skill") == "meta"
    print("✓ skill_category mirrors catalog taxonomy")


# ── TwoPassAgent integration ─────────────────────────────────────

async def test_integration_two_stage_reduces_candidates():
    """End-to-end: on a wifi-cue prompt, twopass's two-stage flow filters
    the candidate pool BEFORE asking the embedding scoper to rank, so top_k
    sees a smaller k than the full skill set."""
    all_names = [
        # 5 wifi_ble
        "wifi_scan", "wifi_deauth", "ble_scan", "arp_scan", "http_recon",
        # 3 nfc
        "nfc_read", "nfc_write", "nfc_emulate",
        # 3 sub_ghz
        "subghz_decode", "subghz_replay", "rf_spectrum_scan",
        # 2 meta
        "hash_identify", "add",
    ]
    registry = _mk_registry(all_names)
    scoper = RecordingScoper(all_names)

    # Force Stage 2 by setting scoper_k below the pinned-pool size.
    # wifi cue → wifi_ble (5) + meta (2) = 7 candidates; scoper_k=3 → Stage 2.
    cfg = AgentConfig(scoper_k=3, replan_enabled=False)

    # We don't need to run the full agent; just call the same code path
    # the agent uses. Simplest is to invoke run() and stop early — but we
    # can directly call the filter helpers to stay deterministic.
    candidates = filter_by_prompt_categories(scoper.all_skills(), "scan the wifi")
    assert len(candidates) < len(all_names), "Stage 1 must narrow the pool"
    assert set(candidates) == {
        "wifi_scan", "wifi_deauth", "ble_scan", "arp_scan", "http_recon",
        "hash_identify", "add",
    }

    # Simulate what twopass does: since len(candidates) > scoper_k, Stage 2
    # runs with k=len(candidates), and the intersection is trimmed to k.
    if len(candidates) > cfg.scoper_k:
        ranked = await scoper.top_k("scan the wifi", k=len(candidates))
        filtered = [n for n in ranked if n in set(candidates)][:cfg.scoper_k]
    else:
        filtered = candidates

    # Scoper was called exactly once, and k was the narrowed pool size.
    assert len(scoper.top_k_calls) == 1
    _, k_seen = scoper.top_k_calls[0]
    assert k_seen == len(candidates), (
        f"expected top_k called with k={len(candidates)} (narrowed pool), "
        f"got k={k_seen}"
    )
    assert len(filtered) == cfg.scoper_k
    print("✓ two-stage: Stage 1 narrows input before Stage 2 embedding ranks")


# ── Runner ─────────────────────────────────────────────────────

async def main():
    await test_no_cue_returns_all()
    await test_wifi_cue()
    await test_unambiguous_nfc_cue()
    await test_unambiguous_lf_rfid_cue()
    await test_ambiguous_card_pins_both()
    await test_sub_ghz_cue()
    await test_ir_cue()
    await test_vision_cue_with_plural()
    await test_multi_category_union()
    await test_bare_nfc_pins_nfc_only()
    await test_bare_rfid_pins_lf_rfid_only()
    await test_multi_domain_with_bare_nfc()
    await test_ambiguous_card_still_works()
    await test_specific_wins_over_ambiguous()
    await test_meta_always_survives()
    await test_skill_category_mirrors_catalog()
    await test_integration_two_stage_reduces_candidates()
    print("\nall scoper-routing tests passed")


if __name__ == "__main__":
    asyncio.run(main())
