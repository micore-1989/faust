"""
Execution plan — the shared structure between the Planner and the Executor.

A Plan is produced by Pass 1 (Mephisto with only the skill catalog in context)
and consumed by Pass 2 (Faust's per-step parameterize-and-dispatch).

Keep this minimal and JSON-serializable. This is the protocol between
Mephisto's reasoning layer and Faust's execution layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PlanStep:
    """One step in an execution plan.

    - skill: name of a registered skill (must exist in the tool registry)
    - intent: natural-language description of what this step should do,
              used as context for parameter generation in Pass 2
    - critical: if True, this step requires explicit user confirmation beyond
                the plan-level approval (maps to sensitivity escalation)
    """
    skill: str
    intent: str
    critical: bool = False


@dataclass
class Plan:
    """Full execution plan produced by the Planner.

    - reasoning: high-level rationale (shown to the user)
    - steps: ordered list of PlanStep
    - safety_notes: any warnings the planner surfaced (shown to the user)
    """
    reasoning: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        steps = [PlanStep(**s) for s in data.get("steps", [])]
        return cls(
            reasoning=data.get("reasoning", ""),
            steps=steps,
            safety_notes=data.get("safety_notes", []),
        )
