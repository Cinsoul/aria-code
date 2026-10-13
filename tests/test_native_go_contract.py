"""The Go runtime's change contract must match runtime/contract.py."""
import json
import os
import subprocess

import pytest

from aria_code.apps.cli.providers.runtime_bridge import build_change_contract


def binary():
    value = os.environ.get("ARIA_GO_RUNTIME_BINARY")
    if not value:
        pytest.skip("The native-runtime CI job builds this executable")
    return value


CALLS = [
    ("read_file", {"path": "billing/invoice.py"}),
    ("search_code", {"query": "refresh"}),
    ("write_file", {"path": "src/auth/session.py"}),
    ("edit_file", {"path": "./src/auth/deep/nested.py"}),
    ("write_file", {"path": "src/auth/secrets.py"}),
    ("write_file", {"path": "billing/invoice.py"}),
    ("write_file", {"path": "tests/test_session.py"}),
    ("write_file", {"path": "../escape.py"}),
    ("write_file", {"path": "/etc/hosts"}),
    ("write_file", {"path": "migrations/0001.sql"}),
    ("write_file", {"path": "数据/文件.py"}),
    ("apply_patch", {"patch": "+++ b/src/auth/a.py\n+++ b/billing/b.py\n"}),
    ("run_command", {"command": "pytest -q"}),
    ("run_command", {"command": "ls -la"}),
    ("run_command", {"command": "git push origin main"}),
    ("run_command", {"command": "npm install left-pad"}),
    ("run_command", {"command": "rm -rf build"}),
    ("run_command", {"command": "touch billing/x.py"}),
    ("run_command", {"command": "cp a src/auth/b.py"}),
    ("run_command", {"command": "git add -A"}),
    ("run_command", {"command": "python manage.py migrate"}),
    ("web_fetch", {"url": "https://example.com"}),
    ("broker_order", {}),
    ("custom_tool", {}),
]

POLICIES = {
    "none": None,
    "no-contract-section": "other: 1\n",
    "empty-file": "",
    "null-contract": "contract:\n",
    "full": """
contract:
  goal: ignored, the request is the goal
  allow: [src/auth/**, tests/**, "数据/"]
  restrict: [src/auth/secrets.py]
  forbid: [git.push, cloud.deploy, database.write]
  max_level: 3
  success:
    - existing tests pass
    - expired sessions refresh
""",
    "directory-patterns": """
contract:
  allow: ["./src/", "**/*.sql", "tests/test_?ession.py"]
  max_level: "2"
""",
    "string-fields": """
contract:
  allow: src/**
  forbid: git.push
  success: tests pass
""",
    "duplicate-forbid": "contract:\n  forbid: [git.push, git.push, cloud.deploy]\n",
    "numbers": "contract:\n  success: [1, 2.5, true]\n  max_level: 2.9\n",
    "max-level-zero": "contract:\n  max_level: 0\n",
    "unknown-capability": "contract:\n  forbid: [git.push, teleport]\n",
    "unknown-capabilities": "contract:\n  forbid: [warp, teleport]\n",
    "max-level-high": "contract:\n  max_level: 7\n",
    "max-level-text": "contract:\n  max_level: three\n",
    "max-level-list": "contract:\n  max_level: [1]\n",
    "allow-number": "contract:\n  allow: 5\n",
    "top-level-list": "- a\n- b\n",
    "contract-list": "contract: [a]\n",
}

GOALS = ["fix the auth refresh bug", "  spread\n over   lines  ", "长" * 250, ""]


def go_contract(root, goal):
    request = {"root": str(root), "goal": goal, "calls": [{"tool": t, "params": p} for t, p in CALLS]}
    result = subprocess.run([binary(), "contract"], input=json.dumps(request), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def python_contract(root, goal):
    contract = build_change_contract({"workspace_root": str(root)}, goal)
    if contract is None:
        return {"contract": None}
    verdicts = []
    for tool, params in CALLS:
        verdict = contract.check(tool, params)
        entry = {"allowed": verdict.allowed, "rule": verdict.rule, "reason": verdict.reason, "level": verdict.assessment.level}
        if not verdict.allowed:
            entry["error"] = verdict.as_tool_result(tool)["error"]
        verdicts.append(entry)
    return {
        "contract": {
            "goal": contract.goal, "allow": list(contract.allow), "restrict": list(contract.restrict),
            "forbid": sorted(contract.forbid), "max_level": contract.max_level, "success": list(contract.success),
            "load_error": contract.load_error, "render": contract.render(), "prompt_block": contract.prompt_block(),
        },
        "verdicts": verdicts,
    }


@pytest.mark.parametrize("policy", sorted(POLICIES))
def test_go_contract_matches_python(tmp_path, policy):
    root = tmp_path / "workspace"
    (root / "src" / "auth").mkdir(parents=True)
    text = POLICIES[policy]
    if text is not None:
        (root / ".aria").mkdir()
        (root / ".aria" / "policy.yaml").write_text(text, encoding="utf-8")
    for goal in GOALS:
        assert go_contract(root, goal) == python_contract(root, goal), (policy, goal)


def test_go_contract_fails_closed_on_invalid_yaml(tmp_path):
    root = tmp_path / "workspace"
    (root / ".aria").mkdir(parents=True)
    (root / ".aria" / "policy.yaml").write_text("contract: [unclosed\n", encoding="utf-8")
    go = go_contract(root, "goal")["contract"]
    python = python_contract(root, "goal")["contract"]
    # The parser's own message differs between PyYAML and yaml.v3; the rest must not.
    prefix = f"{root / '.aria' / 'policy.yaml'}: not valid YAML ("
    assert go["load_error"].startswith(prefix) and python["load_error"].startswith(prefix)
    assert go["max_level"] == python["max_level"] == 0
    assert [v["allowed"] for v in go_contract(root, "goal")["verdicts"]] == [v["allowed"] for v in python_contract(root, "goal")["verdicts"]]
