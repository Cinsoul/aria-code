"""The version counter must not hand back a version that already shipped.

One merge to main is one patch release, so this number is computed
automatically and nobody reviews it. Getting it wrong is not a cosmetic
problem: PyPI refuses a version that exists, so the whole release fails at the
last step, after the tag is already pushed.

The repository has been in both drift states. pyproject said 4.4.1 while 4.4.2
was live on PyPI and npm — deriving from the file alone would have tried to
republish 4.4.2. The reverse happens when a tag is pushed and publishing then
fails.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bump_version.py"


def _load():
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump = _load()


class TripleParsing(unittest.TestCase):
    def test_plain_versions(self):
        self.assertEqual(bump._triple("4.4.1"), (4, 4, 1))
        self.assertEqual(bump._triple("10.0.120"), (10, 0, 120))

    def test_prerelease_and_build_metadata_keep_their_patch(self):
        self.assertEqual(bump._triple("4.4.1-rc.1"), (4, 4, 1))
        self.assertEqual(bump._triple("4.4.1+build7"), (4, 4, 1))

    def test_shapes_it_must_refuse(self):
        for bad in ("4.4", "", "x.y.z", "4.4.x", "v4.4.1", "4..1"):
            with self.subTest(version=bad):
                self.assertIsNone(bump._triple(bad))


class NextPatchOutput(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--next-patch"],
            capture_output=True, text=True, cwd=ROOT,
        )
        return proc

    def test_it_prints_one_plain_version_on_stdout(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        printed = proc.stdout.strip()
        self.assertEqual(len(printed.split("\n")), 1, f"stdout was {printed!r}")
        self.assertIsNotNone(bump._triple(printed), f"not a version: {printed!r}")

    def test_the_next_version_is_higher_than_every_released_tag(self):
        """The whole point. A number that already exists fails the publish."""
        printed = bump._triple(self._run().stdout.strip())
        tags = subprocess.run(["git", "tag", "--list", "v*"],
                              capture_output=True, text=True, cwd=ROOT).stdout.split()
        released = [t for t in (bump._triple(name[1:]) for name in tags) if t]
        if not released:
            self.skipTest("no release tags in this checkout")
        self.assertGreater(printed, max(released))

    def test_it_is_higher_than_the_version_in_the_files(self):
        printed = bump._triple(self._run().stdout.strip())
        self.assertGreater(printed, bump._triple(bump.read_versions()["pyproject.toml"]))

    def test_drift_is_reported_not_absorbed(self):
        """When the tag is ahead of the files, that must be said out loud."""
        proc = self._run()
        from_file = bump._triple(bump.read_versions()["pyproject.toml"])
        from_tag = bump._highest_tag_triple()
        if from_tag and from_tag > from_file:
            self.assertIn("ahead of", proc.stderr,
                          "tag is ahead of pyproject and nothing said so")
        else:
            self.assertNotIn("ahead of", proc.stderr)

    def test_reading_the_next_version_changes_nothing(self):
        before = bump.read_versions()
        self._run()
        self.assertEqual(bump.read_versions(), before)


if __name__ == "__main__":
    unittest.main()
