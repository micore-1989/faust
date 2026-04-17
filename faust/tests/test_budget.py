"""
Pass 1 token-budget trimming tests.

Keeps the rendered catalog from overflowing Hailo's 2048-token window.
Drops from the tail (least-used categories first, because build_catalog
sorts by _CATEGORY_ORDER). Surfaces a safety_note when anything is hidden.

Run with: python -m faust.tests.test_budget
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall
from faust.agent.budget import (
    _CHARS_PER_TOK,
    catalog_budget_tokens,
    estimate_tokens,
    trim_catalog_to_budget,
)
from faust.agent.catalog import build_catalog, render_catalog
from faust.agent.config import AgentConfig
from faust.agent.planner import Planner
from faust.skills.loader import load_skills_into_registry
from faust.tools.registry import Tool, ToolRegistry


# ── estimate_tokens ─────────────────────────────────────────────

async def test_estimate_tokens_monotonic():
    """Longer strings always yield larger estimates."""
    assert estimate_tokens("hi") < estimate_tokens("hi there friend")
    assert estimate_tokens("a" * 100) < estimate_tokens("a" * 1000)
    # The empty string still costs at least 1 token so downstream arithmetic
    # never divides by zero or claims 0 tokens for a present string.
    assert estimate_tokens("") >= 1
    print("✓ estimate_tokens is monotonic on length")


# ── catalog_budget_tokens ───────────────────────────────────────

async def test_budget_positive_under_normal_load():
    """Realistic-size inputs leave healthy room for the catalog."""
    budget = catalog_budget_tokens(
        context_window=2048,
        system_prompt="x" * 1200,   # ~343 tokens
        schema_str="y" * 1200,      # ~343 tokens
        user_prompt="z" * 200,      # ~58 tokens
        conversation_text="",
        response_reserve=256,
    )
    assert budget > 300, f"expected >300 tokens for catalog, got {budget}"
    print(f"✓ normal-load budget leaves {budget} tokens for the catalog")


async def test_budget_zero_when_fixed_overhead_exceeds_window():
    """Overflowing fixed overhead clamps at 0, never goes negative."""
    budget = catalog_budget_tokens(
        context_window=2048,
        system_prompt="x" * 10000,  # already over the window alone
        schema_str="y" * 5000,
        user_prompt="z" * 500,
        conversation_text="",
        response_reserve=256,
    )
    assert budget == 0, f"expected clamped 0, got {budget}"
    print("✓ budget clamps to 0 when fixed overhead exceeds the window")


# ── trim_catalog_to_budget ──────────────────────────────────────

async def test_trim_no_op_when_under_budget():
    """Short rendered text under budget is returned unchanged."""
    rendered = "## Available skills\n\n### wifi_ble\n- wifi_scan [passive]: scan"
    out, dropped = trim_catalog_to_budget(rendered, budget_tokens=1000)
    assert out == rendered
    assert dropped == 0
    print("✓ under-budget catalog is untouched")


async def test_trim_drops_tail_and_counts():
    """With a tight budget, the tail of the catalog is trimmed and the drop
    count reflects the number of skill lines removed (not headers)."""
    rendered = "\n".join([
        "## Available skills",
        "",
        "### wifi_ble",
        "- wifi_scan [passive ~15s]: Scan nearby WiFi networks and clients",
        "- wifi_deauth [disruptive ~10s]: Deauthenticate a client",
        "",
        "### nfc",
        "- nfc_read [passive ~5s]: Read a 13.56 MHz NFC tag",
        "- nfc_write [active ~5s]: Write a 13.56 MHz NFC tag",
        "- nfc_emulate [active ~5s]: Emulate an NFC tag",
    ])
    # Target: 2 of 5 skill lines dropped. Pick a budget that fits the first
    # 3 skills plus their headers but not the rest.
    budget = estimate_tokens("\n".join([
        "## Available skills",
        "",
        "### wifi_ble",
        "- wifi_scan [passive ~15s]: Scan nearby WiFi networks and clients",
        "- wifi_deauth [disruptive ~10s]: Deauthenticate a client",
        "",
        "### nfc",
        "- nfc_read [passive ~5s]: Read a 13.56 MHz NFC tag",
    ]))
    out, dropped = trim_catalog_to_budget(rendered, budget_tokens=budget)
    # First three skills must remain.
    assert "wifi_scan" in out
    assert "wifi_deauth" in out
    assert "nfc_read" in out
    # Last two must be gone.
    assert "nfc_write" not in out
    assert "nfc_emulate" not in out
    # Exactly those two skills were dropped.
    assert dropped == 2, f"expected 2 skills dropped, got {dropped}"
    print("✓ trim drops tail lines and counts only skill lines")


async def test_trim_ignores_header_lines_in_count():
    """A category header trimmed without a surviving skill after it does not
    inflate the dropped-skill count."""
    rendered = "\n".join([
        "## Available skills",
        "",
        "### wifi_ble",
        "- wifi_scan [passive]: scan",
        "",
        "### meta",  # header that will get trimmed with no skill after
    ])
    # Budget that fits everything above the dangling header but not the header.
    keep = "\n".join([
        "## Available skills",
        "",
        "### wifi_ble",
        "- wifi_scan [passive]: scan",
    ])
    budget = estimate_tokens(keep)
    out, dropped = trim_catalog_to_budget(rendered, budget_tokens=budget)
    # Header may or may not be trimmed depending on exact byte math, but the
    # dropped count is 0 because no skill-line ("- ...") was trimmed.
    assert dropped == 0, f"expected 0 skills dropped (only header), got {dropped}"
    print("✓ header-line drops do not count as skill drops")


# ── Planner integration ─────────────────────────────────────────

class ScriptedBackend(LLMBackend):
    """Returns a scripted plan so we can inspect its safety_notes."""

    def __init__(self, response: AssistantMessage) -> None:
        self._response = response
        self.calls: list[dict] = []

    async def complete(self, messages, tools):
        self.calls.append({"messages": list(messages)})
        return self._response


def _dummy_plan_msg() -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(
            id="p",
            name="submit_plan",
            arguments={
                "reasoning": "ok",
                "steps": [{"skill": "wifi_scan", "intent": "scan"}],
                "safety_notes": [],
            },
        )],
        finish_reason="tool_calls",
    )


async def test_planner_surfaces_safety_note_on_trim():
    """Planner given a huge catalog + tiny context window returns a plan
    whose safety_notes include a 'hidden skills' line."""
    # Build a registry with many skills so the rendered catalog overflows.
    reg = ToolRegistry()
    for i in range(60):
        reg.register(Tool(
            name=f"wifi_skill_{i:03d}",
            description=f"long description for wifi skill {i} " * 6,
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda args, _n=i: None,
            sensitivity="passive",
        ))
    catalog = build_catalog(reg)

    cfg = AgentConfig(context_window=512, context_response_reserve=64)
    planner = Planner(ScriptedBackend(_dummy_plan_msg()), config=cfg)
    plan = await planner.plan("scan for wifi", catalog)

    hit = [n for n in plan.safety_notes if "hidden from planner" in n.lower()
           or "skills hidden" in n.lower()]
    assert hit, f"expected a 'hidden skills' safety note, got {plan.safety_notes}"
    print(f"✓ planner surfaces safety note on trim: {hit[0]!r}")


async def test_no_trim_needed_at_current_scale():
    """Regression guard: current skills/ + scoper_k=12 + default 2048 window
    should NOT trigger trimming. If this fails, something grew out of spec."""
    reg = ToolRegistry()
    skills_dir = Path(__file__).resolve().parents[2] / "skills"
    load_skills_into_registry(skills_dir, reg)

    # Simulate scoper narrowing to top-12.
    all_names = [t.name for t in reg.all()]
    allowed = all_names[:12]
    catalog = build_catalog(reg, allowed_names=allowed)
    rendered = render_catalog(catalog)

    cfg = AgentConfig()  # context_window=2048, response_reserve=256 defaults
    # Rough stand-ins for the Pass-1 overhead — actual values come from the
    # planner at runtime; this test wants the budget healthy, not exact.
    from faust.agent.planner import PLANNER_SYSTEM_PROMPT, SUBMIT_PLAN_TOOL
    import json as _json
    budget = catalog_budget_tokens(
        context_window=cfg.context_window,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        schema_str=_json.dumps(SUBMIT_PLAN_TOOL),
        user_prompt="scan the wifi",
        conversation_text="",
        response_reserve=cfg.context_response_reserve,
    )
    _, dropped = trim_catalog_to_budget(rendered, budget_tokens=budget)
    assert dropped == 0, (
        f"trimming triggered at current scale: dropped={dropped}, budget={budget}"
    )
    print(f"✓ no trim needed at current scale (budget={budget} tokens spare)")


# ── Runner ─────────────────────────────────────────────────────

async def main():
    await test_estimate_tokens_monotonic()
    await test_budget_positive_under_normal_load()
    await test_budget_zero_when_fixed_overhead_exceeds_window()
    await test_trim_no_op_when_under_budget()
    await test_trim_drops_tail_and_counts()
    await test_trim_ignores_header_lines_in_count()
    await test_planner_surfaces_safety_note_on_trim()
    await test_no_trim_needed_at_current_scale()
    print("\nall budget tests passed")


if __name__ == "__main__":
    asyncio.run(main())
