"""The per-platform npm packages must be installable and runnable as published.

npm runs no code from these packages — there is no postinstall any more — so
everything that has to be right is in the metadata and the file modes. Each of
these has a concrete failure: a missing +x installs fine and fails with EACCES
on first run; a wrong `os`/`cpu` makes npm download a binary it cannot execute;
a filename without .exe is simply not found on Windows.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import stat
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "make_platform_packages.py"
JS_MODULE = ROOT / "npm" / "lib" / "platform.js"


def _load():
    spec = importlib.util.spec_from_file_location("make_platform_packages", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mpp = _load()


class KeysAgreeWithTheDispatcher(unittest.TestCase):
    def test_python_and_javascript_list_the_same_platforms(self):
        """Two lists, one truth. A key in one and not the other ships a package
        the dispatcher never looks for, or looks for one nobody built."""
        js = JS_MODULE.read_text(encoding="utf-8")
        block = re.search(r"PLATFORM_KEYS = Object\.freeze\(\[(.*?)\]\)", js, re.S)
        self.assertIsNotNone(block, "could not find PLATFORM_KEYS in platform.js")
        from_js = tuple(re.findall(r'"([^"]+)"', block.group(1)))
        self.assertEqual(from_js, mpp.PLATFORM_KEYS)


class GeneratedPackages(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.fake = self.tmp / "fake-bin"
        self.fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.out = self.tmp / "platforms"

    def _build(self, key, mcp=False):
        return mpp.build_one(key, "9.9.9", self.fake, self.out, mcp=mcp)

    def test_windows_binaries_get_exe_and_nothing_else_does(self):
        win = self._build("win32-x64")
        self.assertTrue((win / "bin" / "aria-code-bin.exe").is_file())
        for key in ("darwin-arm64", "linux-x64"):
            pkg = self._build(key)
            self.assertTrue((pkg / "bin" / "aria-code-bin").is_file())
            self.assertFalse((pkg / "bin" / "aria-code-bin.exe").exists())

    def test_the_binary_is_executable(self):
        pkg = self._build("linux-x64")
        mode = (pkg / "bin" / "aria-code-bin").stat().st_mode
        for bit in (stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH):
            self.assertTrue(mode & bit, "binary would install without +x")

    def test_os_and_cpu_let_npm_refuse_the_wrong_machine(self):
        for key, want_os, want_cpu in (
            ("darwin-arm64", "darwin", "arm64"),
            ("linux-x64", "linux", "x64"),
            ("win32-x64", "win32", "x64"),
        ):
            with self.subTest(key=key):
                meta = json.loads((self._build(key) / "package.json").read_text())
                self.assertEqual(meta["os"], [want_os])
                self.assertEqual(meta["cpu"], [want_cpu])

    def test_package_name_matches_what_the_dispatcher_requires(self):
        meta = json.loads((self._build("darwin-arm64") / "package.json").read_text())
        self.assertEqual(meta["name"], "@artheras/aria-code-darwin-arm64")
        self.assertEqual(meta["version"], "9.9.9")
        self.assertEqual(meta["files"], ["bin/"])

    def test_the_mcp_binary_has_its_own_package(self):
        cli = self._build("darwin-arm64")
        mcp = self._build("darwin-arm64", mcp=True)
        self.assertFalse((cli / "bin" / "aria-code-mcp-bin").exists())
        self.assertTrue((mcp / "bin" / "aria-code-mcp-bin").is_file())
        self.assertEqual(json.loads((mcp / "package.json").read_text())["name"],
                         "@artheras/aria-code-mcp-darwin-arm64")

    def test_rebuilding_replaces_rather_than_accumulates(self):
        pkg = self._build("linux-x64")
        stale = pkg / "bin" / "aria-code-mcp-bin"
        stale.write_bytes(b"stale")
        pkg = self._build("linux-x64")
        self.assertFalse(stale.exists(),
                         "a stale binary from a previous build would be published")


class ArgumentHandling(unittest.TestCase):
    def test_an_unknown_platform_key_is_refused(self):
        with self.assertRaises(SystemExit):
            mpp._pairs(["sunos-x64=/dev/null"], "--binary")

    def test_a_missing_file_is_refused_rather_than_packaged_empty(self):
        with self.assertRaises(SystemExit):
            mpp._pairs(["linux-x64=/nonexistent/aria-code-bin"], "--binary")

    def test_a_pair_without_an_equals_sign_is_refused(self):
        with self.assertRaises(SystemExit):
            mpp._pairs(["linux-x64"], "--binary")


if __name__ == "__main__":
    unittest.main()
