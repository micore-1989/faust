"""
Skill loader tests.

Tests parse → validate → register pipeline without any LLM or hardware.
Run with: python -m faust.tests.test_skill_loader
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.skills.loader import (
    SkillFrontmatter,
    load_skill,
    load_skills_into_registry,
    parse_skill_md,
)
from faust.tools.registry import ToolRegistry


# ------------- Helpers -------------

def _write_skill(tmp: Path, name: str, content: str, tool_py: str | None = None) -> Path:
    """Create a skill directory with SKILL.md (and optional tool.py) under tmp."""
    d = tmp / name
    d.mkdir()
    (d / "SKILL.md").write_text(content)
    if tool_py is not None:
        (d / "tool.py").write_text(tool_py)
    return d


VALID_SKILL = """\
---
name: test_echo
description: Echo text back
parameters_schema:
  type: object
  properties:
    text:
      type: string
  required:
    - text
sensitivity: passive
allowed_tools:
  - test_echo
---

# Test Echo

A test skill.
"""

VALID_TOOL_PY = """\
def execute(args):
    return args.get("text", "")
"""


# ------------- Tests -------------

async def test_parse_valid_skill():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text(VALID_SKILL)
        fm, body = parse_skill_md(p)
        assert fm.name == "test_echo"
        assert fm.sensitivity == "passive"
        assert fm.parameters_schema["required"] == ["text"]
        assert "Test Echo" in body
    print("✓ parse valid SKILL.md")


async def test_missing_frontmatter_delimiter():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text("no frontmatter here\njust markdown")
        try:
            parse_skill_md(p)
            assert False, "should have raised"
        except ValueError as e:
            assert "must start with '---'" in str(e)
    print("✓ missing frontmatter delimiter raises ValueError")


async def test_missing_closing_delimiter():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text("---\nname: broken\n")
        try:
            parse_skill_md(p)
            assert False, "should have raised"
        except ValueError as e:
            assert "missing closing" in str(e)
    print("✓ missing closing delimiter raises ValueError")


async def test_invalid_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text("---\n: [invalid yaml\n---\nbody")
        try:
            parse_skill_md(p)
            assert False, "should have raised"
        except ValueError as e:
            assert "invalid YAML" in str(e)
    print("✓ invalid YAML raises ValueError")


async def test_missing_required_field():
    skill = """\
---
name: no_description
sensitivity: passive
---
body
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text(skill)
        try:
            parse_skill_md(p)
            assert False, "should have raised"
        except Exception:
            pass  # pydantic ValidationError
    print("✓ missing required field raises")


async def test_invalid_sensitivity():
    skill = """\
---
name: bad_sens
description: testing
sensitivity: nuclear
---
body
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text(skill)
        try:
            parse_skill_md(p)
            assert False, "should have raised"
        except Exception:
            pass  # pydantic ValidationError
    print("✓ invalid sensitivity raises")


async def test_invalid_name():
    skill = """\
---
name: "123 not valid!"
description: testing
---
body
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text(skill)
        try:
            parse_skill_md(p)
            assert False, "should have raised"
        except Exception:
            pass
    print("✓ invalid name raises")


async def test_load_skill_with_tool_py():
    with tempfile.TemporaryDirectory() as tmp:
        d = _write_skill(Path(tmp), "echo", VALID_SKILL, VALID_TOOL_PY)
        tool = load_skill(d)
        assert tool.name == "test_echo"
        assert tool.sensitivity == "passive"
        # Invoke the loaded callable.
        result = tool.fn({"text": "hello"})
        # Sync function, no await needed.
        assert result == "hello"
    print("✓ load skill with tool.py")


async def test_load_skill_without_tool_py_returns_stub():
    with tempfile.TemporaryDirectory() as tmp:
        d = _write_skill(Path(tmp), "stub", VALID_SKILL)
        tool = load_skill(d)
        result = await tool.fn({"text": "hello"})
        assert "not implemented" in result
    print("✓ load skill without tool.py returns stub")


