"""Echo skill — returns the input text unchanged."""

from __future__ import annotations

from typing import Any


def execute(args: dict[str, Any]) -> str:
    return str(args.get("text", ""))
