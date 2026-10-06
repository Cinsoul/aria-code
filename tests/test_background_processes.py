"""A long-running command can be started, read, written to and stopped.

run_command waited for every command to finish, so a dev server blocked the
turn until the timeout and there was no way to start one and test against it.
"""

from __future__ import annotations

import shlex
import sys
import time

import pytest

from aria_code.runtime import processes

PY = shlex.quote(sys.executable)


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIA_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    yield
    processes.stop_all()
    processes._processes.clear()


def start(command, cwd, **extra):
    from aria_code.apps.cli.tools.system_tools import tool_run_command

    return tool_run_command({"command": command, "background": True, "policy": "balanced",
                             "cwd": str(cwd), "permission_mode": "workspace-write",
                             "network_enabled": False, **extra}, has_rich=False)


SERVER = (f"{PY} -u -c \"import time; print('booting'); time.sleep(0.5); print('Listening on 8000');"
          " [print('tick', i) or time.sleep(0.2) for i in range(200)]\"")


def test_start_returns_at_once_and_waits_for_the_ready_line(tmp_path):
    began = time.monotonic()
    result = start(SERVER, tmp_path, until="Listening on", wait_seconds=10)
    data = result["data"]
    assert result["success"] and data["background"] and data["running"]
    assert data["matched"] and "Listening on 8000" in data["output"]
    assert time.monotonic() - began < 5


def test_output_is_what_came_since_the_last_read(tmp_path):
    pid = start(SERVER, tmp_path, until="Listening on", wait_seconds=10)["data"]["process_id"]
    first = processes.tool_process({"action": "output", "process_id": pid, "wait_seconds": 2})["data"]
    second = processes.tool_process({"action": "output", "process_id": pid, "wait_seconds": 2})["data"]
    assert "tick" in first["output"] and "tick" in second["output"]
    assert "Listening on" not in first["output"] + second["output"]


def test_input_reaches_the_program(tmp_path):
    echo = f"{PY} -u -c \"import sys; [print('got', line.strip()) for line in sys.stdin]\""
    pid = start(echo, tmp_path, wait_seconds=0.5)["data"]["process_id"]
    reply = processes.tool_process({"action": "input", "process_id": pid, "text": "hello\n",
                                    "wait_seconds": 3})["data"]
    assert "got hello" in reply["output"]


def test_stop_ends_the_process_and_its_children(tmp_path):
    parent = f"{PY} -u -c \"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); print('up'); time.sleep(60)\""
    pid = start(parent, tmp_path, until="up", wait_seconds=10)["data"]["process_id"]
    proc = processes._processes[pid]
    stopped = processes.tool_process({"action": "stop", "process_id": pid})["data"]
    assert stopped["stopped"] and not stopped["running"]
    import os
    with pytest.raises(ProcessLookupError):
        os.killpg(proc.popen.pid, 0)


def test_a_command_that_ends_reports_its_exit_code(tmp_path):
    data = start(f"{PY} -c \"print('done')\"", tmp_path, wait_seconds=5)["data"]
    assert data["running"] is False and data["exit_code"] == 0 and "done" in data["output"]


def test_list_and_unknown_ids(tmp_path):
    pid = start(SERVER, tmp_path, wait_seconds=0.2)["data"]["process_id"]
    rows = processes.tool_process({"action": "list"})["data"]["processes"]
    assert [r["process_id"] for r in rows] == [pid]
    missing = processes.tool_process({"action": "output", "process_id": "p999"})
    assert not missing["success"] and pid in missing["error"]


def test_too_many_running_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(processes, "MAX_RUNNING", 1)
    start(SERVER, tmp_path, wait_seconds=0.1)
    second = start(SERVER, tmp_path, wait_seconds=0.1)
    assert not second["success"] and "already running" in second["error"]


def test_the_policy_still_applies(tmp_path):
    blocked = start("curl https://example.com", tmp_path)
    assert not blocked["success"]


@pytest.mark.skipif(not __import__("aria_code.safety.sandbox", fromlist=["available"]).available(),
                    reason="needs macOS sandbox-exec")
def test_background_commands_run_in_the_sandbox(tmp_path):
    from pathlib import Path

    target = Path.home() / ".aria-bg-sandbox-test.txt"
    data = start(f"echo hi > {target}", tmp_path, wait_seconds=5)["data"]
    assert not target.exists()
    assert data["exit_code"] != 0 and "sandbox" in data.get("hint", "")


def test_the_model_is_offered_the_tool_and_the_flag():
    from aria_code import aria_cli

    names = {s["function"]["name"]: s["function"] for s in aria_cli.LOCAL_TOOL_SCHEMAS if "function" in s}
    assert "process" in names and "process" in aria_cli.LOCAL_TOOLS
    assert "background" in names["run_command"]["parameters"]["properties"]
