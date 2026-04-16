"""
Pivot-hint DSL for per-step reactive planning.

A skill declares `pivot_hints` in its SKILL.md frontmatter — a list of
`{when, suggest}` pairs. After the skill executes, the TwoPassAgent evaluates
each `when` condition against the step's summary dict. Every matching hint's
`suggest` string is threaded into the next step's Pass 2 context (and the
re-plan prompt, if re-plan fires).

This lets the skill writer encode domain opinions — "if you find weak hashes,
consider wpa_crack" — so the planner doesn't have to rediscover them each run.

The DSL is intentionally small: one operator per line, dotted-path lookup
against the summary dict, JSON-literal right-hand side. No expressions, no
nesting, no eval().

Grammar:
    when   := PATH OP VALUE | PATH
    PATH   := "summary" ("." KEY)+
    OP     := "==" | "!=" | ">" | ">=" | "<" | "<=" | " in "
    VALUE  := null | true | false | INT | FLOAT | STRING | LIST

A path with no operator evaluates truthy: "summary.captured" matches when
summary["captured"] is truthy.
"""
from __future__ import annotations

import json
from typing import Any


_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: _num(a) >= _num(b),
    "<=": lambda a, b: _num(a) <= _num(b),
    ">":  lambda a, b: _num(a) > _num(b),
    "<":  lambda a, b: _num(a) < _num(b),
    " in ": lambda a, b: a in b if isinstance(b, (list, tuple, set, str)) else False,
}
# Match longer ops first so "==" isn't shadowed by "=" etc.
_OP_ORDER = (" in ", ">=", "<=", "==", "!=", ">", "<")


def _num(x: Any) -> float:
    if isinstance(x, bool):
        return 1.0 if x else 0.0
    if isinstance(x, (int, float)):
        return float(x)
    return 0.0


def _parse_literal(s: str) -> Any:
    s = s.strip()
    if s == "null" or s == "None":
        return None
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    # Try JSON (handles ints, floats, strings, lists, dicts).
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Bare word → treat as string.
        return s.strip('"').strip("'")


def _resolve(path: str, summary: dict[str, Any]) -> Any:
    """Resolve 'summary.x.y' against summary dict. Missing keys return None."""
    parts = path.strip().split(".")
    if parts[0] != "summary":
        return None
    cur: Any = summary
    for p in parts[1:]:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur


def evaluate_when(when: str, summary: dict[str, Any] | None) -> bool:
    """Return True iff `when` holds against the summary dict.

    Never raises — malformed conditions or missing paths just return False.
    """
    if summary is None:
        return False
    try:
        for op in _OP_ORDER:
            if op in when:
                lhs, rhs = when.split(op, 1)
                left = _resolve(lhs, summary)
                right = _parse_literal(rhs)
                return bool(_OPS[op](left, right))
        # No operator → truthy path check.
        value = _resolve(when, summary)
        return bool(value)
    except Exception:
        return False


def matching_suggestions(
    hints: list[dict[str, str]] | None,
    summary: dict[str, Any] | None,
) -> list[str]:
    """Return the `suggest` strings of every hint whose `when` condition holds."""
    if not hints or summary is None:
        return []
    out: list[str] = []
    for h in hints:
        when = h.get("when", "")
        suggest = h.get("suggest", "")
        if when and suggest and evaluate_when(when, summary):
            out.append(suggest)
    return out
