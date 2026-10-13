package main

// The test baseline — a port of src/aria_code/runtime/baseline.py. A red
// check sends the model back to repair; when the test was already failing
// before the turn touched anything, that sends it to "fix" unrelated code.
// The baseline reruns a failed check once on the code as it was before this
// turn and compares: pytest by test id, anything else by exit status.
//
// "Before" is the working tree now with this turn's applied edits undone —
// the native turn keeps each file's content from before its first edit.
// Edits a shell command made are not recorded, so they are in the baseline
// too. In a git repository the working tree is snapshotted into a scratch
// index (the user's index and files are untouched) and checked out as a
// temporary worktree; outside one it is copied when small enough. Either is
// removed straight after. Python's task-worktree base commits have no native
// counterpart yet.

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

var (
	pytestFailure = pyRegexp(`(?m)^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-\s|$)`)
	pytestCommand = pyRegexp(`(?:^|[\s/])(?:py\.test|pytest)(?:\s|$)`)
	shellMeta     = regexp.MustCompile("[|;&<>`$]")
)

const (
	baselineCopyMaxFiles = 5_000
	baselineCopyMaxBytes = 100 * 1024 * 1024
)

var baselineCopySkipped = set(".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
	".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".nox")

var dependencyDirs = []string{"node_modules", ".venv", "venv", "env", ".tox"}

// failingTests is baseline.failing_tests: pytest's failing ids from its
// short summary lines.
func failingTests(output string) map[string]bool {
	out := map[string]bool{}
	for _, m := range pytestFailure.FindAllStringSubmatch(output, -1) {
		out[m[1]] = true
	}
	return out
}

type baselineComparison struct {
	Preexisting bool     `json:"preexisting"`
	NewFailures []string `json:"new_failures"`
	OldFailures []string `json:"old_failures"`
	Note        string   `json:"note"`
}

// compareBaseline is baseline.compare for a failed check and its run before
// the change (nil when unknown).
func compareBaseline(afterOutput string, afterFailed bool, before *baselineRun) baselineComparison {
	if before == nil || !afterFailed {
		return baselineComparison{NewFailures: []string{}, OldFailures: []string{}}
	}
	if before.code == 0 {
		return baselineComparison{NewFailures: []string{}, OldFailures: []string{}, Note: "passed before this change"}
	}
	after, previous := failingTests(afterOutput), failingTests(before.output)
	if len(after) > 0 {
		added, kept := []string{}, []string{}
		for id := range after {
			if previous[id] {
				kept = append(kept, id)
			} else {
				added = append(added, id)
			}
		}
		sort.Strings(added)
		sort.Strings(kept)
		note := ""
		if len(added) == 0 {
			note = "failing before this change"
		}
		return baselineComparison{Preexisting: len(added) == 0, NewFailures: added, OldFailures: kept, Note: note}
	}
	return baselineComparison{Preexisting: true, NewFailures: []string{}, OldFailures: []string{}, Note: "failing before this change"}
}

// keepCollecting is baseline._keep_collecting: a pytest baseline continues
// past collection errors, which the test of a not-yet-written function causes.
func keepCollecting(command string) string {
	if !pytestCommand.MatchString(command) || strings.Contains(command, "--continue-on-collection-errors") || shellMeta.MatchString(command) {
		return command
	}
	return command + " --continue-on-collection-errors"
}

type baselineRun struct {
	code   int
	output string
}

// priorFile is a file's state before this turn's first edit to it.
type priorFile struct {
	existed bool
	content []byte
}

// baselineRunner runs a command in a directory and returns the run result
// the acceptance gate reads.
type baselineRunner func(ctx context.Context, command, cwd string) map[string]any

type testBaseline struct {
	workspace string
	scratch   string
	run       baselineRunner
	prior     map[string]priorFile
	results   map[string]*baselineRun
}

func newTestBaseline(cfg config, workspace, scratch string, run baselineRunner) *testBaseline {
	if !cfg.boolean("test_baseline", true) || run == nil {
		return nil
	}
	return &testBaseline{workspace: resolveLoose(workspace), scratch: scratch, run: run,
		prior: map[string]priorFile{}, results: map[string]*baselineRun{}}
}

// remember records a file's content before its first edit in this turn.
func (b *testBaseline) remember(c fileChange) {
	if b == nil {
		return
	}
	path := resolveLoose(c.path)
	if _, seen := b.prior[path]; !seen {
		b.prior[path] = priorFile{existed: c.existed, content: c.before}
	}
}

// result is the check's (exit code, output) before the change, or nil when
// it could not be found out. Each command runs at most once per turn.
func (b *testBaseline) result(ctx context.Context, command string) *baselineRun {
	if r, ok := b.results[command]; ok {
		return r
	}
	r, err := b.runBefore(ctx, keepCollecting(command))
	if err != nil {
		r = nil
	}
	b.results[command] = r
	return r
}

func randomName() string {
	var b [4]byte
	rand.Read(b[:])
	return "baseline-" + hex.EncodeToString(b[:])
}

func (b *testBaseline) runBefore(ctx context.Context, command string) (*baselineRun, error) {
	destination := filepath.Join(b.scratch, randomName())
	repo, inRepo := gitTopLevel(ctx, b.workspace)
	if !inRepo {
		if err := copyWorkspace(b.workspace, destination); err != nil {
			os.RemoveAll(destination)
			return nil, err
		}
		defer os.RemoveAll(destination)
		b.undo(b.workspace, destination)
		return runResult(b.run(ctx, command, destination)), nil
	}
	commit, err := snapshotTree(ctx, repo)
	if err != nil {
		return nil, err
	}
	linked, err := checkoutWorktree(ctx, repo, commit, destination)
	if err != nil {
		return nil, err
	}
	defer removeWorktree(repo, destination, linked)
	b.undo(repo, destination)
	cwd := destination
	if rel, ok := relativeInside(b.workspace, repo); ok && rel != "." {
		cwd = filepath.Join(destination, filepath.FromSlash(rel))
	}
	if err := os.MkdirAll(cwd, 0o755); err != nil {
		return nil, err
	}
	return runResult(b.run(ctx, command, cwd)), nil
}

func runResult(raw map[string]any) *baselineRun {
	code, output, errText := readRunResult(raw)
	if errText != "" {
		code = 1
	}
	return &baselineRun{code: code, output: output}
}

// undo puts back, in the scratch copy of root, what this turn's edits replaced.
func (b *testBaseline) undo(root, destination string) {
	for path, prior := range b.prior {
		rel, ok := relativeInside(path, root)
		if !ok {
			continue
		}
		target := filepath.Join(destination, filepath.FromSlash(rel))
		if prior.existed {
			os.MkdirAll(filepath.Dir(target), 0o755)
			os.WriteFile(target, prior.content, 0o644)
		} else {
			os.Remove(target)
		}
	}
}

// ── git ─────────────────────────────────────────────────────────────────────

func git(ctx context.Context, dir string, env []string, timeout time.Duration, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Dir = dir
	cmd.Stdin = nil
	if env != nil {
		cmd.Env = append(os.Environ(), env...)
	}
	var stderr strings.Builder
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		detail := strings.TrimSpace(stderr.String())
		if detail == "" {
			detail = err.Error()
		}
		return "", errors.New(detail)
	}
	return strings.TrimSpace(string(out)), nil
}

