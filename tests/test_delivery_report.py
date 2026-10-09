"""The delivery report: how a coding turn ends, written from what happened."""

import asyncio

from aria_code.runtime import AgentEventComplete, AgentOptions, ToolExecutor, run_agent
from aria_code.runtime.delivery import DeliveryReport, report_from_activities

EDIT = {
    "success": True,
    "data": {
        "path": "/w/src/session.py", "applied": True, "checkpoint_id": "cp1",
        "diff": "--- a/src/session.py\n+++ b/src/session.py\n@@\n-old\n+new\n+more\n",
    },
}
CREATE = {
    "success": True,
    "data": {
        "path": "/w/src/refresh.py", "applied": True, "action": "created", "checkpoint_id": "cp2",
        "diff": "--- /dev/null\n+++ b/src/refresh.py\n@@\n+a\n+b\n+c\n",
    },
}
GREEN = {"verified": True, "reports": [{"checks": [{"command": "pytest -q", "passed": True, "exit_code": 0}]}]}
RED = {"verified": False, "reports": [{"checks": [{"command": "pytest -q", "passed": False, "exit_code": 1}]}]}


def _report(activities, **kwargs):
    return report_from_activities(activities, root="/w", **kwargs)


def test_changed_files_with_line_counts_and_checkpoints():
    report = _report([
        ("edit_file", {"path": "src/session.py"}, EDIT),
        ("write_file", {"path": "src/refresh.py"}, CREATE),
        ("read_file", {"path": "src/x.py"}, {"success": True, "data": {"content": "x"}}),
    ], acceptance=GREEN)
    by_path = {item.path: item for item in report.changed}
    assert (by_path["/w/src/session.py"].added, by_path["/w/src/session.py"].removed) == (2, 1)
    assert by_path["/w/src/refresh.py"].created and by_path["/w/src/refresh.py"].added == 3
    assert report.checkpoints == ("cp1", "cp2")
    assert report.status == "done" and report.next == "Ready to commit"
    assert report.risk_level == 1


def test_red_checks_make_the_turn_incomplete_whatever_the_model_said():
    report = _report([("edit_file", {"path": "src/session.py"}, EDIT)], acceptance=RED)
    assert report.status == "incomplete"
    assert report.next == "Fix the failing checks"


def test_a_turn_that_stopped_early_is_incomplete():
    report = _report([("edit_file", {}, EDIT)], acceptance=GREEN, stop_reason="max_rounds")
    assert report.status == "incomplete" and "rounds" in report.next


def test_unverified_changes_say_so():
    report = _report([("edit_file", {}, EDIT)])
    assert report.status == "done" and report.next == "Review the changes — no check ran"
    assert "— no check ran (none could be inferred)" in report.render()


def test_nothing_happened_means_no_report():
    report = _report([("read_file", {"path": "a"}, {"success": True})])
    assert not report.worth_showing


def test_refused_calls_are_reported_and_not_counted_as_changes():
    refused = {"success": False, "error": "x", "contract_violation": {"tool": "write_file", "rule": "allow"}}
    contract = {"refused": [{"tool": "write_file", "reason": "src/billing/x.py is outside the allowed paths"}]}
    report = _report([("write_file", {"path": "src/billing/x.py"}, refused)], contract=contract)
    assert report.worth_showing and not report.changed
    assert "× write_file: src/billing/x.py is outside the allowed paths" in report.render()


def test_render_round_trips_through_a_dict():
    report = _report([("edit_file", {}, EDIT), ("write_file", {}, CREATE)], acceptance=GREEN)
    text = DeliveryReport.from_dict(report.as_dict()).render(rewind_hint="/rewind code run1", root="/w")
    assert text.splitlines()[0] == "DONE"
    for expected in ("M src/session.py", "+2 -1", "A src/refresh.py", "+3", "2 files · +5 / -1",
                     "✓ pytest -q", "Not reviewed", "L1 low", "2 checkpoints · /rewind code run1",
                     "Ready to commit"):
        assert expected in text, expected


def test_run_agent_attaches_the_report():
    rounds = {"n": 0}

    async def provider_fn(message, history, **kwargs):
        rounds["n"] += 1
        if rounds["n"] == 1:
            return {"success": True, "response": "", "provider": "fake",
                    "tool_calls_pending": [{"tool": "edit_file", "params": {"path": "src/session.py"}}]}
        return {"success": True, "response": "I have successfully fixed everything!", "provider": "fake"}

    executor = ToolExecutor({"edit_file": (lambda params: EDIT, "edit")})

    async def collect():
        return [e async for e in run_agent("fix", [], provider_fn=provider_fn, tool_executor=executor,
                                           options=AgentOptions())]

    final = asyncio.run(collect())[-1]
    assert isinstance(final, AgentEventComplete)
    delivery = final.result.delivery
    assert delivery["status"] == "done" and delivery["changed"][0]["added"] == 2
    assert delivery["next"] == "Review the changes — no check ran"


def test_a_read_only_turn_has_no_report():
    async def provider_fn(message, history, **kwargs):
        return {"success": True, "response": "It does X.", "provider": "fake"}

    async def collect():
        return [e async for e in run_agent("what does x do", [], provider_fn=provider_fn,
                                           tool_executor=ToolExecutor({}), options=AgentOptions())]

    assert asyncio.run(collect())[-1].result.delivery is None


def test_terminal_colours():
    from aria_code.ui.render.output import format_delivery_report

    report = _report([("edit_file", {}, EDIT)], acceptance=RED)
    lines = dict((line.strip(), style) for style, line in format_delivery_report(report.as_dict(), run_id="r"))
    assert lines["INCOMPLETE"] == "bold yellow"
    assert lines["✗ pytest -q  (exit 1)"] == "red"
    assert lines["Verified"] == "dim"
