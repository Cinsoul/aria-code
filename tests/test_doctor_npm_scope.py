"""doctor must not report npm-launcher problems to people who did not use npm.

A clean `pip install aria-code` on a machine with no Node ended its first
`aria-code doctor` with "1 errors" and six warnings, all about an npm launcher
that was never installed. The error's repair suggestion —
`node $(npm root -g)/aria-code/scripts/postinstall.js` — was not merely wrong
for that user; it cannot run at all without node.

These checks are real and worth keeping for npm users, so the fix is scope,
not deletion: report the group as skipped when there is no npm installation
for it to be about.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

from doctor import npm_runtime_checks


class NonNpmInstallSkipsTheGroup(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ("ARIA_HOME", "ARIA_CODE_HOME")}
        self._home = tempfile.mkdtemp()
        os.environ["ARIA_HOME"] = self._home
        os.environ.pop("ARIA_CODE_HOME", None)
        # cwd must not look like a source checkout, or that branch applies.
        self._cwd = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_no_npm_install_yields_one_skip_and_no_error(self):
        checks = npm_runtime_checks(cwd=self._cwd)
        self.assertEqual(len(checks), 1, [c.name for c in checks])
        self.assertEqual(checks[0].status, "skip")
        self.assertEqual(checks[0].name, "npm_runtime")

    def test_never_suggests_a_command_that_needs_node(self):
        for check in npm_runtime_checks(cwd=self._cwd):
            self.assertNotIn("node ", check.suggestion or "")

    def test_install_metadata_alone_brings_the_checks_back(self):
        """Evidence of an npm install means the diagnostics apply again."""
        info = pathlib.Path(self._home) / ".npm-install-info.json"
        info.write_text(json.dumps({"version": "4.4.2"}), encoding="utf-8")
        checks = npm_runtime_checks(cwd=self._cwd)
        self.assertGreater(len(checks), 1)
        self.assertNotIn("skip", {c.status for c in checks if c.name == "npm_runtime"})

    def test_a_broken_npm_install_still_reports_problems(self):
        """Scope, not silence: with npm evidence present, errors must surface."""
        (pathlib.Path(self._home) / ".npm-install-info.json").write_text("{}", encoding="utf-8")
        statuses = {c.status for c in npm_runtime_checks(cwd=self._cwd)}
        self.assertTrue(
            statuses & {"err", "warn"},
            "an npm install with no aria_cli.py should still be flagged",
        )


class SourceCheckoutIsStillDiagnosed(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("ARIA_HOME")
        self._home = tempfile.mkdtemp()
        os.environ["ARIA_HOME"] = self._home
        self._cwd = pathlib.Path(tempfile.mkdtemp())
        (self._cwd / "aria_cli.py").write_text("# source checkout marker\n", encoding="utf-8")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ARIA_HOME", None)
        else:
            os.environ["ARIA_HOME"] = self._saved

    def test_running_from_a_clone_is_not_treated_as_absent(self):
        checks = npm_runtime_checks(cwd=self._cwd)
        self.assertGreater(len(checks), 1,
                           "a source checkout has its own guidance and must not be skipped")


if __name__ == "__main__":
    unittest.main()
