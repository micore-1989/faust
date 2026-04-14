"""
Structured events emitted by the agent loop.

Both the CLI (dev) and the UI (later) consume this same stream. Adding a new
event type means: extend the union, add a class, handle it in every consumer.
Keep the surface small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union

from .plan import Plan


@dataclass
class Thinking:
    """Assistant text emitted before/between tool calls. May stream in chunks."""
    type: Literal["thinking"] = "thinking"
    text: str = ""
    is_delta: bool = False  # True if this is a streaming chunk, False if complete


@dataclass
class ToolCallProposed:
    """Model has decided to call a tool. Emitted BEFORE dispatch (so disclosure
    layer can intercept and surface a confirmation banner if needed)."""
    type: Literal["tool_call_proposed"] = "tool_call_proposed"
    call_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    sensitivity: str = "passive"  # passive | active | disruptive


@dataclass
class ToolCallExecuted:
    """Tool dispatch finished. Result may be success or error."""
    type: Literal["tool_call_executed"] = "tool_call_executed"
    call_id: str = ""
    tool_name: str = ""
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


@dataclass
class PlanProposed:
    """Planner has produced an execution plan. Emitted BEFORE any tool call
    so the UI can surface the whole plan for user approval."""
    type: Literal["plan_proposed"] = "plan_proposed"
    plan_id: str = ""
    reasoning: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)

    @classmethod
    def from_plan(cls, plan: Plan, plan_id: str = "") -> "PlanProposed":
        return cls(
            plan_id=plan_id,
            reasoning=plan.reasoning,
            steps=[{
                "skill": s.skill,
                "intent": s.intent,
                "critical": s.critical,
            } for s in plan.steps],
            safety_notes=list(plan.safety_notes),
        )


@dataclass
class Final:
    """Loop terminated. Reason is one of: end_turn (model done), max_iterations,
    user_abort (disclosure layer rejected a call), error (backend crashed)."""
    type: Literal["final"] = "final"
    reason: Literal["end_turn", "max_iterations", "user_abort", "error"] = "end_turn"
    text: str = ""
    error: str | None = None


Event = Union[Thinking, PlanProposed, ToolCallProposed, ToolCallExecuted, Final]
