"""
Dev CLI runner.

Same event stream the touchscreen UI will consume, just printed to terminal.

Usage (once you have Ollama running locally with a tool-capable model):
    ollama pull qwen2.5:1.5b-instruct
    ollama serve  # in another shell
    python -m faust.cli "what is 2+2?"
    python -m faust.cli "echo hello, then add 3 and 4"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from .agent.backends import make_backend, make_deep_backend
from .agent.config import AgentConfig
from .agent.disclosure import DisclosureApprover
from .agent.dispatch import Dispatcher
from .agent.events import Final, PlanProposed, Thinking, ToolCallExecuted, ToolCallProposed
from .agent.journal import Journal
from .agent.loop import AgentLoop
from .agent.plan import Plan
from .agent.twopass import TwoPassAgent
from .skills.loader import load_skills_into_registry
from .skills.scoper import make_scoper
from .tools.registry import Sensitivity, Tool, ToolRegistry
from .transport.link import LinkState, MephistoLink


# --- Two trivial demo tools so the loop can be exercised end-to-end ---

def _echo(args: dict[str, Any]) -> str:
    return str(args.get("text", ""))


def _add(args: dict[str, Any]) -> int:
    return int(args["a"]) + int(args["b"])


def build_demo_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="echo",
            description="Echo a string back. Use to verify the loop is wired up.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to echo"},
                },
                "required": ["text"],
            },
            fn=_echo,
            sensitivity="passive",
        )
    )
    reg.register(
        Tool(
            name="add",
            description="Add two integers and return the sum.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            fn=_add,
            sensitivity="passive",
        )
    )
    return reg


# --- ANSI dim/reset for legibility ---
DIM = "\033[2m"
BOLD = "\033[1m"
YELLOW = "\033[33m"
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"


def cli_confirm(
    tool_name: str,
    arguments: dict[str, Any],
    sensitivity: Sensitivity,
) -> bool:
    """Stdin confirmation for active/disruptive tool calls."""
    color = YELLOW if sensitivity == "active" else RED
    label = sensitivity.upper()
    print(f"\n{color}[{label}] {tool_name}({arguments}){RESET}")
    try:
        answer = input(f"{color}  approve? [y/N] {RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


async def main(prompt: str) -> int:
    cfg = AgentConfig.from_env()
    backend = make_backend(cfg)
    registry = ToolRegistry()

    # Load skills from skills/ directory (project root).
    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    loaded = load_skills_into_registry(skills_dir, registry)
    if loaded:
        print(f"{DIM}loaded skills: {', '.join(loaded)}{RESET}")
    else:
        # Fall back to hardcoded demo tools if no skills/ directory.
        registry = build_demo_registry()
        print(f"{DIM}no skills/ directory — using demo tools{RESET}")

    # Disclosure layer: journal + confirmation UI.
    journal_path = Path(__file__).resolve().parent.parent / "journal.db"
    journal = Journal(str(journal_path))
    approver = DisclosureApprover(journal, confirm=cli_confirm)

    dispatcher = Dispatcher(registry, approver=approver)

    # Skill scoper — keeps tool_schemas context-compact as the library grows.
    scoper = None
    if cfg.scoper_enabled:
        scoper = make_scoper(
            skills_dir,
            [t.name for t in registry.all()],
            remote_endpoint=cfg.effective_scoper_endpoint() or None,
        )
        print(f"{DIM}scoper={type(scoper).__name__} k={cfg.scoper_k}{RESET}")

    if cfg.mode == "twopass":
        def cli_plan_approve(plan: Plan) -> bool:
            print(f"\n{BOLD}PLAN:{RESET} {plan.reasoning}")
            for i, s in enumerate(plan.steps, 1):
                crit = f" {RED}[critical]{RESET}" if s.critical else ""
                print(f"  {i}. {YELLOW}{s.skill}{RESET}{crit} — {s.intent}")
            for note in plan.safety_notes:
                print(f"  {RED}⚠ {note}{RESET}")
            try:
                ans = input(f"\n{BOLD}execute plan? [y/N] {RESET}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False
            return ans in ("y", "yes")

        deep_backend = make_deep_backend(cfg)
        if deep_backend is not None:
            print(f"{DIM}deep planner: {cfg.planning_model} @ {cfg.effective_planning_endpoint()}{RESET}")
        agent = TwoPassAgent(
            backend, dispatcher, cfg,
            scoper=scoper,
            plan_approver=cli_plan_approve,
            deep_backend=deep_backend,
        )
        print(f"{DIM}mode=twopass{RESET}")
    else:
        agent = AgentLoop(
            backend, dispatcher, cfg,
            scoper=scoper, scoper_k=cfg.scoper_k,
        )
        print(f"{DIM}mode=single{RESET}")

    # If using Mephisto backend, check link health before starting.
    link: MephistoLink | None = None
    if cfg.backend == "mephisto":
        from .agent.config import MEPHISTO_ENDPOINT
        link = MephistoLink(endpoint=MEPHISTO_ENDPOINT)
        status = await link.check()
        if status.state == LinkState.CONNECTED:
            print(f"{GREEN}mephisto: connected ({status.model}, {status.latency_ms}ms){RESET}")
        elif status.state == LinkState.REACHABLE:
            print(f"{YELLOW}mephisto: reachable but no model loaded{RESET}")
        else:
            print(f"{RED}mephisto: disconnected — {status.error}{RESET}")
            print(f"{RED}  is Mephisto docked and hailo-ollama running?{RESET}")

    print(f"{DIM}backend={cfg.backend} model={cfg.model} endpoint={cfg.llm_endpoint}{RESET}")
    print(f"{DIM}journal={journal_path}{RESET}")
    print(f"{BOLD}> {prompt}{RESET}\n")

    exit_code = 0
    try:
        async for event in agent.run(prompt):
            match event:
                case Thinking(text=text):
                    print(text, end="", flush=True)
                case PlanProposed(reasoning=reasoning, steps=steps):
                    # CLI already prints the plan via cli_plan_approve;
                    # this keeps the event surfaced for debugging.
                    print(f"{DIM}[plan proposed: {len(steps)} steps]{RESET}")
                case ToolCallProposed(tool_name=name, arguments=args, sensitivity=sens):
                    color = {"passive": DIM, "active": YELLOW, "disruptive": RED}[sens]
                    print(f"\n{color}→ {name}({args}) [{sens}]{RESET}")
                case ToolCallExecuted(tool_name=name, result=res, error=err, duration_ms=ms):
                    if err:
                        print(f"  {RED}✗ {name} → {err} ({ms}ms){RESET}")
                    else:
                        print(f"  {GREEN}✓ {name} → {res} ({ms}ms){RESET}")
                case Final(reason=reason, error=err):
                    print(f"\n{DIM}[done: {reason}{f' — {err}' if err else ''}]{RESET}")
                    if reason == "error":
                        exit_code = 1
    finally:
        journal.close()
        if link is not None:
            await link.aclose()
        if cfg.mode == "twopass":
            db = getattr(agent, "deep_backend", None)
            if db is not None:
                await db.aclose()
        await backend.aclose()
    return exit_code


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m faust.cli '<prompt>'", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(" ".join(sys.argv[1:]))))
