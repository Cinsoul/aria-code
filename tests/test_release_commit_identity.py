"""Automated commits must be attributed to an account we actually mean.

GitHub attributes a commit by matching its author email to an account. The
release workflow committed as

    aria-release[bot] <aria-release[bot]@users.noreply.github.com>

a name picked without checking whether it was taken. It was: aria-release[bot]
is a GitHub App owned by an unrelated organisation, so every release commit in
this repository showed that organisation's logo and linked to their app.

The robust form of a noreply address carries the account's numeric id —
`<id>+<login>@users.noreply.github.com` — which GitHub resolves by id. A bare
`<login>@users.noreply.github.com` resolves by login, and a login is whatever
somebody registered first.
"""

from __future__ import annotations

import pathlib
import re
import unittest

WORKFLOWS = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"

_EMAIL = re.compile(r'git config(?: --global)? user\.email\s+"([^"]+)"')
_NAME = re.compile(r'git config(?: --global)? user\.name\s+"([^"]+)"')
# <numeric id>+<login>@users.noreply.github.com
_ID_PINNED = re.compile(r"^\d+\+[A-Za-z0-9-]+(?:\[bot\])?@users\.noreply\.github\.com$")

# github-actions[bot]'s account id, as GET /users/github-actions[bot] reports it.
GITHUB_ACTIONS_BOT = "41898282+github-actions[bot]@users.noreply.github.com"


class EveryCommitIdentityIsPinnedById(unittest.TestCase):
    def test_noreply_addresses_carry_an_account_id(self) -> None:
        found = 0
        for path in sorted(WORKFLOWS.glob("*.yml")):
            for email in _EMAIL.findall(path.read_text(encoding="utf-8")):
                found += 1
                with self.subTest(workflow=path.name, email=email):
                    if not email.endswith("@users.noreply.github.com"):
                        continue  # a real address resolves to its owner
                    self.assertRegex(
                        email, _ID_PINNED,
                        f"{path.name} commits as {email!r}, which GitHub resolves "
                        f"by login — and a login belongs to whoever registered "
                        f"it first. aria-release[bot] was already taken.",
                    )
        self.assertGreater(found, 0, "no commit identities found to check")


class TheReleaseCommitsAsGithubActions(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (WORKFLOWS / "release-on-merge.yml").read_text(encoding="utf-8")

    def test_the_email_is_github_actions_bot(self) -> None:
        self.assertEqual(_EMAIL.findall(self.text), [GITHUB_ACTIONS_BOT])

    def test_the_name_matches_the_account(self) -> None:
        self.assertEqual(_NAME.findall(self.text), ["github-actions[bot]"])

    def test_the_borrowed_identity_is_gone(self) -> None:
        live = [line for line in self.text.splitlines()
                if "aria-release[bot]" in line and not line.lstrip().startswith("#")]
        self.assertEqual(live, [])


if __name__ == "__main__":
    unittest.main()
