package main

// The review gate — a port of src/aria_code/runtime/review.py. Before a turn
// that changed files ends, a separate model call with a fresh context and no
// tools reads what an outside reviewer would: the goal, the change contract,
// the checks and the diff — not the builder's reasoning or transcript. It
// answers in JSON; blocking findings go back to the builder once, and the
// review lands in the delivery report. A reviewer that fails never blocks.
// tests/test_native_go_review.py compares parsing, prompt and report text
// with Python.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"regexp"
	"strings"
)

const reviewerSystem = "You are an independent code reviewer. You did not write the change in front " +
	"of you, and you cannot run or edit anything: you read and judge. Do not call " +
	"tools. Answer with one JSON object and nothing else."

const reviewInstructions = `Review the change below against the goal.

Report as BLOCKING only what makes the change wrong or unsafe for the goal:
incorrect behaviour, a missed requirement, a broken edge case the goal implies,
a security problem, data loss, or a breach of the change contract. Everything
else — naming, style, structure, extra tests you would like — is a SUGGESTION.
Do not report problems in code the change did not touch. If you are unsure
whether something is a bug, it is a suggestion.

Answer with exactly this JSON shape:
{"verdict": "pass" | "blocking",
 "summary": "<one sentence>",
 "findings": [{"severity": "blocking" | "suggestion",
               "file": "<path>", "line": <number or null>,
               "issue": "<what is wrong and why, one or two sentences>"}],
 "behaviour": {"before": "<what the code did before, one sentence>",
               "after": "<what it does now>",
               "why": "<why the change was needed, from the goal>",
               "impact": "<callers, modules or users affected>"}}
"verdict" is "blocking" exactly when a finding is blocking. "behaviour" describes
the change in terms of behaviour, not lines; leave a field empty if the diff does
not say.`

type reviewFinding struct {
	Severity string `json:"severity"`
	File     string `json:"file"`
	Line     *int64 `json:"line"`
	Issue    string `json:"issue"`
}

func (f reviewFinding) blocking() bool { return f.Severity == "blocking" }

func (f reviewFinding) where() string {
	if f.File == "" {
		return ""
	}
	if f.Line != nil {
		return fmt.Sprintf("%s:%d", f.File, *f.Line)
	}
	return f.File
}

type reviewReport struct {
	Verdict   string // "pass" | "blocking" | "error"
	Summary   string
	Findings  []reviewFinding
	Attempt   int
	Error     string
	Behaviour map[string]any
}

func (r reviewReport) split() (blocking, suggestions []reviewFinding) {
	for _, f := range r.Findings {
		if f.blocking() {
			blocking = append(blocking, f)
		} else {
			suggestions = append(suggestions, f)
		}
	}
	return
}

func plural(n int, word string) string {
	if n == 1 {
		return fmt.Sprintf("%d %s", n, word)
	}
	return fmt.Sprintf("%d %ss", n, word)
}

func (r reviewReport) headline() string {
	if r.Verdict == "error" {
		return "Review did not complete: " + r.Error
	}
	blocking, suggestions := r.split()
	if len(blocking) > 0 {
		return "Review: " + plural(len(blocking), "blocking finding")
	}
	tail := ""
	if len(suggestions) > 0 {
		tail = " · " + plural(len(suggestions), "suggestion")
	}
	return "Review: no blocking findings" + tail
}

// lines is the Review section of the delivery report.
func (r reviewReport) lines(limit int) []string {
	if r.Verdict == "error" {
		return []string{"⚠ did not complete: " + r.Error}
	}
	blocking, suggestions := r.split()
	mark := "✓ "
	if len(blocking) > 0 {
		mark = "✗ "
	}
	out := []string{mark + strings.TrimPrefix(r.headline(), "Review: ")}
	ordered := append(append([]reviewFinding{}, blocking...), suggestions...)
	for i, f := range ordered {
		if i == limit {
			break
		}
		sign, where := "·", ""
		if f.blocking() {
			sign = "✗"
		}
		if f.where() != "" {
			where = f.where() + " — "
		}
		out = append(out, fmt.Sprintf("  %s %s%s", sign, where, f.Issue))
	}
	if hidden := len(r.Findings) - limit; hidden > 0 {
		out = append(out, fmt.Sprintf("  … +%d more", hidden))
	}
	return out
}

func (r reviewReport) repairDirective() string {
	blocking, _ := r.split()
	var items []string
	for _, f := range blocking {
		where := ""
		if f.where() != "" {
			where = f.where() + ": "
		}
		items = append(items, "- "+where+f.Issue)
	}
	noun := "problems"
	if len(blocking) == 1 {
		noun = "problem"
	}
	return "[Independent review]\n" +
		"A reviewer who saw only the goal, the contract, the checks and your diff " +
		fmt.Sprintf("found %d blocking %s:\n", len(blocking), noun) +
		strings.Join(items, "\n") + "\n\n" +
		"Fix them, or — if a finding is wrong — say why in your final message. " +
		"The checks will run again after you change files."
}