func gitTopLevel(ctx context.Context, workspace string) (string, bool) {
	top, err := git(ctx, workspace, nil, time.Minute, "rev-parse", "--show-toplevel")
	if err != nil || top == "" {
		return "", false
	}
	return resolveLoose(filepath.FromSlash(top)), true
}

// snapshotTree is task_worktree.snapshot: the working tree, tracked and
// untracked alike (ignored excluded), committed through a scratch index.
func snapshotTree(ctx context.Context, repo string) (string, error) {
	scratch, err := os.MkdirTemp("", "aria-snapshot-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(scratch)
	env := []string{"GIT_INDEX_FILE=" + filepath.Join(scratch, "index"),
		"GIT_AUTHOR_NAME=Aria Code", "GIT_AUTHOR_EMAIL=aria@localhost",
		"GIT_COMMITTER_NAME=Aria Code", "GIT_COMMITTER_EMAIL=aria@localhost"}
	head, _ := git(ctx, repo, env, time.Minute, "rev-parse", "--verify", "-q", "HEAD")
	if head != "" {
		if _, err := git(ctx, repo, env, time.Minute, "read-tree", head); err != nil {
			return "", err
		}
	}
	if _, err := git(ctx, repo, env, time.Minute, "add", "-A", "--", ".", ":(exclude,glob)**/__pycache__/**", ":(exclude,glob)**/*.py[co]"); err != nil {
		return "", err
	}
	tree, err := git(ctx, repo, env, time.Minute, "write-tree")
	if err != nil {
		return "", err
	}
	args := []string{"commit-tree", tree}
	if head != "" {
		args = append(args, "-p", head)
	}
	return git(ctx, repo, env, time.Minute, append(args, "-m", "aria: task base snapshot")...)
}

// checkoutWorktree is task_worktree.checkout: a detached worktree of commit,
// with ignored dependency directories linked in from the repository.
func checkoutWorktree(ctx context.Context, repo, commit, destination string) ([]string, error) {
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return nil, err
	}
	if _, err := git(ctx, repo, nil, 5*time.Minute, "worktree", "add", "--detach", destination, commit); err != nil {
		os.RemoveAll(destination)
		return nil, err
	}
	var linked []string
	for _, name := range dependencyDirs {
		source := filepath.Join(repo, name)
		if info, err := os.Stat(source); err != nil || !info.IsDir() || exists(filepath.Join(destination, name)) {
			continue
		}
		if _, err := git(ctx, repo, nil, time.Minute, "check-ignore", "-q", name); err != nil {
			continue // tracked or not ignored: it came with the checkout
		}
		if os.Symlink(source, filepath.Join(destination, name)) == nil {
			linked = append(linked, name)
		}
	}
	return linked, nil
}

