"""Guards for the SafetyService adoption.

SafetyService existed with zero callers while the command layer reached for
the underlying primitives directly, each site with its own convention. Two
things must stay true now that the sites are routed through it.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "aria_code"
COMMANDS = SRC / "apps" / "cli" / "commands"

# Primitives the *command* layer must not call directly: it always has a config
# dict in hand, so it can and should ask the service, which sources mode,
# policy and network state from that one config. The tool layer is exempt on
# purpose — it is handed explicit params by its caller and has no config.
FORBIDDEN_CALLS = {
    "evaluate_command_policy",
    # Trading risk, same rule. brokers/ itself is exempt and stays direct: it
    # *is* the trading domain, and SafetyService is the facade over it — a
    # call the other way would invert the layering.
    "global_dry_run",
    "policy_from_config",
    "resolve_trading_mode",
}
# Deriving state from config is the service's job. Constructing a
# PrivacySettings outright is not — /privacy on|off legitimately builds one,
# and the service exposes no setter — so the rule names the derivation, not
# the class.
FORBIDDEN_ATTR_CALLS = {("PrivacySettings", "from_config")}


def _violations(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
            found.add(fn.id)
        elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
            if (fn.value.id, fn.attr) in FORBIDDEN_ATTR_CALLS:
                found.add(f"{fn.value.id}.{fn.attr}")
    return found


class CommandLayerUsesTheService(unittest.TestCase):
    def test_no_direct_primitive_use_in_command_layer(self):
        offenders = {}
        for path in sorted(COMMANDS.rglob("*.py")):
            hits = _violations(path)
            if hits:
                offenders[path.name] = sorted(hits)
        self.assertEqual(
            offenders, {},
            "command modules must go through SafetyService, not the raw "
            f"primitives: {offenders}",
        )


class ServiceReturnsTheSameClassesItsCallersUse(unittest.TestCase):
    """The tree is importable under two roots, so a facade can hand back a
    class that is *not* the one its callers compare against. The service must
    match whichever form its own domain's callers actually use — packaged for
    privacy, bare for brokers.trading. Asserting this is not pedantry: the two
    classes are unequal dataclasses that duck-type identically, so a mismatch
    fails silently.
    """

    def test_privacy_matches_the_packaged_form(self):
        from aria_code.privacy import PrivacySettings
        from aria_code.safety import SafetyService
        self.assertIs(type(SafetyService({}).privacy()), PrivacySettings)

    def test_trading_matches_the_bare_form(self):
        from brokers.trading import TradingPolicy
        from aria_code.safety import SafetyService
        self.assertIs(type(SafetyService({}).trading_policy()), TradingPolicy)


if __name__ == "__main__":
    unittest.main()
