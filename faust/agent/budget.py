"""
Pass 1 context-budget arithmetic.

The Hailo NPU exposes a 2048-token window. The planner prompt, submit_plan
schema, rendered skill catalog, user prompt, and conversation history all
compete for that window, with a response reserve held back for the model's
reply. Without a bound on the catalog, an oversized registry plus optional
conversation memory can silently push past the window and let the runtime
truncate somewhere arbitrary.

This module computes the budget and trims the catalog from the tail. Because
`build_catalog()` sorts by `_CATEGORY_ORDER` (wifi_ble first, meta last),
tail-trimming drops the least-used categories first — which is what we want
for this device.

Token estimation uses a conservative 3.5 chars/token ratio, ~10-15%
pessimistic vs real Qwen BPE. Err in the direction of over-counting so we
never overrun the actual window.
"""

from __future__ import annotations


_CHARS_PER_TOK = 3.5


def estimate_tokens(s: str) -> int:
    """Conservative character-based token estimate.

    +1 so an empty string still costs a token — prevents downstream callers
    from treating "no content" as "free."
    """
    return int(len(s) / _CHARS_PER_TOK) + 1


def catalog_budget_tokens(
    *,
    context_window: int,
    system_prompt: str,
    schema_str: str,
    user_prompt: str,
    conversation_text: str,
    response_reserve: int,
) -> int:
    """Tokens available for the rendered catalog.

    Formula: context_window − (system_prompt + schema + user_prompt +
    conversation_memory + response_reserve).

    Clamps at 0: negative means the fixed overhead has already overfilled
    the window. Caller's job to drop conversation memory before re-trying.
    """
    fixed = (
        estimate_tokens(system_prompt)
        + estimate_tokens(schema_str)
        + estimate_tokens(user_prompt)
        + estimate_tokens(conversation_text)
        + response_reserve
    )
    return max(0, context_window - fixed)


def trim_catalog_to_budget(
    rendered: str,
    budget_tokens: int,
) -> tuple[str, int]:
    """Trim the rendered catalog from the tail to fit `budget_tokens`.

    Returns (trimmed_text, dropped_skill_count). `dropped_skill_count`
    counts skill lines only — category headers and blank lines are not
    counted, so a safety_note reflects what the operator actually lost.

    Under budget: returns `(rendered, 0)` unchanged.

    Otherwise binary-searches the longest line-prefix of the input that
    fits, then joins and returns. Caller decides whether to surface the
    drop count as a safety_note.
    """
    if estimate_tokens(rendered) <= budget_tokens:
        return rendered, 0

    lines = rendered.split("\n")

    # Binary search: largest k such that "\n".join(lines[:k]) fits the budget.
    lo, hi, best = 0, len(lines), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if estimate_tokens("\n".join(lines[:mid])) <= budget_tokens:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    dropped_skill_count = sum(1 for line in lines[best:] if line.startswith("- "))
    return "\n".join(lines[:best]), dropped_skill_count
