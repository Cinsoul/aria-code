"""What a new user sees before anything is set up, and how answers are laid out.

A fresh install defaults to Gemini on Google Cloud. With no Google setup the
banner said "Cloud model configured", the first question failed with
"Error: vertex_needs_project: set …" wrapped back to column 0, a snapshot ran
"Takeaway" and "Watch" together into one paragraph ("Watch: Watch USD …"),
and /ta mixed "Signal:4.5761" with "322.9569" and "data:ok stale:no".
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from aria_code.runtime.agent_loop import AgentErrorPresentation


def _console(width=60):
    return Console(file=io.StringIO(), width=width, color_system=None, highlight=False)


@pytest.mark.parametrize("error, first", [
    ("vertex_needs_project: set GOOGLE_CLOUD_PROJECT, /config set gcp_project=<id>, or `gcloud config set project <id>`",
     "Gemini runs on Google Cloud, and no project is set."),
    ("vertex_not_logged_in: run `gcloud auth login`", "Gemini runs on Google Cloud, and gcloud is not signed in."),
    ("vertex_gcloud_failed: TimeoutExpired", "gcloud could not issue an access token (TimeoutExpired)."),
])
def test_google_cloud_failures_are_explained(error, first):
    shown = AgentErrorPresentation.from_error(error, lang="en")
    assert shown.lines[0] == first and not shown.use_generic_error_prefix
    assert "vertex_" not in " ".join(shown.lines)
    assert "vertex_" not in " ".join(AgentErrorPresentation.from_error(error, lang="zh").lines)


def test_a_long_message_wraps_under_itself_and_keeps_its_brackets():
    from aria_code.ui.render.output import print_hanging

    console = _console(40)
    print_hanging(console, "  └ ", "Usage: /init [--force] generates ARIA.md for the current project")
    lines = console.file.getvalue().splitlines()
    assert lines[0].startswith("  └ Usage: /init [--force]")
    assert len(lines) > 1 and all(line.startswith("    ") for line in lines[1:])


@pytest.fixture
def no_google(monkeypatch, tmp_path):
    import aria_code.providers.llm.registry as registry

    monkeypatch.setattr(registry, "_load_provider_cfg_from_file", lambda _provider: {})
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "K_SERVICE",
                 "GCE_METADATA_HOST", "GOOGLE_CLOUD_PROJECT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gcloud" if name == "gcloud" else None)
    return tmp_path


def test_readiness_names_what_is_missing(no_google, monkeypatch):
    from aria_code.apps.cli.providers.base import google_readiness

    folder = no_google
    assert google_readiness({}) == "no Google Cloud project"
    (folder / "configurations").mkdir()
    (folder / "active_config").write_text("work")
    (folder / "configurations" / "config_work").write_text("[core]\nproject = demo-123\n")
    assert google_readiness({}) == "gcloud not signed in"
    (folder / "credentials.db").write_text("")
    assert google_readiness({}) == ""
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert google_readiness({}) == "no Google credentials"
    assert google_readiness({"gemini_key": "k"}) == ""


def test_snapshot_lines_stay_on_their_own_lines():
    from aria_code.ui.console import make_markdown

    console = _console(90)
    console.print(make_markdown("**Takeaway**: AAPL is bullish.  \n**Levels**: Watch USD 334.30 for a break."))
    lines = [line.strip() for line in console.file.getvalue().splitlines() if line.strip()]
    assert lines == ["Takeaway: AAPL is bullish.", "Levels: Watch USD 334.30 for a break."]


def test_ta_reads_as_one_style():
    from aria_code.ui.render.market import print_ta_result

    result = SimpleNamespace(
        data={"price": 333.63, "rsi": 52.82, "macd": 3.5509, "macd_signal": 4.5761, "macd_hist": -1.0252,
              "bb_upper": 346.2, "bb_mid": 332.58, "bb_lower": 318.95, "bb_position": 0.54,
              "ma5": 332.012, "ma60": 322.9569, "ma120": 307.8},
        provider_chain=["yfinance"], quality={"status": "ok"}, stale=False, missing_fields=[])
    fmt = lambda value, digits=2: "-" if value is None else f"{float(value):.{digits}f}"
    console = _console(120)
    print_ta_result(console=console, has_rich=True, symbol="AAPL", days=120, service_result=result,
                    formatter=fmt, lang="en")
    text = console.file.getvalue()
    assert "MA5 332.01 · MA60 322.96 · MA120 307.80" in text
    assert "signal 4.5761" in text and "hist -1.0252" in text and "Signal:" not in text
    assert "stale:" not in text and "source yfinance" in text
    stale = SimpleNamespace(**{**vars(result), "stale": True, "missing_fields": ["bb_upper"]})
    console = _console(120)
    print_ta_result(console=console, has_rich=True, symbol="AAPL", days=120, service_result=stale,
                    formatter=fmt, lang="en")
    assert "⚠ data: may be stale · missing bb_upper" in console.file.getvalue()
