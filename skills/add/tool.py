"""Add skill — sum two integers."""

from __future__ import annotations

from typing import Any


def execute(args: dict[str, Any]) -> int:
    return int(args["a"]) + int(args["b"])
