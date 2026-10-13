package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"google.golang.org/genai"
)

// reviewedTurn runs one coding turn whose reviewer answers with the given
// replies in order, and returns the answer, the evidence and what happened.
func reviewedTurn(t *testing.T, cfg config, replies []string, reviewerErr error) (string, *turnEvidence, []string, []string) {
	t.Helper()
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "app.py"), []byte("token = None\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	scope, err := newScope(root, nil, nil, false)
	if err != nil {
		t.Fatal(err)
	}
	var reviewPrompts, builderMessages []string
	edits := 0
	provider := providerFunc(func(ctx context.Context, contents []*genai.Content, system string, tools []*genai.Tool, emit func(string)) (*genai.Content, error) {
		if system == reviewerSystem {
			if tools != nil || len(contents) != 1 {
				t.Fatal("the reviewer gets a fresh context and no tools")
			}
			reviewPrompts = append(reviewPrompts, contents[0].Parts[0].Text)
			if reviewerErr != nil {
				return nil, reviewerErr
			}
			reply := replies[0]
			replies = replies[1:]
			return genai.NewContentFromText(reply, genai.RoleModel), nil
		}
		last := contents[len(contents)-1]
		if last.Parts[0].Text != "" {
			builderMessages = append(builderMessages, last.Parts[0].Text)
		}
		if last.Parts[0].FunctionResponse == nil {
			edits++
			return &genai.Content{Role: "model", Parts: []*genai.Part{call("write_file", map[string]any{"path": "app.py", "content": strings.Repeat("token = refresh()\n", edits)})}}, nil
		}
		text := "Done."
		if edits > 1 {
			text = "Fixed after review."
		}
		emit(text)
		return genai.NewContentFromText(text, genai.RoleModel), nil
	})
	hooks := quietHooks()
	hooks.evidence = newTurnEvidence(root)
	var statuses []string
	hooks.emit = func(kind string, fields map[string]any) {
		if kind == "turn.status" {
			statuses = append(statuses, fields["state"].(string)+": "+fields["message"].(string))
		}
	}
	_, answer, err := nativeTurn(context.Background(), provider, scope, cfg, nil, "Make the token refresh", hooks)
	if err != nil {
		t.Fatal(err)
	}
	return answer, hooks.evidence, append(reviewPrompts, builderMessages...), statuses
}

func TestBlockingReviewGoesBackToTheBuilderOnce(t *testing.T) {
	blocking := `{"verdict":"blocking","findings":[{"severity":"blocking","file":"app.py","line":1,"issue":"refresh() is never imported"}],
		"behaviour":{"before":"no token","after":"token refreshed","why":"the goal"}}`
	answer, evidence, messages, statuses := reviewedTurn(t, config{"review_gate": true, "acceptance_gate": false}, []string{blocking, `{"verdict":"pass","findings":[]}`}, nil)
	if answer != "Fixed after review." {
		t.Fatalf("the answer must be the repaired turn's, not %q", answer)
	}
	if len(evidence.gate.reports) != 2 {
		t.Fatal("the repaired diff is reviewed again", evidence.gate.reports)
	}
	if !strings.Contains(messages[0], "GOAL\nMake the token refresh") || !strings.Contains(messages[0], "+token = refresh()") {
		t.Fatal("the reviewer reads the goal and the diff:", messages[0])
	}
	directive := ""
	for _, m := range messages {
		if strings.HasPrefix(m, "[Independent review]") {
			directive = m
		}
	}
	if !strings.Contains(directive, "- app.py:1: refresh() is never imported") {
		t.Fatal("the builder gets the blocking findings:", messages)
	}
	if strings.Join(statuses, "|") != "review_started: Independent review of the change|review_blocking: Review: 1 blocking finding|review_started: Independent review of the change|review_passed: Review: no blocking findings" {
		t.Fatal(statuses)
	}
	report := evidence.report("completed").Render("", "")
	if !strings.Contains(report, "Review\n  ✓ no blocking findings") || !strings.HasPrefix(report, "DONE") {
		t.Fatal(report)
	}
}

func TestUnresolvedBlockingReviewLeavesTheTurnIncomplete(t *testing.T) {
	blocking := `{"findings":[{"severity":"blocking","issue":"still wrong"}]}`
	_, evidence, _, _ := reviewedTurn(t, config{"review_gate": true, "review_max_attempts": 0.0, "acceptance_gate": false}, []string{blocking}, nil)
	report := evidence.report("completed")
	text := report.Render("", "")
	if report.Status != "incomplete" || !strings.Contains(text, "Address the review's blocking findings") || !strings.Contains(text, "✗ still wrong") {
		t.Fatal(text)
	}
}

func TestAFailedReviewerNeverBlocks(t *testing.T) {
	answer, evidence, _, statuses := reviewedTurn(t, config{"review_gate": true, "acceptance_gate": false}, nil, errors.New("quota exceeded"))
	if answer != "Done." || evidence.report("completed").Status != "done" {
		t.Fatal(answer)
	}
	if !strings.Contains(statuses[len(statuses)-1], "review_error: Review did not complete: quota exceeded") {
		t.Fatal(statuses)
	}
}

func TestNoReviewUnlessTheGateIsOn(t *testing.T) {
	for _, cfg := range []config{{}, {"review_gate": true, "permission_mode": "read-only"}} {
		if newReviewGate(cfg) != nil {
			t.Fatal(cfg)
		}
	}
	answer, evidence, messages, _ := reviewedTurn(t, config{"acceptance_gate": false}, nil, nil)
	if answer != "Done." || evidence.gate != nil || strings.Contains(strings.Join(messages, ""), "GOAL") {
		t.Fatal("review_gate is off by default")
	}
}
