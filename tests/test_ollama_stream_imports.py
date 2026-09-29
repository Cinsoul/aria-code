"""stream_ollama's module-level imports must not diverge from aria_cli.

stream_ollama borrows 45 bare names from aria_cli's module globals and is
rebound at aria_cli import time. The rebind MERGES — dict(source.__globals__)
then .update(globals()) — so a name defined in ollama_stream is the base and
aria_cli wins on conflict. That makes adding an import safe for the CLI path
and useful for the fallback path (SDK, daemon), but only while the imported
object is the one aria_cli holds.

Where it is not, the failure is silent and one-directional. apps.cli.
tool_executor exposes a _CONFIRM_TOOLS that is an empty set() placeholder
while aria_cli's is the real confirmation set: importing the obvious-looking
source would have made every tool skip confirmation on the fallback path, with
nothing raising.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

MODULE = (pathlib.Path(__file__).resolve().parents[1] / "src" / "aria_code"
          / "apps" / "cli" / "providers" / "llm" / "ollama_stream.py")

# Names ollama_stream defines itself; aria_cli has no counterpart to compare.
LOCAL_ONLY = {"annotations"}


def _module_level_imported_names() -> set:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names - LOCAL_ONLY


class ImportedNamesMatchAriaCli(unittest.TestCase):
    def test_every_shared_name_is_the_same_object(self):
        import aria_cli
        import aria_code.apps.cli.providers.llm.ollama_stream as mod

        diverged = []
        for name in sorted(_module_level_imported_names()):
            ours = getattr(mod, name, None)
            theirs = getattr(aria_cli, name, None)
            if theirs is None:          # aria_cli does not hold it — nothing to diverge from
                continue
            if ours is not theirs:
                diverged.append(name)
        self.assertEqual(
            diverged, [],
            "these module-level imports resolve to a different object than "
            "aria_cli's, so the fallback path would behave differently from "
            f"the CLI path: {diverged}",
        )

    def test_the_computed_constant_matches_by_value(self):
        """ANALYSIS_SYSTEM_PROMPT cannot be checked by identity, so check value.

        It is assigned, not imported: build_analysis_system_prompt() stamps
        today's date at call time, so ollama_stream's snapshot and aria_cli's
        are equal strings on the same day and never the same object. Leaving it
        out of the identity test entirely would hide a real divergence, so the
        exception is asserted rather than assumed.
        """
        import aria_cli
        import aria_code.apps.cli.providers.llm.ollama_stream as mod

        self.assertIsNot(mod.ANALYSIS_SYSTEM_PROMPT, aria_cli.ANALYSIS_SYSTEM_PROMPT,
                         "now the same object — drop this exception and let the "
                         "identity test cover it")
        self.assertEqual(mod.ANALYSIS_SYSTEM_PROMPT, aria_cli.ANALYSIS_SYSTEM_PROMPT)

    def test_the_stub_trap_is_still_a_trap(self):
        """Documents why _CONFIRM_TOOLS is excluded, and fails if that changes.

        If tool_executor ever gains the real set, this test fails and the
        exclusion can be revisited — which is the point of asserting it rather
        than only writing it in a comment.
        """
        import aria_cli
        from aria_code.apps.cli import tool_executor

        self.assertEqual(
            tool_executor._CONFIRM_TOOLS, set(),
            "tool_executor._CONFIRM_TOOLS is no longer an empty placeholder — "
            "re-check whether ollama_stream can now import it",
        )
        self.assertTrue(
            aria_cli._CONFIRM_TOOLS,
            "aria_cli._CONFIRM_TOOLS is empty; the confirmation set is gone",
        )


class FallbackPathResolvesMoreNames(unittest.TestCase):
    """The borrow set must only ever shrink.

    Scoping is done with stdlib ``symtable`` — Python's own analyser — rather
    than a hand-rolled AST walk. A hand-rolled one got this wrong in both
    directions while this test was being written: counting a nested function's
    closure variables as borrowed (too high) and a parameter as bound in the
    wrong scope (too low). symtable answers the exact question, which is which
    names a scope resolves as global.
    """

    # Names stream_ollama cannot resolve from its own module globals and must
    # therefore receive from aria_cli's rebind. 45 → 30 → 20 → 12. Decrease
    # this, never increase it.
    BORROW_BUDGET = 12

    @staticmethod
    def _borrowed() -> list:
        import builtins
        import symtable

        table = symtable.symtable(
            MODULE.read_text(encoding="utf-8"), MODULE.name, "exec"
        )
        defined = {
            sym.get_name() for sym in table.get_symbols()
            if sym.is_assigned() or sym.is_imported()
        }
        globals_used: set = set()

        def walk(scope):
            for sym in scope.get_symbols():
                if sym.is_global():
                    globals_used.add(sym.get_name())
            for child in scope.get_children():
                walk(child)

        walk(table)
        return sorted(globals_used - defined - set(dir(builtins)))

    def test_borrow_count_is_within_budget(self):
        borrowed = self._borrowed()
        self.assertLessEqual(
            len(borrowed), self.BORROW_BUDGET,
            f"stream_ollama now borrows {len(borrowed)} names "
            f"(budget {self.BORROW_BUDGET}): {borrowed}",
        )

    def test_budget_is_not_stale(self):
        """A budget that drifted above the real count stops guarding anything."""
        borrowed = self._borrowed()
        self.assertEqual(
            len(borrowed), self.BORROW_BUDGET,
            f"borrow count is {len(borrowed)} — set BORROW_BUDGET to that",
        )

    def test_the_reclaimed_names_are_really_gone(self):
        """Spot-check: the names now imported must not be borrowed any more."""
        borrowed = set(self._borrowed())
        for name in ("json", "os", "time", "logger", "console", "HAS_RICH",
                     "Panel", "LOCAL_TOOL_SCHEMAS", "CODING_SYSTEM_PROMPT"):
            with self.subTest(name=name):
                self.assertNotIn(name, borrowed)


if __name__ == "__main__":
    unittest.main()