async def test_tool_py_missing_execute_raises():
    bad_tool_py = "def not_execute(args): pass"
    with tempfile.TemporaryDirectory() as tmp:
        d = _write_skill(Path(tmp), "bad", VALID_SKILL, bad_tool_py)
        try:
            load_skill(d)
            assert False, "should have raised"
        except ValueError as e:
            assert "must define an 'execute' function" in str(e)
    print("✓ tool.py without execute() raises ValueError")


async def test_load_skills_into_registry():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "echo", VALID_SKILL, VALID_TOOL_PY)

        skill2 = VALID_SKILL.replace("test_echo", "test_add")
        _write_skill(root, "add", skill2, "def execute(args): return 42")

        registry = ToolRegistry()
        loaded = load_skills_into_registry(root, registry)
        assert len(loaded) == 2
        assert set(loaded) == {"test_add", "test_echo"}
        assert registry.get("test_echo") is not None
        assert registry.get("test_add") is not None
        # OpenAI schemas should have both.
        schemas = registry.to_openai_schemas()
        assert len(schemas) == 2
    print("✓ load_skills_into_registry populates registry")


async def test_duplicate_skill_name_raises():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "a", VALID_SKILL, VALID_TOOL_PY)
        _write_skill(root, "b", VALID_SKILL, VALID_TOOL_PY)  # same name in frontmatter

        registry = ToolRegistry()
        try:
            load_skills_into_registry(root, registry)
            assert False, "should have raised"
        except ValueError as e:
            assert "already registered" in str(e)
    print("✓ duplicate skill name raises")


async def test_nonexistent_skills_dir_returns_empty():
    registry = ToolRegistry()
    loaded = load_skills_into_registry(Path("/nonexistent"), registry)
    assert loaded == []
    print("✓ nonexistent skills dir returns empty list")


async def test_directory_without_skill_md_is_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "random_dir").mkdir()
        (root / "random_dir" / "notes.txt").write_text("not a skill")
        _write_skill(root, "valid", VALID_SKILL, VALID_TOOL_PY)

        registry = ToolRegistry()
        loaded = load_skills_into_registry(root, registry)
        assert loaded == ["test_echo"]
    print("✓ directories without SKILL.md are skipped")


async def test_disruptive_sensitivity_propagates():
    disruptive_skill = """\
---
name: wifi_deauth
description: Deauth a client
parameters_schema:
  type: object
  properties:
    bssid:
      type: string
  required:
    - bssid
sensitivity: disruptive
---
Disruptive skill.
"""
    with tempfile.TemporaryDirectory() as tmp:
        d = _write_skill(Path(tmp), "deauth", disruptive_skill)
        tool = load_skill(d)
        assert tool.sensitivity == "disruptive"
    print("✓ disruptive sensitivity propagates to Tool")


async def test_default_parameters_schema():
    minimal = """\
---
name: minimal_skill
description: Minimal skill with no explicit schema
---
body
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "SKILL.md"
        p.write_text(minimal)
        fm, _ = parse_skill_md(p)
        assert fm.parameters_schema == {"type": "object", "properties": {}}
    print("✓ default parameters_schema when omitted")


async def main():
    await test_parse_valid_skill()
    await test_missing_frontmatter_delimiter()
    await test_missing_closing_delimiter()
    await test_invalid_yaml()
    await test_missing_required_field()
    await test_invalid_sensitivity()
    await test_invalid_name()
    await test_load_skill_with_tool_py()
    await test_load_skill_without_tool_py_returns_stub()
    await test_tool_py_missing_execute_raises()
    await test_load_skills_into_registry()
    await test_duplicate_skill_name_raises()
    await test_nonexistent_skills_dir_returns_empty()
    await test_directory_without_skill_md_is_skipped()
    await test_disruptive_sensitivity_propagates()
    await test_default_parameters_schema()
    print("\nall skill loader tests passed")


if __name__ == "__main__":
    asyncio.run(main())
