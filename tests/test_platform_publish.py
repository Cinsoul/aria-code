"""The platform publish step does not pass while a package is missing.

v0.81.0's darwin-arm64 and v0.86.0's mcp-linux-arm64 were never published,
and the step passed: it skipped any package `npm view` said existed, trusting
the exit status with the output discarded. The dispatcher then waited an hour
for the missing package and failed. The step now asks the registry directly,
and before it reports success every package must be visible — a missing one
is published again, and after the deadline the step fails naming it.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAMES = [f"aria-code-{p}" for p in ("darwin-arm64", "darwin-x64", "linux-arm64", "linux-x64", "win32-x64")]
NAMES += [n.replace("aria-code-", "aria-code-mcp-") for n in NAMES]


def _step() -> str:
    jobs = yaml.safe_load((ROOT / ".github/workflows/build-native-binaries.yml").read_text())["jobs"]
    for job in jobs.values():
        for step in job.get("steps", []):
            if step.get("name") == "Publish each platform package":
                return step["run"]
    raise AssertionError("no publish step")


class PlatformPublish(unittest.TestCase):
    def _run(self, *, lose: str = "", never: str = "", deadline_zero: bool = False):
        script = _step().replace("sleep 30", "sleep 0")
        if deadline_zero:
            script = script.replace("+ 1200", "+ 0", 1)
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            for name in NAMES:
                (work / "npm/platforms" / name).mkdir(parents=True)
                (work / "npm/platforms" / name / "package.json").write_text("{}")
            bin_dir, registry, log = work / "bin", work / "registry", work / "publishes"
            bin_dir.mkdir()
            registry.write_text("")
            # node: the spec of a package dir, or the packed size from stdin.
            (bin_dir / "node").write_text(
                '#!/bin/sh\nif [ "$#" -ge 3 ]; then d=$(basename "$(dirname "$3")"); echo "@artheras/$d@1.0.0"; '
                "else echo 100; fi\n")
            # npm publish: recorded; `lose` is accepted once without appearing,
            # `never` never appears.
            (bin_dir / "npm").write_text(
                "#!/bin/sh\n"
                'if [ "$1" = publish ]; then name=$(basename "$PWD"); echo "$name" >> ' + str(log) + "\n"
                '  if [ "$name" = "' + never + '" ]; then exit 0; fi\n'
                '  if [ "$name" = "' + lose + '" ] && [ "$(grep -c "^$name$" ' + str(log) + ')" = 1 ]; then exit 0; fi\n'
                '  echo "$name" >> ' + str(registry) + "\nfi\nexit 0\n")
            # curl: 200 / the version list only for what reached the registry.
            (bin_dir / "curl").write_text(
                "#!/bin/sh\n"
                'for a in "$@"; do case "$a" in (https://*) url="$a";; esac; done\n'
                'name=$(echo "$url" | sed -e "s|https://registry.npmjs.org/@artheras%2F||" -e "s|[/?].*||")\n'
                'if grep -qx "$name" ' + str(registry) + '; then hit=1; else hit=0; fi\n'
                'case "$*" in *http_code*) [ $hit = 1 ] && printf 200 || printf 404; exit 0;; esac\n'
                '[ $hit = 1 ] && echo \'{"versions":{"1.0.0":{}}}\' || echo \'{"versions":{}}\'\n')
            for tool in ("node", "npm", "curl"):
                (bin_dir / tool).chmod(0o755)
            env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", NODE_AUTH_TOKEN="t")
            result = subprocess.run(["bash", "-c", script], cwd=work, env=env, capture_output=True, text=True,
                                    timeout=60)
            published = log.read_text().split() if log.exists() else []
            return result, published

    def test_all_ten_are_published_once(self):
        result, published = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sorted(published), sorted(NAMES))
        self.assertIn("All 10 platform packages are visible", result.stdout)

    def test_a_package_that_did_not_arrive_is_published_again(self):
        result, published = self._run(lose="aria-code-mcp-linux-arm64")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(published.count("aria-code-mcp-linux-arm64"), 2)
        self.assertIn("not visible yet, publishing again: @artheras/aria-code-mcp-linux-arm64@1.0.0", result.stdout)

    def test_the_step_fails_naming_a_package_that_never_appears(self):
        result, _ = self._run(never="aria-code-darwin-arm64", deadline_zero=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Not on the registry: @artheras/aria-code-darwin-arm64@1.0.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
