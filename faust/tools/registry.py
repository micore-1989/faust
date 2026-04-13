"""
Tool registry.

A tool is: a name, a JSON-schema description (for the model), a Python callable
that takes a dict of arguments and returns a result, and a sensitivity class.

In v0 we register tools imperatively. The skill loader (next session) will
populate this same registry from SKILL.md files.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

Sensitivity = Literal["passive", "active", "disruptive"]
ToolCallable = Callable[[dict[str, Any]], Awaitable[Any] | Any]


@dataclass
class Tool:
    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSON Schema
    fn: ToolCallable
    sensitivity: Sensitivity = "passive"

    def to_openai_schema(self) -> dict[str, Any]:
        """Format this tool for the OpenAI /v1/chat/completions tools field."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def to_openai_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    async def invoke(self, name: str, args: dict[str, Any]) -> Any:
        """Invoke a tool. Awaits if the callable is a coroutine, else calls
        directly. Errors propagate; the dispatch layer is responsible for
        converting them into ToolCallExecuted(error=...) events."""
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        result = tool.fn(args)
        if inspect.isawaitable(result):
            result = await result
        return result
