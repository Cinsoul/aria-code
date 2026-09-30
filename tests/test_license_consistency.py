"""The declared license must be the same one in every place that declares it.

Before this test the repository named three different licenses at once. LICENSE
was BSL 1.1, pyproject and both npm manifests said BUSL-1.1, and
CONTRIBUTING.md told contributors their work would be published under MIT --
which had not been true since 4.2.0. A contributor who read CONTRIBUTING.md was
being given the wrong terms, and nothing failed, because no test reads these
files.

The fix is not "check that they all say Apache-2.0". Six files declaring the
same string independently will drift again; that is what happened. LICENSE is
the authority here, because it is the only one of them that is the license
rather than a claim about it, so every other file is checked against it.

The per-version history is deliberately asserted too. A license grant cannot be
withdrawn from someone who already holds it, so the 4.x releases stay BSL and
the pre-4.2 releases stay MIT no matter what this repository says today. Losing
that note from NOTICE would misrepresent what those releases are.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The SPDX identifier the repository is on, read from LICENSE rather than
# written here, so that changing the license is one edit and not seven.
_SPDX_BY_LICENSE_TITLE = {
    "Apache License": "Apache-2.0",
    "Business Source License 1.1": "BUSL-1.1",
    "MIT License": "MIT",
}


def _declared_license() -> str:
    """The SPDX id of whatever LICENSE actually contains."""
    head = (ROOT / "LICENSE").read_text(encoding="utf-8")[:400]
    for title, spdx in _SPDX_BY_LICENSE_TITLE.items():
        if title in head:
            return spdx
    raise AssertionError(f"LICENSE opens with no license this test recognises:\n{head[:200]}")


class EveryManifestAgreesWithTheLicenseFile(unittest.TestCase):
    def setUp(self) -> None:
        self.spdx = _declared_license()

    def test_pyproject_license_field(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^license\s*=\s*\{\s*text\s*=\s*"([^"]+)"', text, re.M)
        self.assertIsNotNone(match, "pyproject.toml declares no license field")
        self.assertEqual(match.group(1), self.spdx)

    def test_npm_main_package(self) -> None:
        manifest = json.loads((ROOT / "npm" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("license"), self.spdx)

    def test_the_platform_package_generator(self) -> None:
        # Each per-platform binary package is published separately, so a stale
        # string here ships five wrong manifests rather than one.
        text = (ROOT / "scripts" / "make_platform_packages.py").read_text(encoding="utf-8")
        found = set(re.findall(r'"license":\s*"([^"]+)"', text))
        self.assertEqual(found, {self.spdx}, f"generator stamps {found or 'nothing'}")

    def test_contributing_does_not_promise_different_terms(self) -> None:
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        wrong = {s for s in _SPDX_BY_LICENSE_TITLE.values() if s != self.spdx}
        for name in ("MIT License", "Business Source License"):
            if _SPDX_BY_LICENSE_TITLE.get(name, name) in wrong or name in wrong:
                self.assertNotIn(
                    name, text,
                    f"CONTRIBUTING.md still names {name}, but LICENSE is {self.spdx}",
                )


class TheLicenseIsOsiApprovedAndSaysSo(unittest.TestCase):
    """PyPI shows a license badge from the classifier, not the license field."""

    def test_an_osi_classifier_is_present_when_the_license_is_osi_approved(self) -> None:
        spdx = _declared_license()
        osi = {"Apache-2.0": "License :: OSI Approved :: Apache Software License",
               "MIT": "License :: OSI Approved :: MIT License"}
        expected = osi.get(spdx)
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        if expected is None:
            # BSL has no OSI classifier to give; absence is correct, not a gap.
            self.assertNotIn("License :: OSI Approved", text)
        else:
            self.assertIn(expected, text)


class NoticeKeepsThePerVersionHistory(unittest.TestCase):
    def setUp(self) -> None:
        self.notice = (ROOT / "NOTICE").read_text(encoding="utf-8")

    def test_the_superseded_licenses_are_still_named(self) -> None:
        # Not decoration. Someone running 4.4.2 holds a BSL grant, and someone
        # running 4.1.2 holds an MIT one; both are still in effect.
        self.assertIn("4.1.2", self.notice)
        self.assertIn("MIT", self.notice)
        self.assertIn("Business Source License 1.1", self.notice)

    def test_it_says_the_old_grants_cannot_be_withdrawn(self) -> None:
        self.assertRegex(self.notice, r"cannot be withdrawn|not\s+retroactive")

    def test_the_quant_engine_carve_out_is_not_claimed_while_it_is_in_the_tree(self) -> None:
        # CLOSING_SOURCE.md plans to move the engine to a private repository.
        # Until that happens, NOTICE must not imply it is already outside the
        # license -- the first draft of this NOTICE did exactly that.
        engine = ROOT / "src" / "aria_code" / "packages" / "quant_engine"
        in_tree = any(engine.rglob("*.py")) if engine.exists() else False
        if in_tree:
            self.assertNotIn("are not part of this repository", self.notice)
            self.assertIn("quant_engine", self.notice)


if __name__ == "__main__":
    unittest.main()
