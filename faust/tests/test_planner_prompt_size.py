"""
Planner prompt-size budget tests.

Pass 1 must fit Hailo's 2048-token window even on the fast-fallback path.
The planner system prompt + submit_plan tool schema are static boilerplate
that shrink the budget available for the skill catalog, so they are kept
under hard character/token ceilings.

Run with: python -m faust.tests.test_planner_prompt_size
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.planner import PLANNER_SYSTEM_PROMPT, SUBMIT_PLAN_TOOL


def test_system_prompt_under_budget() -> None:
    """PLANNER_SYSTEM_PROMPT must stay ≤340 rough tokens (3.5 chars/tok)."""
    est_tokens = len(PLANNER_SYSTEM_PROMPT) / 3.5
    assert est_tokens <= 340, (
        f"system prompt too large: ~{est_tokens:.0f} tokens "
        f"({len(PLANNER_SYSTEM_PROMPT)} chars); budget is 340"
    )


def test_submit_plan_schema_under_budget() -> None:
    """SUBMIT_PLAN_TOOL schema must stay ≤170 rough tokens."""
    schema_json = json.dumps(SUBMIT_PLAN_TOOL)
    est_tokens = len(schema_json) / 3.5
    assert est_tokens <= 170, (
        f"submit_plan schema too large: ~{est_tokens:.0f} tokens "
        f"({len(schema_json)} chars); budget is 170"
    )


if __name__ == "__main__":
    test_system_prompt_under_budget()
    test_submit_plan_schema_under_budget()
    print("prompt-size tests passed")
