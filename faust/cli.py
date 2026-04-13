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
from typing import Any

from .agent.backends import make_backend
from .agent.config import AgentConfig
from .agent.dispatch import Dispatcher
from .agent.events import Final, Thinking, ToolCallExecuted, ToolCallProposed
from .agent.loop import AgentLoop
from .tools.registry import Tool, ToolRegistry


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


async def main(prompt: str) -> int:
    cfg = AgentConfig.from_env()
    backend = make_backend(cfg)
    registry = build_demo_registry()
    dispatcher = Dispatcher(registry)
    loop = AgentLoop(backend, dispatcher, cfg)

    print(f"{DIM}backend={cfg.backend} model={cfg.model} endpoint={cfg.llm_endpoint}{RESET}")
    print(f"{BOLD}> {prompt}{RESET}\n")

    exit_code = 0
    try:
        async for event in loop.run(prompt):
            match event:
                case Thinking(text=text):
                    print(text, end="", flush=True)
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
        await backend.aclose()
    return exit_code


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m faust.cli '<prompt>'", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(" ".join(sys.argv[1:]))))
