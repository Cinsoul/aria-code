"""Post-turn context pressure must obey the user's compaction settings.

send_message has three places that decide whether history is too hot to carry
forward. Two honoured auto_compact_context and auto_compact_threshold; the
post-turn char-estimate path honoured neither and hardcoded 90% compact / 70%
warn. `/config set auto_compact_context=false` therefore did not turn
auto-compaction off — /status reported "auto compact off" while that path
still rewrote history — and a threshold of 0.95 was overridden by the hidden
0.90.
"""

from __future__ import annotations

import unittest

from aria_code.apps.cli.turn_planning import (
    CONTEXT_WARN_FRACTION,
    MAX_COMPACT_THRESHOLD,
    MIN_COMPACT_THRESHOLD,
    clamp_compact_threshold,
    estimate_context_tokens,
    post_turn_context_decision,
)

CTX = 10_000


def decide(pct, **kw):
    return post_turn_context_decision(int(CTX * pct / 100), CTX, **kw)


class OffMeansOff(unittest.TestCase):
    def test_disabled_never_compacts_at_any_fill(self):
        for pct in (70, 80, 90, 95, 100, 130):
            with self.subTest(pct=pct):
                self.assertFalse(
                    decide(pct, auto_compact_enabled=False)["should_compact"],
                    f"compacted at {pct}% with auto_compact_context=false",
                )

    def test_disabled_still_warns(self):
        """Off means 'do not rewrite my history', not 'stop telling me'.

        The user who turned compaction off is exactly the one who needs to be
        told to run /compact, so the warning is deliberately not gated on the
        toggle — this is a change from the old behaviour, where a full context
        with compaction 'off' silently compacted instead of warning.
        """
        d = decide(95, auto_compact_enabled=False)
        self.assertFalse(d["should_compact"])
        self.assertTrue(d["should_warn"])


class ThresholdIsHonoured(unittest.TestCase):
    def test_user_threshold_decides_the_boundary(self):
        for threshold in (0.50, 0.60, 0.78, 0.90, 0.95):
            limit = int(threshold * 100)
            with self.subTest(threshold=threshold):
                self.assertFalse(decide(limit - 1, threshold=threshold)["should_compact"])
                self.assertTrue(decide(limit, threshold=threshold)["should_compact"])

    def test_the_old_hardcoded_90_no_longer_leaks_through(self):
        """At threshold 0.95, 90% full must not compact — it used to."""
        self.assertFalse(decide(90, threshold=0.95)["should_compact"])
        self.assertTrue(decide(95, threshold=0.95)["should_compact"])

    def test_threshold_is_clamped_to_the_range_config_accepts(self):
        self.assertEqual(clamp_compact_threshold(0.01), MIN_COMPACT_THRESHOLD)
        self.assertEqual(clamp_compact_threshold(9.9), MAX_COMPACT_THRESHOLD)

    def test_garbage_threshold_falls_back_rather_than_raising(self):
        for junk in (None, "", "abc", [], {}):
            with self.subTest(junk=junk):
                self.assertTrue(0 < clamp_compact_threshold(junk) <= 1)


class SuppressionAndEdges(unittest.TestCase):
    def test_already_compacted_suppresses_both(self):
        d = decide(99, already_compacted=True)
        self.assertFalse(d["should_compact"])
        self.assertFalse(d["should_warn"])

    def test_warn_band_sits_below_the_compact_threshold(self):
        warn_at = int(CONTEXT_WARN_FRACTION * 100)
        self.assertFalse(decide(warn_at - 1, threshold=0.90)["should_warn"])
        self.assertTrue(decide(warn_at, threshold=0.90)["should_warn"])

    def test_compacting_and_warning_are_mutually_exclusive(self):
        for pct in range(0, 131, 5):
            for enabled in (True, False):
                d = decide(pct, auto_compact_enabled=enabled)
                with self.subTest(pct=pct, enabled=enabled):
                    self.assertFalse(d["should_compact"] and d["should_warn"])

    def test_unknown_context_window_decides_nothing(self):
        d = post_turn_context_decision(5000, 0)
        self.assertEqual(d, {"fill_pct": 0, "should_compact": False, "should_warn": False})

    def test_fill_pct_is_capped_at_100(self):
        self.assertEqual(decide(400)["fill_pct"], 100)


class TokenEstimate(unittest.TestCase):
    def test_matches_the_inline_formula_it_replaced(self):
        conv = [{"role": "user", "content": "x" * 300},
                {"role": "assistant", "content": "y" * 600}]
        self.assertEqual(estimate_context_tokens(conv), 900 // 3)

    def test_survives_missing_and_none_content(self):
        self.assertEqual(estimate_context_tokens([{}, {"content": None}]), 0)
        self.assertEqual(estimate_context_tokens([]), 0)
        self.assertEqual(estimate_context_tokens(None), 0)


if __name__ == "__main__":
    unittest.main()
