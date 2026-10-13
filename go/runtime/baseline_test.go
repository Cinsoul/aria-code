package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"google.golang.org/genai"
)

func gitFixture(t *testing.T, files map[string]string) string {
	t.Helper()
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git is not installed")
	}
	root := t.TempDir()
	run := func(args ...string) string {
		cmd := exec.Command("git", append([]string{"-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false"}, args...)...)
		cmd.Dir = root
		out, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatal(args, string(out))
		}
		return string(out)
	}
	run("init", "-q")
	for name, text := range files {
		os.MkdirAll(filepath.Dir(filepath.Join(root, name)), 0o755)
		if err := os.WriteFile(filepath.Join(root, name), []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	run("add", "-A")
	run("commit", "-q", "-m", "base")
	return root
}

func gitStatus(t *testing.T, root string) string {
	cmd := exec.Command("git", "status", "--porcelain")
	cmd.Dir = root
	out, err := cmd.Output()
	if err != nil {
		t.Fatal(err)
	}
	return string(out)
}

// snapshotProbe is a baseline runner that reports what it sees in its cwd.
func snapshotProbe(seen *[]string) baselineRunner {
	return func(ctx context.Context, command, cwd string) map[string]any {
		var lines []string
		for _, name := range []string{"app.py", "new.py", "notes.txt", "sub/inner.py"} {
			body, err := os.ReadFile(filepath.Join(cwd, name))
			if err != nil {
				lines = append(lines, name+": absent")
			} else {
				lines = append(lines, name+": "+strings.TrimSpace(string(body)))
			}
		}
		*seen = append(*seen, cwd)
		return map[string]any{"success": true, "data": map[string]any{"exit_code": 1, "stdout": strings.Join(lines, "\n")}}
	}
}

func TestBaselineRunsOnTheTreeBeforeThisTurn(t *testing.T) {
	root := gitFixture(t, map[string]string{"app.py": "old\n", "sub/inner.py": "inner\n"})
	if err := os.WriteFile(filepath.Join(root, "notes.txt"), []byte("untracked before the turn\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	// This turn: app.py edited, new.py created.
	os.WriteFile(filepath.Join(root, "app.py"), []byte("new\n"), 0o644)
	os.WriteFile(filepath.Join(root, "new.py"), []byte("created\n"), 0o644)
	statusBefore := gitStatus(t, root)
	var seen []string
	b := newTestBaseline(config{}, root, t.TempDir(), snapshotProbe(&seen))
	b.remember(fileChange{path: filepath.Join(root, "app.py"), existed: true, before: []byte("old\n")})
	b.remember(fileChange{path: filepath.Join(root, "app.py"), existed: true, before: []byte("intermediate\n")})
	b.remember(fileChange{path: filepath.Join(root, "new.py"), existed: false})
	r := b.result(context.Background(), "pytest -q")
	if r == nil {
		t.Fatal("no baseline")
	}
	want := "app.py: old\nnew.py: absent\nnotes.txt: untracked before the turn\nsub/inner.py: inner"
	if r.output != want || r.code != 1 {
		t.Fatalf("%q", r.output)
	}
	if _, err := os.Stat(seen[0]); !os.IsNotExist(err) {
		t.Fatal("the scratch worktree is removed")
	}
	if gitStatus(t, root) != statusBefore {
		t.Fatal("the user's index and files are untouched")
	}
	if b.result(context.Background(), "pytest -q"); len(seen) != 1 {
		t.Fatal("each command runs at most once per turn")
	}
}

func TestBaselineRunsInTheWorkspaceSubdirectory(t *testing.T) {
	root := gitFixture(t, map[string]string{"sub/inner.py": "inner\n"})
	var seen []string
	b := newTestBaseline(config{}, filepath.Join(root, "sub"), t.TempDir(), snapshotProbe(&seen))
	if r := b.result(context.Background(), "make"); r == nil || !strings.Contains(r.output, "inner.py: absent") {
		t.Fatal("cwd is the workspace inside the checkout", r)
	}
	if filepath.Base(seen[0]) != "sub" {
		t.Fatal(seen)
	}
}

func TestBaselineCopiesAWorkspaceOutsideGit(t *testing.T) {
	root := t.TempDir()
	os.WriteFile(filepath.Join(root, "app.py"), []byte("new\n"), 0o644)
	os.MkdirAll(filepath.Join(root, "node_modules", "big"), 0o755)
	os.WriteFile(filepath.Join(root, "node_modules", "big", "x.js"), []byte("skip me"), 0o644)
	var seen []string
	probe := snapshotProbe(&seen)
	sawModules := false
	b := newTestBaseline(config{}, root, t.TempDir(), func(ctx context.Context, command, cwd string) map[string]any {
		_, err := os.Stat(filepath.Join(cwd, "node_modules"))
		sawModules = err == nil
		return probe(ctx, command, cwd)
	})
	b.remember(fileChange{path: filepath.Join(root, "app.py"), existed: true, before: []byte("old\n")})
	r := b.result(context.Background(), "make")
	if r == nil || !strings.HasPrefix(r.output, "app.py: old") || sawModules {
		t.Fatal(r, sawModules)
	}
	if body, _ := os.ReadFile(filepath.Join(root, "app.py")); string(body) != "new\n" {
		t.Fatal("the workspace itself is untouched")
	}
}

func TestBaselineRefusesToCopyAHugeWorkspace(t *testing.T) {
	root := t.TempDir()
	for i := 0; i <= baselineCopyMaxFiles; i++ {
		os.WriteFile(filepath.Join(root, fmt.Sprintf("f%05d", i)), nil, 0o644)
	}
	ran := false
	b := newTestBaseline(config{}, root, t.TempDir(), func(context.Context, string, string) map[string]any { ran = true; return nil })
	if b.result(context.Background(), "make") != nil || ran {
		t.Fatal("too big for a baseline: every failure counts as the change's")
	}
}

func TestCompareBaselineAndKeepCollecting(t *testing.T) {
	after := "FAILED tests/test_a.py::test_x - assert 1\nERROR tests/test_b.py\nFAILED tests/test_c.py::test_z"
	before := &baselineRun{code: 1, output: "FAILED tests/test_a.py::test_x - assert 1\n"}
	c := compareBaseline(after, true, before)
	if c.Preexisting || strings.Join(c.NewFailures, ",") != "tests/test_b.py,tests/test_c.py::test_z" || strings.Join(c.OldFailures, ",") != "tests/test_a.py::test_x" {
		t.Fatal(c)
	}
	if c := compareBaseline("boom", true, &baselineRun{code: 2}); !c.Preexisting {
		t.Fatal("a non-pytest command failing before too is pre-existing")
	}
	if c := compareBaseline("boom", true, &baselineRun{code: 0}); c.Preexisting || c.Note != "passed before this change" {
		t.Fatal(c)
	}
	for command, want := range map[string]string{
		"python3 -m pytest -q": "python3 -m pytest -q --continue-on-collection-errors",
		"pytest | tail":        "pytest | tail",
		"npm test":             "npm test",
	} {
		if got := keepCollecting(command); got != want {
			t.Errorf("%q: %q", command, got)
		}
	}
}

func TestPreexistingFailuresAreNotSentBackToBeRepaired(t *testing.T) {
	t.Setenv("ARIA_HOME", t.TempDir())
	for _, tc := range []struct {
		name, before string
		repaired     bool
	}{
		{"failing before the turn", "still broken\n", false},
		{"passing before the turn", "fixed\n", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := gitFixture(t, map[string]string{"app.py": tc.before})
			scope, err := newScope(root, nil, nil, false)
			if err != nil {
				t.Fatal(err)
			}
			repairs := 0
			provider := providerFunc(func(ctx context.Context, contents []*genai.Content, system string, tools []*genai.Tool, emit func(string)) (*genai.Content, error) {
				last := contents[len(contents)-1].Parts[0]
				if strings.HasPrefix(last.Text, "## 验收未通过") {
					repairs++
				}
				if last.FunctionResponse == nil && repairs == 0 {
					return &genai.Content{Role: "model", Parts: []*genai.Part{call("write_file", map[string]any{"path": "app.py", "content": "broken by the turn\n"})}}, nil
				}
				emit("Done.")
				return genai.NewContentFromText("Done.", genai.RoleModel), nil
			})
			hooks := quietHooks()
			hooks.evidence = newTurnEvidence(root)
			cfg := config{"acceptance_commands": []any{contentCheck()}}
			if _, _, err := nativeTurn(context.Background(), provider, scope, cfg, nil, "Edit app.py", hooks); err != nil {
				t.Fatal(err)
			}
			if (repairs > 0) != tc.repaired {
				t.Fatalf("repairs: %d", repairs)
			}
			report := hooks.evidence.report("completed")
			text := report.Render("", root)
			if !tc.repaired && (report.Status != "done" || !strings.Contains(text, "— already failing before this change") ||
				!strings.Contains(text, "the failing checks already failed before this change")) {
				t.Fatal(text)
			}
			if tc.repaired && report.Status != "incomplete" {
				t.Fatal(text)
			}
		})
	}
}
