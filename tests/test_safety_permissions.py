import unittest

from safety import PermissionService, evaluate_command_policy, normalize_command


class SafetyPermissionTests(unittest.TestCase):
    def test_normalize_command_uses_shell_quoting(self):
        self.assertEqual(normalize_command("python script.py"), "python3 script.py")
        self.assertEqual(normalize_command("pip install rich"), "pip3 install rich")

    def test_read_only_blocks_medium_commands(self):
        decision = PermissionService(mode="read-only", command_policy="balanced").evaluate_command("pytest -q")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk, "medium")

    def test_network_can_be_disabled(self):
        decision = evaluate_command_policy("curl https://example.com", "full", network_enabled=False)
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.network)
        self.assertIn("Network command blocked", decision.reason)

    def test_tool_permissions(self):
        svc = PermissionService(mode="workspace-write")
        self.assertTrue(svc.evaluate_tool("read_file").allowed)
        write = svc.evaluate_tool("write_file")
        self.assertTrue(write.allowed)
        self.assertTrue(write.requires_approval)
        unknown = svc.evaluate_tool("unknown_tool")
        self.assertFalse(unknown.allowed)

    def test_full_policy_allows_high_risk_but_marks_risk(self):
        decision = evaluate_command_policy("git push origin main", "full")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.risk, "high")


class InvalidModeFailsClosedTests(unittest.TestCase):
    """An unrecognised permission mode must never be laxer than read-only.

    The assertion is deliberately *relative*, not "invalid == read-only": the
    point is the direction of the fallback, and a relative test keeps holding
    if the mode ladder is ever extended. The regression it guards is real —
    apps/cli/tools/system_tools.py used to default this argument to "safe",
    which is a *policy* name and no PermissionMode, so every caller that
    reached the default silently got workspace-write.
    """

    PROBES = (
        "touch newfile.txt",
        "mkdir build",
        "git commit -m x",
        "pip install requests",
        "curl https://example.com",
    )

    def _decide(self, command, mode):
        return evaluate_command_policy(command, "balanced", mode=mode, network_enabled=True)

    def test_unknown_mode_is_no_laxer_than_read_only(self):
        for bogus in ("safe", "", "Workspace-Write", "yolo", "full-acess"):
            for command in self.PROBES:
                with self.subTest(mode=bogus, command=command):
                    strict = self._decide(command, "read-only")
                    fallback = self._decide(command, bogus)
                    if not strict.allowed:
                        self.assertFalse(
                            fallback.allowed,
                            f"{bogus!r} allowed {command!r} that read-only denies",
                        )
                        # Denying but offering approval is still laxer: it hands
                        # the user a prompt that can unlock the command.
                        self.assertLessEqual(
                            bool(fallback.requires_approval),
                            bool(strict.requires_approval),
                            f"{bogus!r} offers approval for {command!r} where read-only hard-blocks",
                        )

    def test_policy_names_are_not_modes(self):
        """The two vocabularies are disjoint; passing one for the other is a bug."""
        from aria_code.safety.permissions import PermissionMode

        modes = {m.value for m in PermissionMode}
        for policy in ("safe", "balanced", "full"):
            self.assertNotIn(policy, modes)


if __name__ == "__main__":
    unittest.main()
