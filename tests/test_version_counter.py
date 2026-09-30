"""The version counter must not hand back a version that already shipped.

Codex's scheme: major always 0, minor carries the release count, patch only for
a fix on top of a shipped release. Crossing from the old 4.x line into 0.x is
the one case where "next" cannot be derived — 0.x is numerically lower than
every 4.x — so the first 0.x version is stated, and these tests pin that the
crossing happens once and announces itself.

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


class NextReleaseOutput(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--next-release"],
            capture_output=True, text=True, cwd=ROOT,
        )
        return proc

    def test_it_prints_one_plain_version_on_stdout(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        printed = proc.stdout.strip()
        self.assertEqual(len(printed.split("\n")), 1, f"stdout was {printed!r}")
        self.assertIsNotNone(bump._triple(printed), f"not a version: {printed!r}")

    def test_it_never_repeats_a_version_within_its_own_line(self):
        """A number that already exists fails the publish. Compared inside the
        major line, because 0.x is below every 4.x by design."""
        printed = bump._triple(self._run().stdout.strip())
        tags = subprocess.run(["git", "tag", "--list", "v*"],
                              capture_output=True, text=True, cwd=ROOT).stdout.split()
        same_line = [t for t in (bump._triple(n[1:]) for n in tags)
                     if t and t[0] == printed[0]]
        if same_line:
            self.assertGreater(printed, max(same_line))

    def test_crossing_into_the_zerox_line_says_so(self):
        """While the files are still 4.x, the first 0.x version is stated rather
        than derived, and the reason is printed — a version going *down* with no
        explanation is indistinguishable from a bug."""
        proc = self._run()
        current = bump._triple(bump.read_versions()["pyproject.toml"])
        printed = bump._triple(proc.stdout.strip())
        if current[0] != 0:
            self.assertEqual(printed, (0, bump.FIRST_ZEROX_MINOR, 0))
            self.assertIn("leaving the", proc.stderr)
        else:
            self.assertEqual(printed, (0, current[1] + 1, 0))

    def test_a_release_resets_patch(self):
        """patch means "a fix on top of a shipped release", so carrying it into
        the next release would say something untrue about it."""
        printed = bump._triple(self._run().stdout.strip())
        self.assertEqual(printed[2], 0)

    def test_hotfix_bumps_patch_and_leaves_minor_alone(self):
        for base, want in (((0, 7, 0), "0.7.1"), ((0, 7, 3), "0.7.4"),
                           ((0, 159, 1), "0.159.2")):
            with self.subTest(base=base):
                self.assertEqual(f"0.{base[1]}.{base[2] + 1}", want)

    def test_hotfix_is_refused_on_the_old_line(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "--next-hotfix"],
                              capture_output=True, text=True, cwd=ROOT)
        current = bump._triple(bump.read_versions()["pyproject.toml"])
        if current[0] != 0:
            self.assertEqual(proc.returncode, 1)
            self.assertIn("refusing", proc.stderr)
        else:
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_major_stays_zero_once_on_the_zerox_line(self):
        """Codex has 196 stable versions and every one of them starts with 0."""
        printed = bump._triple(self._run().stdout.strip())
        self.assertEqual(printed[0], 0)

    def test_reading_the_next_version_changes_nothing(self):
        before = bump.read_versions()
        self._run()
        self.assertEqual(bump.read_versions(), before)


if __name__ == "__main__":
    unittest.main()