// asDict is ReviewReport.as_dict, the shape the delivery report reads.
func (r reviewReport) asDict() map[string]any {
	findings := make([]reviewFinding, len(r.Findings))
	copy(findings, r.Findings)
	var behaviour any
	if len(r.Behaviour) > 0 {
		behaviour = r.Behaviour
	}
	lines := r.lines(5)
	linesAny := make([]any, len(lines))
	for i, l := range lines {
		linesAny[i] = l
	}
	return map[string]any{
		"verdict": r.Verdict, "summary": r.Summary, "findings": findings, "attempt": r.Attempt,
		"error": r.Error, "headline": r.headline(), "lines": linesAny, "behaviour": behaviour,
	}
}

var fencedJSON = regexp.MustCompile("(?s)```(?:json)?\\s*(\\{.*?\\})\\s*```")

// parseReview is review.parse_review: never fails; an unreadable answer is
// an "error" report, which never blocks.
func parseReview(text string, attempt int) reviewReport {
	raw := strings.TrimSpace(text)
	if raw == "" {
		return reviewReport{Verdict: "error", Attempt: attempt, Error: "the reviewer gave no answer"}
	}
	candidate := ""
	if m := fencedJSON.FindStringSubmatch(raw); m != nil {
		candidate = m[1]
	} else if start, end := strings.Index(raw, "{"), strings.LastIndex(raw, "}"); start >= 0 && end >= start {
		candidate = raw[start : end+1]
	}
	decoder := json.NewDecoder(bytes.NewReader([]byte(candidate)))
	decoder.UseNumber()
	var parsed any
	if !json.Valid([]byte(candidate)) || decoder.Decode(&parsed) != nil {
		return reviewReport{Verdict: "error", Attempt: attempt, Error: "the reviewer's answer was not JSON"}
	}
	data, ok := pyNumbers(parsed).(map[string]any)
	if !ok {
		return reviewReport{Verdict: "error", Attempt: attempt, Error: "the reviewer's answer was not a JSON object"}
	}
	collapse := func(value any) string {
		if value == nil {
			return ""
		}
		return strings.Join(strings.FieldsFunc(pyStr(value), pyIsSpace), " ")
	}
	var findings []reviewFinding
	for _, raw := range asSlice(data["findings"]) {
		item, ok := raw.(map[string]any)
		if !ok || !truthy(item["issue"]) || strings.TrimSpace(pyStr(item["issue"])) == "" {
			continue
		}
		severity := "suggestion"
		if s, _ := item["severity"].(string); strings.ToLower(s) == "blocking" {
			severity = "blocking"
		}
		finding := reviewFinding{Severity: severity, Issue: collapse(item["issue"])}
		if truthy(item["file"]) {
			finding.File = strings.TrimSpace(pyStr(item["file"]))
		}
		if line, ok := item["line"].(int); ok && line > 0 {
			n := int64(line)
			finding.Line = &n
		}
		findings = append(findings, finding)
	}
	// The verdict follows the findings: a "blocking" verdict with no blocking
	// finding gives the builder nothing to fix, and a "pass" over one would hide it.
	verdict := "pass"
	for _, f := range findings {
		if f.blocking() {
			verdict = "blocking"
		}
	}
	rawBehaviour := data["behaviour"]
	if !truthy(rawBehaviour) {
		rawBehaviour = data["behavior"]
	}
	var behaviour map[string]any
	if m, ok := rawBehaviour.(map[string]any); ok {
		for _, key := range []string{"before", "after", "why", "impact"} {
			value := ""
			if truthy(m[key]) {
				value = collapse(m[key])
			}
			if runes := []rune(value); len(runes) > 240 {
				value = string(runes[:240])
			}
			if value != "" {
				if behaviour == nil {
					behaviour = map[string]any{}
				}
				behaviour[key] = value
			}
		}
	}
	summary := ""
	if truthy(data["summary"]) {
		summary = strings.TrimSpace(pyStr(data["summary"]))
	}
	return reviewReport{Verdict: verdict, Summary: summary, Findings: findings, Attempt: attempt, Behaviour: behaviour}
}

// pyNumbers turns decoded json.Numbers into the int or float Python's json
// module makes of them, throughout a decoded value.
func pyNumbers(value any) any {
	switch v := value.(type) {
	case json.Number:
		if i, err := v.Int64(); err == nil && !strings.ContainsAny(v.String(), ".eE") {
			return int(i)
		}
		f, _ := v.Float64()
		return f
	case map[string]any:
		for key, item := range v {
			v[key] = pyNumbers(item)
		}
	case []any:
		for i, item := range v {
			v[i] = pyNumbers(item)
		}
	}
	return value
}

