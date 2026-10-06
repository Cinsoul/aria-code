"""The platform publish step makes sure every package reaches npm.

It skipped any package `npm view` answered for — trusting the exit status,
with the output thrown away — and npm versions differ on whether a missing
version is an error there. It now asks the registry directly, and checks that
every package can be seen, publishing a missing one again. npm itself can be
slow to expose a package (v0.86.0's mcp-linux-arm64 appeared 15 minutes after
its neighbours), so one still missing after 45 minutes is named in a warning
and the dispatcher's own wait makes the final call.
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
            self.assertIn("+ 2700", script)
            script = script.replace("+ 2700", "+ 0", 1)
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

    def test_a_package_still_missing_at_the_deadline_is_named_not_fatal(self):
        """npm has taken 15 minutes, maybe 80, to expose a package: a slow
        registry must not fail the release here — the dispatcher's wait decides."""
        result, _ = self._run(never="aria-code-darwin-arm64", deadline_zero=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("::warning::Not on the registry yet: @artheras/aria-code-darwin-arm64@1.0.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
