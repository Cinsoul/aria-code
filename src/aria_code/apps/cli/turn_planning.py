"""Per-turn planning DECISIONS for send_message (pure, testable).

Extracted from ``aria_cli.send_message`` — the first slice of the file's
1300+ line stateful method to be pulled out. This module holds only the
*decision* logic (round budget, whether to trigger AI decomposition), which
depends solely on the user's message text and has no I/O, no ``self`` state,
and no side effects. It is safe to unit-test in isolation and safe to extract
without any behavior change, unlike the surrounding streaming/tool-loop code.

Mirrors send_message's inline logic exactly:
  • task complexity  → message > 120 chars, or contains a multi-step keyword
  • round budget      → complex tasks get a larger soft/hard round budget
  • decomposition     → long (>150 char), complex, non-slash-command messages
                         trigger an upfront AI decomposition pass
"""

from __future__ import annotations

TASK_COMPLEXITY_LENGTH_THRESHOLD = 120

TASK_COMPLEXITY_KEYWORDS = (
    "然后", "接着", "最后", "步骤", "并且", "同时",
    "and then", "step", "finally", "after that", "next",
    "完整", "全面", "详细", "系统", "comprehensive", "complete",
)

DECOMP_THRESHOLD = 150   # chars

SOFT_ROUND_BUDGET_SIMPLE = 16
SOFT_ROUND_BUDGET_COMPLEX = 30
HARD_ROUND_EXTENSION_SIMPLE = 10
HARD_ROUND_EXTENSION_COMPLEX = 20


def is_complex_task(message: str) -> bool:
    """A message is 'complex' if it's long or names a multi-step structure."""
    return (
        len(message) > TASK_COMPLEXITY_LENGTH_THRESHOLD
        or any(kw in message for kw in TASK_COMPLEXITY_KEYWORDS)
    )


def round_budget_for(is_complex: bool) -> tuple[int, int]:
    """-> (max_rounds, hard_max_rounds). Complex tasks get a larger budget
    on both the soft limit (where we start checking for real progress) and
    the hard extension (how far a still-progressing task can run past it)."""
    max_rounds = SOFT_ROUND_BUDGET_COMPLEX if is_complex else SOFT_ROUND_BUDGET_SIMPLE
    hard_max_rounds = max_rounds + (
        HARD_ROUND_EXTENSION_COMPLEX if is_complex else HARD_ROUND_EXTENSION_SIMPLE
    )
    return max_rounds, hard_max_rounds


def should_decompose(message: str, is_complex: bool) -> bool:
    """Trigger an upfront AI decomposition pass for long, complex, non-slash
    messages. Slash commands (``/...``) and bang commands (``!...``) are never
    decomposed — they're already a single deterministic action."""
    return (
        len(message) > DECOMP_THRESHOLD
        and is_complex
        and not any(message.startswith(p) for p in ("/", "!"))
    )


# ── post-turn context pressure ───────────────────────────────────────────────
# send_message had three separate places that decide whether history is too hot
# to carry into the next turn, and they disagreed. The usage-driven one (real
# provider prompt_tokens) and the pre-turn one both honour auto_compact_context
# and auto_compact_threshold; the post-turn char-estimate one honoured neither
# and hardcoded 90% compact / 70% warn. So `/config set
# auto_compact_context=false` did not turn auto-compaction off — /status said
# "auto compact off" while the third path still compacted — and a threshold of
# 0.95 was capped at the hidden 0.90.
#
# Warning is deliberately NOT gated on the toggle. Turning auto-compaction off
# means "do not rewrite my history", not "stop telling me how full it is" —
# and it is precisely the user who disabled compaction who needs to be told to
# run /compact.

CONTEXT_WARN_FRACTION = 0.70
CHARS_PER_TOKEN_ESTIMATE = 3
DEFAULT_COMPACT_THRESHOLD = 0.78
MIN_COMPACT_THRESHOLD = 0.50
MAX_COMPACT_THRESHOLD = 0.95


def estimate_context_tokens(conversation: list) -> int:
    """Rough token count for a conversation, by characters."""
    return sum(
        len(m.get("content", "") or "") for m in (conversation or [])
    ) // CHARS_PER_TOKEN_ESTIMATE


def clamp_compact_threshold(value) -> float:
    """Config threshold as a fraction, clamped to the range /config accepts."""
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return DEFAULT_COMPACT_THRESHOLD
    return max(MIN_COMPACT_THRESHOLD, min(MAX_COMPACT_THRESHOLD, threshold))


def post_turn_context_decision(
    used_tokens: int,
    max_tokens: int,
    *,
    auto_compact_enabled: bool = True,
    threshold=DEFAULT_COMPACT_THRESHOLD,
    already_compacted: bool = False,
) -> dict:
    """-> {"fill_pct", "should_compact", "should_warn"}.

    ``already_compacted`` is the usage-driven path having fired this turn; it
    suppresses both outcomes so one turn never compacts twice or warns about a
    figure it just fixed.
    """
    if max_tokens <= 0:
        return {"fill_pct": 0, "should_compact": False, "should_warn": False}

    fill_pct = min(100, int(used_tokens / max_tokens * 100))
    limit_pct = clamp_compact_threshold(threshold) * 100

    should_compact = (
        bool(auto_compact_enabled)
        and not already_compacted
        and fill_pct >= limit_pct
    )
    should_warn = (
        not should_compact
        and not already_compacted
        and fill_pct >= CONTEXT_WARN_FRACTION * 100
    )
    return {
        "fill_pct": fill_pct,
        "should_compact": should_compact,
        "should_warn": should_warn,
    }
