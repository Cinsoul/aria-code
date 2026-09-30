"""A caller must grant every permission the workflows it calls ask for.

GitHub caps a called workflow's GITHUB_TOKEN at whatever the caller was
granted. A scope the caller does not list is `none` for the callee, and the run
is rejected before any job starts:

    the workflow is requesting 'packages: write',
    but is only allowed 'contents: write'

That is a `startup_failure`: no jobs, no logs, no annotations, and no red X on
anything a person looks at. Nothing in the repository reports it.

It happened here. When release-on-merge.yml changed from "push a tag and let
publish.yml trigger on it" to "call publish.yml directly" — the fix for tags
that published nothing — publish.yml's jobs kept asking for `packages: write`
and `id-token: write` while release-on-merge.yml still granted only
`contents: write`. Every merge from #48 onward failed at startup. Four merges
produced no release, no tag and no version bump, and the only evidence was a
workflow run nobody opened.

The rule is mechanical, so a test can hold it.
"""

from __future__ import annotations

import pathlib
import unittest

import yaml

WORKFLOWS = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"

# GitHub's ordering. A caller granting "read" does not satisfy a callee's "write".
_RANK = {"none": 0, "read": 1, "write": 2}


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _max_permissions(doc: dict) -> dict[str, str]:
    """The strongest level each scope reaches anywhere in *doc*.

    Workflow-level and job-level blocks are merged, because the caller's grant
    caps every job in the called workflow, not just the ones declared at the top.
    """
    merged: dict[str, str] = {}

    def absorb(block) -> None:
        # `permissions: read-all` / `write-all` / {} are legal shorthands.
        if isinstance(block, str):
            if block in ("read-all", "write-all"):
                merged["__all__"] = "read" if block == "read-all" else "write"
            return
        for scope, level in (block or {}).items():
            if _RANK.get(level, 0) > _RANK.get(merged.get(scope, "none"), 0):
                merged[scope] = level

    absorb(doc.get("permissions"))
    for job in (doc.get("jobs") or {}).values():
        absorb((job or {}).get("permissions"))
    return merged


def _called_workflows(doc: dict) -> list[str]:
    """Local reusable workflows this document calls, as bare file names."""
    names = []
    for job in (doc.get("jobs") or {}).values():
        uses = (job or {}).get("uses")
        if isinstance(uses, str) and uses.startswith("./.github/workflows/"):
            names.append(uses.rsplit("/", 1)[-1])
    return names


class EveryCallerCoversWhatItCalls(unittest.TestCase):
    def test_callers_grant_at_least_what_their_callees_request(self) -> None:
        failures: list[str] = []

        for caller_path in sorted(WORKFLOWS.glob("*.yml")):
            caller = _load(caller_path)
            callees = _called_workflows(caller)
            if not callees:
                continue
            granted = _max_permissions(caller)
            if "__all__" in granted:
                continue  # write-all covers everything

            for name in callees:
                callee_path = WORKFLOWS / name
                with self.subTest(caller=caller_path.name, callee=name):
                    self.assertTrue(
                        callee_path.exists(),
                        f"{caller_path.name} calls {name}, which does not exist",
                    )
                    for scope, level in _max_permissions(_load(callee_path)).items():
                        if scope == "__all__":
                            continue
                        have = granted.get(scope, "none")
                        if _RANK.get(level, 0) > _RANK.get(have, 0):
                            failures.append(
                                f"{caller_path.name} grants {scope}: {have}, but "
                                f"{name} requests {scope}: {level}"
                            )

        self.assertEqual(
            failures, [],
            "a called workflow asks for more than its caller was granted, which "
            "GitHub rejects as startup_failure before any job runs:\n  "
            + "\n  ".join(failures),
        )


class TheReleaseCallerIsWiredAsExpected(unittest.TestCase):
    """Guards the specific arrangement, so the general test cannot pass vacuously."""

    def setUp(self) -> None:
        self.doc = _load(WORKFLOWS / "release-on-merge.yml")

    def test_it_still_calls_both_publishing_workflows(self) -> None:
        # If this ever stops being true the general test above goes quiet, and
        # the scopes below would look like unexplained over-permissioning.
        self.assertEqual(
            sorted(_called_workflows(self.doc)),
            ["build-native-binaries.yml", "publish.yml"],
        )

    def test_the_scopes_publishing_needs_are_granted(self) -> None:
        granted = _max_permissions(self.doc)
        for scope in ("contents", "packages", "id-token"):
            with self.subTest(scope=scope):
                self.assertEqual(granted.get(scope), "write")


# Whether the callees declare on.workflow_call, and accept a "tag" input, is
# already asserted by tests/test_release_chain.py::CalledWorkflowsAcceptATag.
# Not repeated here: two tests owning one fact means one of them rots.


if __name__ == "__main__":
    unittest.main()
