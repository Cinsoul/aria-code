#!/usr/bin/env python3
"""Record a real Aria Code session for the README and the intro video.

Nothing here is drawn or scripted output. The real `aria-code` CLI runs in a
pseudo-terminal; its input is typed at human speed; every byte it prints goes
into an asciinema v2 .cast file with real timestamps. Approval menus are
answered the way a person would — after a pause long enough to read them —
by accepting the default ("Yes").

    python scripts/record_demo.py coding    --cast /tmp/coding.cast
    python scripts/record_demo.py finance   --cast /tmp/finance.cast
    python scripts/record_demo.py logistics --cast /tmp/logistics.cast
    python scripts/render_demo.py --cast /tmp/coding.cast --gif docs/assets/demo-coding.gif

Scenarios:
- coding: a natural-language task — write fx.py and its tests, run them —
  then /review of the result. This calls your configured model; for Gemini on
  Vertex AI set GOOGLE_CLOUD_PROJECT and be logged in to gcloud.
- finance: /ta and /backtest on real market data (needs network, no model).
- logistics: /inventory and /carriers on the eval fixtures (no network, no
  model), including the refusal to mix two shippers' data.

The session runs in a throwaway HOME with a pinned light palette, so the
recording does not depend on the recording machine's appearance or config.
"""

from __future__ import annotations

import argparse
import codecs
import csv
import fcntl
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"
COLS, ROWS = 104, 40
IDLE_PROMPT = "Ask Aria"            # the empty input box: the CLI is waiting for input
APPROVAL_MENU = "Esc/q Cancel"      # an approval picker is open
READ_PAUSE = 1.6                    # seconds a viewer gets to read a menu before it is answered


def _prepare_logistics(work: Path) -> None:
    shutil.copy(FIXTURES / "inventory_reorder" / "skus.csv", work / "skus.csv")
    shutil.copy(FIXTURES / "freight_audit" / "waybills.csv", work / "waybills.csv")
    rows = list(csv.DictReader((work / "skus.csv").open()))
    beta = [{**r, "owner_id": "BETA", "sku": "B" + r["sku"][1:]} for r in rows]
    with (work / "all_skus.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows + beta)


def _prepare_coding(work: Path) -> None:
    # A repository with one commit, so /review has something to compare to.
    (work / "README.md").write_text("# fx-tools\n\nSmall currency helpers.\n")
    for args in (["init", "-q", "-b", "main"], ["add", "."],
                 ["-c", "user.name=demo", "-c", "user.email=demo@example.com", "commit", "-q", "-m", "start"]):
        subprocess.run(["git", *args], cwd=work, check=True, capture_output=True)


@dataclass
class Scenario:
    workspace: str
    steps: tuple[str, ...]
    prepare: Callable[[Path], None] | None = None
    uses_model: bool = False
    step_timeout: float = 60
    env: dict = field(default_factory=dict)


SCENARIOS = {
    "logistics": Scenario(
        workspace="acme-3pl", prepare=_prepare_logistics, env={"ARIA_OFFLINE": "1"},
        steps=("/inventory skus.csv", "/inventory all_skus.csv",
               "/inventory all_skus.csv --owner BETA", "/carriers waybills.csv"),
    ),
    "finance": Scenario(
        workspace="research", step_timeout=120,
        steps=("/ta AAPL", "/backtest momentum SPY --period 1y"),
    ),
    "coding": Scenario(
        workspace="fx-tools", prepare=_prepare_coding, uses_model=True, step_timeout=420,
        steps=("Create fx.py with convert(amount, rate) that uses Decimal and rounds half-up to cents, "
               "plus test_fx.py with three unittest cases, then run python3 -m unittest -v",
               "/review"),
    ),
}


def record(scenario: Scenario, cast: Path, cli: str) -> None:
    # Resolved, so the CLI sees its cwd under HOME and shows "~/<workspace>".
    home = Path(tempfile.mkdtemp(prefix="aria-demo-home-")).resolve()
    try:
        work = home / scenario.workspace
        work.mkdir()
        if scenario.prepare:
            scenario.prepare(work)
        # A light terminal, pinned: left alone, the CLI follows the recording
        # machine's appearance and a re-record could come out in another palette.
        env = {**os.environ, "HOME": str(home), "TERM": "xterm-256color", "COLORTERM": "truecolor",
               "COLORFGBG": "0;15", "ARIA_THEME": "light",
               "COLUMNS": str(COLS), "LINES": str(ROWS), **scenario.env}
        if scenario.uses_model:
            # The throwaway HOME must not hide the user's gcloud login.
            env.setdefault("CLOUDSDK_CONFIG", str(Path(os.path.expanduser("~")) / ".config" / "gcloud"))
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(work)
            os.execve(cli, [cli], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))

        import pyte  # only to know what is on screen while recording

        screen = pyte.Screen(COLS, ROWS)
        stream = pyte.Stream(screen)
        start = time.time()
        events: list[list] = []
        # Incremental: a read can end inside a multi-byte character (a box
        # corner, "→"), and decoding each read alone turns it into "���".
        decoder = codecs.getincrementaldecoder("utf-8")("replace")

        def mark(label: str) -> None:
            events.append([round(time.time() - start, 4), "m", label])

        def pump(seconds: float) -> None:
            until = time.time() + seconds
            while time.time() < until:
                ready, _, _ = select.select([fd], [], [], 0.05)
                if not ready:
                    continue
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    return
                text = decoder.decode(chunk)
                if text:
                    events.append([round(time.time() - start, 4), "o", text])
                    stream.feed(text)

        def visible() -> str:
            return "\n".join(screen.display)

        def wait_for(predicate, timeout: float) -> bool:
            until = time.time() + timeout
            while time.time() < until:
                pump(0.2)
                if predicate():
                    return True
            return False

        if not wait_for(lambda: IDLE_PROMPT in visible(), 30):
            raise RuntimeError("the CLI did not reach its prompt")
        pump(1.2)
        for step in scenario.steps:
            mark(f"start {step}")
            for ch in step:
                os.write(fd, ch.encode())
                pump(0.035 if len(step) > 40 else 0.06)
            pump(0.4)
            mark(f"enter {step}")
            before = visible()
            os.write(fd, b"\r")
            # A fast command can print and return to the prompt between two
            # polls, so wait for the screen to change, not for a busy state.
            wait_for(lambda: visible() != before, 10)
            deadline = time.time() + scenario.step_timeout
            while time.time() < deadline:
                if wait_for(lambda: IDLE_PROMPT in visible() or APPROVAL_MENU in visible(),
                            deadline - time.time()) and APPROVAL_MENU in visible():
                    pump(READ_PAUSE)
                    mark("approve")
                    os.write(fd, b"\r")
                    wait_for(lambda: APPROVAL_MENU not in visible(), 10)
                    continue
                break
            else:
                raise RuntimeError(f"{step!r} did not finish within {scenario.step_timeout:.0f}s")
            if IDLE_PROMPT not in visible():
                raise RuntimeError(f"{step!r} did not finish within {scenario.step_timeout:.0f}s")
            pump(1.0)
            mark(f"end {step}")
            pump(1.2)
        os.kill(pid, 9)

        with cast.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps({"version": 2, "width": COLS, "height": ROWS,
                                     "timestamp": int(start), "env": {"TERM": "xterm-256color"}}) + "\n")
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--cast", type=Path, required=True)
    parser.add_argument("--cli", default=shutil.which("aria-code") or str(Path(sys.prefix) / "bin" / "aria-code"))
    args = parser.parse_args()
    record(SCENARIOS[args.scenario], args.cast, args.cli)
    print(args.cast)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
