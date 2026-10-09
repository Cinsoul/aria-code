"""Change contracts: declared in .aria/policy.yaml, enforced on every tool call."""

import asyncio

import pytest

from aria_code.runtime import AgentEventComplete, AgentEventStatus, AgentOptions, ToolExecutor, run_agent
from aria_code.runtime.contract import ChangeContract, ContractError

POLICY = """\
contract:
  allow: [src/auth/**, tests/**]
  restrict: [src/auth/secrets.py]
  forbid: [git.push, cloud.deploy]
  max_level: 3
  success: [existing tests pass]
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".aria").mkdir()
    (tmp_path / ".aria" / "policy.yaml").write_text(POLICY)
    return tmp_path


def test_loads_from_the_policy_file(project):
    contract = ChangeContract.load(project)
    assert contract.allow == ("src/auth/**", "tests/**")
    assert contract.forbid == {"git.push", "cloud.deploy"}
    assert contract.max_level == 3
    assert contract.source.endswith("policy.yaml")


def test_no_policy_file_or_section_means_no_contract(tmp_path):
    assert ChangeContract.load(tmp_path) is None
    (tmp_path / ".aria").mkdir()
    (tmp_path / ".aria" / "policy.yaml").write_text("other: 1\n")
    assert ChangeContract.load(tmp_path) is None


@pytest.mark.parametrize("text", [
    "contract: [1, 2]\n",
    "contract:\n  forbid: [git.pussh]\n",
    "contract:\n  max_level: 9\n",
    "contract: {allow: [\n",
])
def test_a_broken_contract_is_an_error_not_silence(tmp_path, text):
    (tmp_path / ".aria").mkdir()
    (tmp_path / ".aria" / "policy.yaml").write_text(text)
    with pytest.raises(ContractError):
        ChangeContract.load(tmp_path)


@pytest.mark.parametrize("tool, params, allowed, rule", [
    ("write_file", {"path": "src/auth/session.py"}, True, ""),
    ("edit_file", {"path": "tests/test_session.py"}, True, ""),
    ("edit_file", {"path": "src/billing/invoice.py"}, False, "allow"),
    ("write_file", {"path": "src/auth/secrets.py"}, False, "restrict"),
    ("write_file", {"path": "/etc/hosts"}, False, "outside-workspace"),
    ("read_file", {"path": "src/billing/invoice.py"}, True, ""),      # reading is never restricted
    ("run_command", {"command": "pytest -q"}, True, ""),
    ("run_command", {"command": "git push origin main"}, False, "forbid"),
    ("run_command", {"command": "rm -rf build"}, False, "max_level"),
    ("run_command", {"command": "sed -i s/a/b/ src/billing/x.py"}, False, "allow"),
])
def test_check(project, tool, params, allowed, rule):
    verdict = ChangeContract.load(project).check(tool, params)
    assert verdict.allowed is allowed
    assert verdict.rule == rule


def test_globs():
    contract = ChangeContract(root=".", allow=("src/", "**/*.md", ".github/**"))
    assert contract.check("write_file", {"path": "src/a/b.py"}).allowed
    assert contract.check("write_file", {"path": "docs/x/readme.md"}).allowed
    assert contract.check("write_file", {"path": ".github/workflows/ci.yml"}).allowed
    assert not contract.check("write_file", {"path": "lib/a.py"}).allowed


def test_render_reads_like_a_contract(project):
    text = ChangeContract.load(project).with_goal("Fix the auth refresh bug").render()
    assert text.startswith("CHANGE CONTRACT")
    for expected in ("Fix the auth refresh bug", "✓ modify src/auth/**", "× modify src/auth/secrets.py",
                     "× git.push", "above L3", "✓ existing tests pass"):
        assert expected in text


def test_fail_closed_allows_reading_only(tmp_path):
    contract = ChangeContract.fail_closed(tmp_path, "bad yaml")
    assert contract.check("read_file", {"path": "a"}).allowed
    assert contract.check("run_command", {"command": "pytest"}).allowed
    assert not contract.check("write_file", {"path": "a.py"}).allowed
    assert "could not be read: bad yaml" in contract.render()


def test_bridge_fails_closed_on_a_broken_policy(tmp_path):
    from aria_code.apps.cli.providers.runtime_bridge import build_change_contract

    assert build_change_contract({"workspace_root": str(tmp_path)}, "x") is None
    (tmp_path / ".aria").mkdir()
    (tmp_path / ".aria" / "policy.yaml").write_text("contract:\n  forbid: [nope]\n")
    contract = build_change_contract({"workspace_root": str(tmp_path)}, "fix it")
    assert contract.max_level == 0 and "nope" in contract.load_error
    assert contract.goal == "fix it"


def test_the_loop_refuses_a_breaking_call_and_runs_the_rest(project):
    ran = []
    prompts = []
    rounds = {"n": 0}

    async def provider_fn(message, history, **kwargs):
        prompts.append(message)
        rounds["n"] += 1
        if rounds["n"] == 1:
            return {"success": True, "response": "", "provider": "fake", "tool_calls_pending": [
                {"tool": "write_file", "params": {"path": "src/billing/x.py", "content": "x"}},
                {"tool": "write_file", "params": {"path": "src/auth/ok.py", "content": "y"}},
                {"tool": "read_file", "params": {"path": "src/billing/x.py"}},
            ]}
        return {"success": True, "response": "done", "provider": "fake"}

    def tool(name):
        return lambda params: ran.append((name, params["path"])) or {"success": True}

    executor = ToolExecutor({"write_file": (tool("write_file"), "w"), "read_file": (tool("read_file"), "r")})
    contract = ChangeContract.load(project).with_goal("fix auth")

    async def collect():
        return [e async for e in run_agent("fix auth", [], provider_fn=provider_fn, tool_executor=executor,
                                           options=AgentOptions(contract=contract))]

    events = asyncio.run(collect())

    # The executor makes paths absolute; compare their tails.
    ran = [(name, path.replace("\\", "/").split("/src/", 1)[-1]) for name, path in ran]
    assert ("write_file", "billing/x.py") not in ran
    assert ("write_file", "auth/ok.py") in ran and ("read_file", "billing/x.py") in ran
    assert prompts[0].startswith("[Change contract]") and "[User request]\nfix auth" in prompts[0]
    assert "Blocked by the change contract (allow)" in prompts[1]
    assert any(isinstance(e, AgentEventStatus) and e.state == "contract_blocked" for e in events)
    final = events[-1]
    assert isinstance(final, AgentEventComplete)
    assert final.result.contract["refused"][0]["rule"] == "allow"
    assert final.result.contract["goal"] == "fix auth"
