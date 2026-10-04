"""What Aria shows users and where it sends them must be true and ours.

Found in one sweep of every hardcoded host (2026-10-04):

- Every interactive session opened with "Keep working from anywhere — check
  progress or reply to any session from mobile app, desktop app, or
  https://arthera.finance/sessions/<id>. To keep session in this terminal only,
  run /remote-control". Sessions are stored only locally (session_jsonl.py),
  the page is the site's catch-all (identical for any id), there is no mobile
  app, and /remote-control does not exist.
- The source installer switched to third-party package and Python mirrors on
  any failed download, without asking, and fetched Python through ghfast.top,
  a public GitHub proxy whose operator is unknown.
- hooks.json's comment linked to https://aria.code/docs/hooks, which cannot
  resolve (.code is not a top-level domain).
- scripts/generate_demo_video.py rendered the same session-sync claim, on
  arthera.ai — a domain no one has registered — plus "100% local-first,
  zero telemetry", which the default cloud model contradicts. Nothing used it.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "aria_code"


def _source_files():
    return sorted(SRC.rglob("*.py"))


class TestNoFeatureThatDoesNotExist:
    def test_no_session_sync_is_advertised(self):
        offending = [str(p.relative_to(ROOT)) for p in _source_files()
                     if re.search(r"Keep working from anywhere|随时随地继续工作|render_session_banner",
                                  p.read_text(encoding="utf-8"))]
        assert not offending, offending

    def test_no_command_is_advertised_unless_it_is_registered(self):
        cli = (SRC / "aria_cli.py").read_text(encoding="utf-8")
        for path in _source_files():
            for command in set(re.findall(r"/remote-control\b", path.read_text(encoding="utf-8"))):
                assert f'"{command}"' in cli, f"{path.relative_to(ROOT)} tells users to run {command}"

    def test_the_fake_demo_generator_is_gone(self):
        assert not (ROOT / "scripts" / "generate_demo_video.py").exists()


class TestTheSourceInstallerAsksBeforeUsingMirrors:
    TEXT = (ROOT / "install.sh").read_text(encoding="utf-8")

    def test_mirrors_only_when_the_user_opts_in(self):
        calls = [line.strip() for line in self.TEXT.splitlines()
                 if "enable_cn_mirror" in line and not line.strip().startswith(("#", "enable_cn_mirror()"))]
        assert calls == ['[[ "$ARIA_CN" == "1" ]] && enable_cn_mirror'], calls

    def test_failures_suggest_the_mirror_instead_of_switching(self):
        assert self.TEXT.count("re-run with ARIA_CN=1") == 2

    def test_python_builds_do_not_come_through_an_unknown_proxy(self):
        mirror = re.search(r'^CN_PY_REPO="([^"]+)"', self.TEXT, re.M).group(1)
        assert mirror == "https://registry.npmmirror.com/-/binary/python-build-standalone"
        assert "ghfast" not in self.TEXT.replace("came through ghfast.top before", "")


def test_the_hooks_example_links_somewhere_real(tmp_path):
    from aria_code.apps.cli import hooks

    target = tmp_path / "hooks.json"
    hooks.create_example_hooks(target)
    comment = json.loads(target.read_text(encoding="utf-8"))["_comment"]
    assert "https://github.com/artheras/aria-code/" in comment
    assert "aria.code/" not in comment
