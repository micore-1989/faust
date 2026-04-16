"""
Skill loader.

Parses SKILL.md files (OpenClaw format: YAML frontmatter + markdown body) and
populates a ToolRegistry. Each skill lives in its own directory:

    skills/
      wifi-scan/
        SKILL.md          <- required: frontmatter + docs
        tool.py           <- optional: execute(args) callable
      sub-ghz-capture/
        SKILL.md
        tool.py

Frontmatter schema (validated by pydantic):
    name: wifi_scan
    description: Scan for nearby WiFi networks
    parameters_schema:
      type: object
      properties:
        interface: {type: string, description: "WiFi interface"}
      required: [interface]
    sensitivity: passive          # passive | active | disruptive
    allowed_tools: [wifi_scan]    # reserved for multi-tool skills (future)

If a skill directory contains tool.py with an `execute` function, it becomes
the tool callable. Otherwise a stub is generated that returns
"tool not implemented: <name>".

Fails loudly on malformed skills per project convention.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

from ..tools.registry import Sensitivity, Tool, ToolCallable, ToolRegistry


class SkillFrontmatter(BaseModel):
    """Validated SKILL.md frontmatter."""

    name: str
    description: str
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
    }
    sensitivity: Sensitivity = "passive"
    allowed_tools: list[str] = []
    # Wall-clock seconds a typical run takes. Used by the planner to budget
    # sequences and by the UI to show an estimate on PlanProposed. None = unknown.
    typical_duration_s: int | None = None
    # Domain-opinion hints the skill writer bakes in. Each entry is
    # {"when": "<dsl>", "suggest": "<hint text for the planner>"}.
    # See faust/agent/pivots.py for the DSL. After the skill runs, matching
    # suggestions are injected into the next step's Pass 2 context so the
    # planner can pivot without paying a full re-plan call.
    pivot_hints: list[dict[str, str]] = []

    @field_validator("name")
    @classmethod
    def name_must_be_identifier(cls, v: str) -> str:
        if not v.replace("-", "_").isidentifier():
            raise ValueError(f"skill name must be a valid identifier: {v!r}")
        return v

    @field_validator("sensitivity")
    @classmethod
    def sensitivity_must_be_valid(cls, v: str) -> str:
        allowed = {"passive", "active", "disruptive"}
        if v not in allowed:
            raise ValueError(f"sensitivity must be one of {allowed}, got {v!r}")
        return v


def parse_skill_md(path: Path) -> tuple[SkillFrontmatter, str]:
    """Parse a SKILL.md file into validated frontmatter + markdown body.

    Raises ValueError on malformed frontmatter or missing delimiters.
    """
    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise ValueError(f"{path}: SKILL.md must start with '---' frontmatter delimiter")

    # Split on the closing '---' (second occurrence).
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: SKILL.md missing closing '---' frontmatter delimiter")

    raw_yaml = parts[1]
    body = parts[2].strip()

    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: invalid YAML in frontmatter: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"{path}: frontmatter must be a YAML mapping, got {type(data).__name__}")

    frontmatter = SkillFrontmatter(**data)
    return frontmatter, body


def _load_tool_callable(skill_dir: Path, skill_name: str) -> ToolCallable:
    """Load execute() from tool.py if it exists, else return a stub."""
    tool_py = skill_dir / "tool.py"
    if not tool_py.exists():
        async def _stub(args: dict[str, Any]) -> str:
            return f"tool not implemented: {skill_name}"
        return _stub

    # Import tool.py as a module scoped to this skill.
    module_name = f"faust_skill_{skill_name}"
    spec = importlib.util.spec_from_file_location(module_name, tool_py)
    if spec is None or spec.loader is None:
        raise ValueError(f"{tool_py}: failed to create module spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    fn = getattr(module, "execute", None)
    if fn is None:
        raise ValueError(f"{tool_py}: must define an 'execute' function")
    if not callable(fn):
        raise ValueError(f"{tool_py}: 'execute' must be callable")

    return fn


def load_skill(skill_dir: Path) -> Tool:
    """Load a single skill from a directory containing SKILL.md."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"{skill_dir}: missing SKILL.md")

    frontmatter, _body = parse_skill_md(skill_md)
    fn = _load_tool_callable(skill_dir, frontmatter.name)

    return Tool(
        name=frontmatter.name,
        description=frontmatter.description,
        parameters_schema=frontmatter.parameters_schema,
        fn=fn,
        sensitivity=frontmatter.sensitivity,
        typical_duration_s=frontmatter.typical_duration_s,
        pivot_hints=frontmatter.pivot_hints,
    )


def load_skills_into_registry(
    skills_dir: Path,
    registry: ToolRegistry,
) -> list[str]:
    """Walk skills_dir, load each subdirectory as a skill, register into registry.

    Returns list of loaded skill names. Raises on the first malformed skill
    (fail loudly per project convention).
    """
    if not skills_dir.is_dir():
        return []

    loaded: list[str] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "SKILL.md").exists():
            continue

        tool = load_skill(child)
        registry.register(tool)
        loaded.append(tool.name)

    return loaded