// buildReviewPrompt is review.build_review_prompt.
func buildReviewPrompt(goal, diff string, checks []map[string]any, contract string, maxDiffChars int) string {
	if runes := []rune(diff); len(runes) > maxDiffChars {
		omitted := len(runes) - maxDiffChars
		diff = string(runes[:maxDiffChars]) + fmt.Sprintf("\n… [%s characters of diff omitted]", thousands(omitted))
	}
	var checkLines []string
	for _, c := range checks {
		status := "FAIL"
		if truthy(c["passed"]) {
			status = "PASS"
		}
		command, _ := c["command"].(string)
		checkLines = append(checkLines, status+"  "+command)
	}
	checkText := strings.Join(checkLines, "\n")
	if checkText == "" {
		checkText = "(no checks ran)"
	}
	goal = strings.TrimSpace(goal)
	if goal == "" {
		goal = "(not stated)"
	}
	parts := []string{reviewInstructions, "", "GOAL", goal}
	if contract != "" {
		parts = append(parts, "", "CONTRACT", strings.TrimSpace(contract))
	}
	diff = strings.TrimSpace(diff)
	if diff == "" {
		diff = "(empty)"
	}
	parts = append(parts, "", "CHECKS", checkText, "", "DIFF", diff)
	return strings.Join(parts, "\n")
}

func thousands(n int) string {
	text := fmt.Sprint(n)
	for i := len(text) - 3; i > 0; i -= 3 {
		text = text[:i] + "," + text[i:]
	}
	return text
}

// reviewGate is review.ReviewGate: armed by a changed diff, reviewing each
// distinct diff once, at most maxAttempts+1 times per turn.
type reviewGate struct {
	maxAttempts  int
	maxDiffChars int
	reports      []reviewReport
	reviewedDiff string
}

func newReviewGate(cfg config) *reviewGate {
	if !cfg.boolean("review_gate", false) || cfg.text("permission_mode", "workspace-write") == "read-only" {
		return nil
	}
	attempts := 1
	if n, ok := pyInt(cfg["review_max_attempts"]); ok {
		attempts = max(0, n)
	}
	return &reviewGate{maxAttempts: attempts, maxDiffChars: 24_000}
}

func (g *reviewGate) shouldRun(changed bool, diff string) bool {
	if !changed || strings.TrimSpace(diff) == "" {
		return false
	}
	if len(g.reports) > 0 && diff == g.reviewedDiff {
		return false
	}
	return len(g.reports) <= g.maxAttempts
}

func (g *reviewGate) canRepair() bool { return len(g.reports) <= g.maxAttempts }

func (g *reviewGate) last() *reviewReport {
	if len(g.reports) == 0 {
		return nil
	}
	return &g.reports[len(g.reports)-1]
}

// record files the reviewer's answer (or the error calling it) as a report.
func (g *reviewGate) record(answer string, err error, diff string) reviewReport {
	report := reviewReport{Verdict: "error", Attempt: len(g.reports) + 1}
	if err != nil {
		report.Error = err.Error()
	} else {
		report = parseReview(answer, len(g.reports)+1)
	}
	g.reports = append(g.reports, report)
	g.reviewedDiff = diff
	return report
}

// reviewCommand answers `aria-runtime review`: {"answers": [...]} parsed into
// report dicts, and {"prompt": {goal, diff, checks, contract, max_diff_chars}}
// rendered as the reviewer's prompt — for comparison with Python.
func reviewCommand(stdin io.Reader, stdout, stderr io.Writer) int {
	var request struct {
		Answers []string `json:"answers"`
		Prompt  *struct {
			Goal         string           `json:"goal"`
			Diff         string           `json:"diff"`
			Checks       []map[string]any `json:"checks"`
			Contract     string           `json:"contract"`
			MaxDiffChars int              `json:"max_diff_chars"`
		} `json:"prompt"`
	}
	if err := json.NewDecoder(io.LimitReader(stdin, 4<<20)).Decode(&request); err != nil {
		fmt.Fprintln(stderr, "review: expected a JSON request:", err)
		return 2
	}
	out := map[string]any{}
	reports := []map[string]any{}
	for i, answer := range request.Answers {
		r := parseReview(answer, i+1)
		dict := r.asDict()
		dict["repair_directive"] = r.repairDirective()
		reports = append(reports, dict)
	}
	out["reports"] = reports
	if p := request.Prompt; p != nil {
		if p.MaxDiffChars == 0 {
			p.MaxDiffChars = 24_000
		}
		out["prompt"] = buildReviewPrompt(p.Goal, p.Diff, p.Checks, p.Contract, p.MaxDiffChars)
	}
	if err := json.NewEncoder(stdout).Encode(out); err != nil {
		return 2
	}
	return 0
}
