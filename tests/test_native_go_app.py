"""Exercise the actual Go app executable and its Rust containment barrier."""
import json
import os
import queue
import subprocess
import threading
import time

import pytest


def binary():
    value = os.environ.get("ARIA_GO_RUNTIME_BINARY")
    if not value:
        pytest.skip("The native-runtime CI job builds this executable")
    return value


def test_native_app_does_not_touch_state_before_the_host_barrier(tmp_path):
    program = binary()
    state = tmp_path / "state"
    project = tmp_path / "project"
    state.mkdir()
    project.mkdir()
    cfg = state / "config.json"
    original = json.dumps(dict(local_provider="google", model="gemini-3.5-flash"))
    cfg.write_text(original, encoding="utf-8")
    env = dict(os.environ, ARIA_HOME=str(state))
    process = subprocess.Popen([program, "app"], cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    events = queue.Queue()
    def read():
        for line in process.stdout:
            events.put(json.loads(line))
    threading.Thread(target=read, daemon=True).start()
    try:
        time.sleep(0.2)
        assert not (state / "sessions").exists()
        assert cfg.read_text(encoding="utf-8") == original
        assert events.empty()
        process.stdin.write("\n")
        process.stdin.flush()
        assert events.get(timeout=5)["type"] == "session.ready"
        process.stdin.write(json.dumps(dict(protocol=1, type="shutdown")) + "\n")
        process.stdin.flush()
        assert events.get(timeout=5)["type"] == "session.closed"
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_unsupported_native_provider_preserves_existing_user_state(tmp_path):
    cfg = tmp_path / "config.json"
    original = json.dumps(dict(local_provider="ollama", last_session_id="previous"))
    cfg.write_text(original, encoding="utf-8")
    process = subprocess.run([binary(), "app"], input="\n", env=dict(os.environ, ARIA_HOME=str(tmp_path)), capture_output=True, text=True, timeout=5)
    assert process.returncode != 0
    assert cfg.read_text(encoding="utf-8") == original
    assert not (tmp_path / "sessions").exists()
    events = [json.loads(line) for line in process.stdout.splitlines()]
    assert [event["type"] for event in events] == ["session.failed", "session.closed"]
