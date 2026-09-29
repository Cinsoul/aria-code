"""A released tag must be reachable from the default branch.

v4.4.2 was published to PyPI and npm from a commit that is not an ancestor of
main. The release line and the development line then diverged for a month:
main gained 73 commits, the tag's branch 72 different ones, and 25 shipped
modules under src/aria_code/ — packs/, evals/, workspace_service,
project_review, runtime/acceptance, runtime/repo_map — exist only on the tag.

Nothing caught it. publish.yml's verify-version compares the tag name against
the version strings in the files, which agreed; it never asked whether the
commit being released was on main. So the check passed on a branch that main
had never seen, and `pip install aria-code` has since been serving code that
is not in the repository's main line.

This test asks the question that was missing. Known-diverged tags are listed
so the suite is green on today's history; a NEW tag that leaves main fails.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Tags that already diverged when this guard was written. Do not add to this
# list to make a failure go away — a new entry means a release shipped code
# that main does not have, which is the thing being guarded against. Remove an
# entry once its work is merged into main.
KNOWN_DIVERGED = {
    "v4.4.2": (
        "released 2026-08-28 from a branch that never merged; carries 25 "
        "src/aria_code modules main lacks (packs/, evals/, workspace_*, "
        "project_review*, runtime/acceptance, runtime/repo_map)"
    ),
}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, check=False,
    )


class ReleaseTagsAreOnMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _git("rev-parse", "--git-dir").returncode != 0:
            raise unittest.SkipTest("not a git checkout")
        tags = _git("tag", "--list", "v*").stdout.split()
        if not tags:
            raise unittest.SkipTest("no release tags in this checkout")
        cls.tags = tags

    def _head_ref(self) -> str:
        for ref in ("origin/main", "main", "HEAD"):
            if _git("rev-parse", "--verify", "--quiet", ref).returncode == 0:
                return ref
        return "HEAD"

    def test_no_new_tag_has_left_the_main_line(self):
        head = self._head_ref()
        diverged = []
        for tag in sorted(self.tags):
            if _git("merge-base", "--is-ancestor", tag, head).returncode != 0:
                diverged.append(tag)

        unexpected = sorted(set(diverged) - set(KNOWN_DIVERGED))
        self.assertEqual(
            unexpected, [],
            "these tags were released from commits that are not on "
            f"{head}, so what users install is not what the repo builds: "
            f"{unexpected}",
        )

    def test_the_known_divergence_list_does_not_go_stale(self):
        """Once a listed tag is merged, its entry must go.

        A permanent allowlist stops being a record of debt and becomes
        background noise, which is how the original divergence survived.
        """
        head = self._head_ref()
        for tag in sorted(KNOWN_DIVERGED):
            if _git("rev-parse", "--verify", "--quiet", tag).returncode != 0:
                continue  # shallow clone or tag not fetched
            with self.subTest(tag=tag):
                merged = _git("merge-base", "--is-ancestor", tag, head).returncode == 0
                self.assertFalse(
                    merged,
                    f"{tag} is now on {head} — remove it from KNOWN_DIVERGED",
                )


if __name__ == "__main__":
    unittest.main()