func removeWorktree(repo, destination string, linked []string) {
	for _, name := range linked {
		link := filepath.Join(destination, name)
		if info, err := os.Lstat(link); err == nil && info.Mode()&fs.ModeSymlink != 0 {
			os.Remove(link)
		}
	}
	ctx := context.Background()
	if _, err := git(ctx, repo, nil, time.Minute, "worktree", "remove", "--force", destination); err != nil {
		os.RemoveAll(destination)
		git(ctx, repo, nil, time.Minute, "worktree", "prune")
	}
}

// copyWorkspace is Baseline._copy: the workspace outside git, skipping
// dependency and cache directories, refused when too big. Symbolic links are
// copied as links: they may point outside the workspace.
func copyWorkspace(source, destination string) error {
	type entry struct{ from, to string }
	var files []entry
	total := int64(0)
	tooBig := errors.New("workspace too large for a baseline copy")
	err := filepath.WalkDir(source, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			if path != source && baselineCopySkipped[d.Name()] {
				return filepath.SkipDir
			}
			return nil
		}
		if d.Type()&fs.ModeSymlink == 0 {
			if !d.Type().IsRegular() {
				return nil
			}
			info, err := d.Info()
			if err != nil {
				return nil
			}
			total += info.Size()
		}
		rel, _ := filepath.Rel(source, path)
		files = append(files, entry{path, filepath.Join(destination, rel)})
		if len(files) > baselineCopyMaxFiles || total > baselineCopyMaxBytes {
			return tooBig
		}
		return nil
	})
	if err != nil {
		return err
	}
	for _, f := range files {
		if err := os.MkdirAll(filepath.Dir(f.to), 0o755); err != nil {
			return err
		}
		info, err := os.Lstat(f.from)
		if err != nil {
			return err
		}
		if info.Mode()&fs.ModeSymlink != 0 {
			target, err := os.Readlink(f.from)
			if err != nil {
				return err
			}
			if err := os.Symlink(target, f.to); err != nil {
				return err
			}
			continue
		}
		body, err := os.ReadFile(f.from)
		if err != nil {
			return err
		}
		if err := os.WriteFile(f.to, body, info.Mode().Perm()); err != nil {
			return err
		}
	}
	return os.MkdirAll(destination, 0o755)
}
