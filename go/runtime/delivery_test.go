package main

import (
	"context"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"google.golang.org/genai"
)

// applyUnified rebuilds the new text from the old text and lineDiff's hunk.
func applyUnified(t *testing.T, before, diff string) string {
	t.Helper()
	old := strings.Split(strings.TrimSuffix(before, "\n"), "\n")
	if before == "" {
		old = nil
	}
	lines := strings.Split(strings.TrimSuffix(diff, "\n"), "\n")
	var start, count int
	if _, err := fmt.Sscanf(lines[2], "@@ -%d,%d", &start, &count); err != nil {
		t.Fatal(lines[2], err)
	}
	if start > 0 {
		start--
	}
	var out []string
	out = append(out, old[:start]...)
	position := start
	for _, line := range lines[3:] {
		switch line[0] {
		case ' ':
			out = append(out, line[1:])
			position++
		case '-':
			position++
		case '+':
			out = append(out, line[1:])
		}
	}
	out = append(out, old[position:]...)
	if len(out) == 0 {
		return ""
	}
	return strings.Join(out, "\n") + "\n"
}

func TestLineDiffCountsAndReconstructs(t *testing.T) {
	diff := lineDiff("src/a.py", []byte("a\nb\nc\n"), []byte("a\nB\nc\nd\n"), true)
	if added, removed, created := diffStats(diff); added != 2 || removed != 1 || created {
		t.Fatal(diff)
	}
	if lineDiff("a", []byte("same\n"), []byte("same\n"), true) != "" {
		t.Fatal("no change, no diff")
	}
	if _, _, created := diffStats(lineDiff("n.py", nil, []byte("x\n"), false)); !created {
		t.Fatal("a new file is created")
	}
	random := rand.New(rand.NewSource(7))
	words := []string{"a", "b", "c", "d", ""}
	text := func() string {
		var lines []string
		for range random.Intn(12) {
			lines = append(lines, words[random.Intn(len(words))])
		}
		if len(lines) == 0 {
			return ""
		}
		return strings.Join(lines, "\n") + "\n"
	}
	for range 500 {
		before, after := text(), text()
		diff := lineDiff("f", []byte(before), []byte(after), true)
		if diff == "" {
			if before != after {
				t.Fatalf("missed a change: %q → %q", before, after)
			}
			continue
		}
		if got := applyUnified(t, before, diff); got != after {
			t.Fatalf("%q → %q\n%s\nrebuilt %q", before, after, diff, got)
		}
	}
}

func TestChecksAfterTheLastChangeDecideVerification(t *testing.T) {
	var c checkLedger
	if c.acceptance() != nil {
		t.Fatal("no checks, no acceptance")
	}
	c.ran("pytest -q", 1)
	c.changed()
	if c.acceptance()["verified"] != nil {
		t.Fatal("a change after the check makes it stale")
	}
	c.ran("pytest -q", 0)
	c.ran("ruff check .", 0)
	c.ran("pytest -q", 0)
	acceptance := c.acceptance()
	if acceptance["verified"] != true || len(acceptance["reports"].([]any)[0].(map[string]any)["checks"].([]any)) != 2 {
		t.Fatal(acceptance)
	}
}

func TestNativeTurnEndsWithADeliveryReport(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("the verification command uses a POSIX shell")
	}
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "app.py"), []byte("a\nb\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	scope, err := newScope(root, nil, nil, false)
	if err != nil {
		t.Fatal(err)
	}
	step := 0
	provider := providerFunc(func(ctx context.Context, contents []*genai.Content, system string, tools []*genai.Tool, emit func(string)) (*genai.Content, error) {
		step++
		switch step {
		case 1:
			return &genai.Content{Role: "model", Parts: []*genai.Part{
				call("edit_file", map[string]any{"path": "app.py", "old_string": "b", "new_string": "B\nc"}),
				call("write_file", map[string]any{"path": "new.py", "content": "x\n"}),
			}}, nil
		case 2:
			return &genai.Content{Role: "model", Parts: []*genai.Part{call("run_command", map[string]any{"command": "pytest -q || true"})}}, nil
		default:
			emit("Done.")
			return genai.NewContentFromText("Done.", genai.RoleModel), nil
		}
	})
	hooks := quietHooks()
	hooks.evidence = newTurnEvidence(root)
	// The model's own checks stand in when the acceptance gate is off.
	if _, _, err := nativeTurn(context.Background(), provider, scope, config{"acceptance_gate": false}, nil, "Change app.py", hooks); err != nil {
		t.Fatal(err)
	}
	report := hooks.evidence.report("completed")
	text := report.Render("", root)
	for _, want := range []string{"DONE", "M app.py  +2 -1", "A new.py  +1", "2 files · +3 / -1", "— no check ran (none could be inferred)", "Review the changes — no check ran"} {
		if !strings.Contains(text, want) {
			t.Errorf("missing %q in\n%s", want, text)
		}
	}
	if !strings.Contains(hooks.evidence.ledger.DiffText(), "+B\n+c\n") {
		t.Fatal(hooks.evidence.ledger.DiffText())
	}
}
