"""The post-release check must wait out registry lag, and still catch a gap.

v0.58.0 was published completely — dispatcher, ten platform packages, PyPI —
and "Verify the release actually shipped" failed it anyway: npm answered "no
such version" for a dispatcher written moments before. A release that fails
when nothing is wrong teaches everyone to ignore the check that exists to
catch v0.45.0-style tags pointing at nothing.

v0.103.0 failed the same way after npm's answer started coming from `npm
view`, whose cache and CDN can keep saying "no such version" for minutes. The
step now asks the registry directly, past every cache, as publish-npm does.

This runs the step's real script under GitHub's shell flags, with curl, node
and sleep replaced by stubs: curl answers for both registries and reports a
package as absent for its first N queries.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"


def _script() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in doc["jobs"]["verify-published"]["steps"]:
        if step.get("name") == "The tagged version must exist on PyPI and npm":
            return step["run"]
    raise AssertionError("verification step not found")


# Answers like the two registries. npm: the version path gets a status code,
# the package document a version list (only once the version path would say
# 200 — the stub keeps them consistent). PyPI: curl -f's exit status.
_CURL = r"""#!/bin/bash
url="${@: -1}"
present() {  # key -> succeeds once the key has been asked for more than N times
  f="$STATE/$1"; n=$(cat "$f.count" 2>/dev/null || echo 0)
  [ "${2:-count}" = count ] && echo $((n+1)) > "$f.count"
  want=$(cat "$f.absent" 2>/dev/null || echo 0)
  [ "$want" != never ] && [ "$n" -ge "$want" ]
}
case "$url" in
  *pypi.org*) present pypi && exit 0; exit 22 ;;
  *registry.npmjs.org/*)
    path="${url#https://registry.npmjs.org/}"; path="${path%%\?*}"
    name="${path%%/*}"; name="${name//%2F//}"
    if [ "$path" != "${path#*/}" ] && [[ "$*" == *http_code* ]]; then
      key="$(echo "$name@${path#*/}" | tr "/@" "__")"
      present "$key" && printf 200 || printf 404
      exit 0
    fi
    echo '{"versions":{}}'; exit 0 ;;
esac
exit 22
"""


class VerificationWaitsForTheRegistries(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "npm").mkdir()
        (self.tmp / "npm" / "package.json").write_text(json.dumps({
            "optionalDependencies": {"@artheras/aria-code-linux-x64": "9.9.9",
                                     "@artheras/aria-code-mcp-linux-x64": "9.9.9"}}))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.state = self.tmp / "state"
        self.state.mkdir()
        # absent-for: how many queries each spec misses before it appears;
        # "never" means it never does.
        for name, body in {
            "curl": _CURL,
            # The pins the step reads from npm/package.json.
            "node": '#!/bin/bash\necho @artheras/aria-code-linux-x64@9.9.9\n'
                    'echo @artheras/aria-code-mcp-linux-x64@9.9.9\n',
            "npm": '#!/bin/bash\necho "npm must not be asked: its cache lags the registry" >&2\nexit 99\n',
            "sleep": '#!/bin/bash\necho slept >> "$STATE/sleeps"\n',
        }.items():
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)

    def absent(self, spec: str, times) -> None:
        key = "pypi" if spec == "pypi" else spec.replace("/", "_").replace("@", "_")
        (self.state / f"{key}.absent").write_text(str(times))

    def run_step(self) -> subprocess.CompletedProcess[str]:
        env = {"PATH": f"{self.bin}:/usr/bin:/bin",
               "STATE": str(self.state), "INPUT_TAG": "v9.9.9", "GITHUB_REF_NAME": "v9.9.9",
               "NPM_RESULT": "success", "PYPI_RESULT": "success",
               "GITHUB_STEP_SUMMARY": str(self.tmp / "summary")}
        return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _script()],
                              cwd=self.tmp, env=env, capture_output=True, text=True, timeout=60)

    def sleeps(self) -> int:
        f = self.state / "sleeps"
        return len(f.read_text().splitlines()) if f.exists() else 0

    def test_everything_present_passes_without_waiting(self) -> None:
        proc = self.run_step()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.sleeps(), 0)

    def test_a_dispatcher_that_appears_late_passes(self) -> None:
        """The v0.58.0 case."""
        self.absent("@artheras/aria-code@9.9.9", 2)
        self.absent("pypi", 1)
        proc = self.run_step()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.sleeps(), 2)

    def test_a_package_that_never_appears_fails_and_is_named(self) -> None:
        self.absent("@artheras/aria-code-mcp-linux-x64@9.9.9", "never")
        proc = self.run_step()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no @artheras/aria-code-mcp-linux-x64@9.9.9", proc.stdout)
        self.assertNotIn("no @artheras/aria-code-linux-x64@9.9.9", proc.stdout)
        self.assertEqual(self.sleeps(), 30, "should give up after the retry budget")

    def test_npm_is_asked_past_its_cache(self) -> None:
        """The v0.103.0 case: npm view's cache said "absent" for five minutes."""
        proc = self.run_step()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("npm must not be asked", proc.stderr)

    def test_present_packages_are_not_asked_again(self) -> None:
        self.absent("@artheras/aria-code-mcp-linux-x64@9.9.9", 3)
        self.assertEqual(self.run_step().returncode, 0)
        count = self.state / "_artheras_aria-code-linux-x64_9.9.9.count"
        self.assertEqual(count.read_text().strip(), "1")


if __name__ == "__main__":
    unittest.main()
