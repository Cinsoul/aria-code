"""The Go runtime's review gate must read reviewers like runtime/review.py."""
import json
import os
import subprocess

import pytest

from aria_code.runtime.review import build_review_prompt, parse_review


def binary():
    value = os.environ.get("ARIA_GO_RUNTIME_BINARY")
    if not value:
        pytest.skip("The native-runtime CI job builds this executable")
    return value


def go_review(request):
    result = subprocess.run([binary(), "review"], input=json.dumps(request), capture_output=True, text=True,
                            encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def finding(severity, issue, file="", line=None):
    return {"severity": severity, "issue": issue, "file": file, "line": line}


ANSWERS = [
    "",
    "   ",
    "Looks good to me!",
    "not json {",
    "[1, 2]",
    '"text"',
    "{} trailing }",
    '{"verdict": "pass", "summary": " Fine. ", "findings": []}',
    '{"verdict": "blocking", "summary": "nothing really", "findings": []}',
    json.dumps({"verdict": "pass", "findings": [finding("BLOCKING", "refresh() drops the token", "src/auth.py", 42)]}),
    json.dumps({"verdict": "blocking", "findings": [
        finding("blocking", "  expired   sessions\nnever refresh ", "src/session.py", 12),
        finding("suggestion", "rename x", "src/a.py"),
        finding("nit", "add a test", "", 3),
        finding("blocking", "", "src/b.py"),
        {"severity": "blocking"},
        "not a finding",
        finding("blocking", "line is text", "c.py", "7"),
        finding("blocking", "line is zero", "c.py", 0),
        finding("blocking", "line is float", "c.py", 3.0),
        finding("suggestion", 12345, None, -1),
        finding("blocking", "密钥被写入日志", "数据/日志.py", 8),
    ]}),
    json.dumps({"findings": [finding("suggestion", f"s{i}") for i in range(9)]}),
    json.dumps({"findings": [finding("blocking", f"b{i}", f"f{i}.py", i + 1) for i in range(7)]}),
    "Here is my review:\n```json\n" + json.dumps({"findings": [finding("blocking", "fenced")]}) + "\n```\nThanks.",
    "```\n" + json.dumps({"summary": "bare fence"}) + "\n```",
    "Preamble {\"summary\": \"embedded\", \"findings\": null} epilogue",
    json.dumps({"behaviour": {"before": "  failed\n", "after": "x" * 300, "why": "", "impact": None}}),
    json.dumps({"behavior": {"before": "american spelling", "after": 5}}),
    json.dumps({"behaviour": {}, "behavior": {"why": "fallback"}}),
    json.dumps({"behaviour": "not a mapping"}),
    json.dumps({"summary": 0, "findings": {"severity": "blocking"}}),
]


def test_go_review_parses_answers_like_python():
    actual = go_review({"answers": ANSWERS})["reports"]
    for index, (answer, got) in enumerate(zip(ANSWERS, actual)):
        report = parse_review(answer, attempt=index + 1)
        expected = json.loads(json.dumps(report.as_dict()))
        expected["repair_directive"] = report.repair_directive()
        assert got == expected, answer


@pytest.mark.parametrize("case", [
    dict(goal="Fix the refresh bug", diff="--- a/x\n+++ b/x\n+y\n", checks=[{"command": "pytest -q", "passed": True}],
         contract="CHANGE CONTRACT\n\nAllowed\n  ✓ modify src/**\n"),
    dict(goal="  ", diff="  ", checks=[]),
    dict(goal="修复", diff="界" * 30, checks=[{"command": "go test ./...", "passed": False}, {"passed": True}],
         max_diff_chars=10),
    dict(goal="g", diff="d" * 25_000, checks=[]),
])
def test_go_review_prompt_matches_python(case):
    expected = build_review_prompt(goal=case["goal"], diff=case["diff"], checks=case["checks"],
                                   contract=case.get("contract", ""), max_diff_chars=case.get("max_diff_chars", 24_000))
    assert go_review({"prompt": case})["prompt"] == expected
