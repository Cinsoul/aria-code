package main

import (
	"context"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func approvalServer(t *testing.T, cfg config, options appOptions) *server {
	t.Helper()
	root, project := t.TempDir(), t.TempDir()
	if err := atomicJSON(filepath.Join(root, "config.json"), cfg); err != nil {
		t.Fatal(err)
	}
	options.root, options.workspace, options.noninteractive = root, project, true
	s, err := newServer(options, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestApprovalRequirementFollowsRiskLevels(t *testing.T) {
	for _, tc := range []struct {
		command, mode string
		auto          any
		want          string
	}{
		{"ls", "manual", nil, "ask"},
		{"ls", "risk", nil, "auto"},
		{"git add -A", "risk", 1.0, "auto"},
		{"npm install", "risk", 1.0, "ask"},
		{"npm install", "risk", 2.0, "auto"},
		{"npm install", "risk", "2", "auto"},
		{"git push", "risk", 9.0, "ask"},
		{"git add -A", "risk", "high", "auto"},
		{"git add -A", "risk", -3.0, "ask"},
		{"rm -rf build", "risk", 2.0, "always"},
		{"rm -rf build", "manual", nil, "always"},
	} {
		if got := approvalRequirement(AssessCommand(tc.command), tc.mode, tc.auto); got != tc.want {
			t.Errorf("%q mode=%s auto=%v: %s, want %s", tc.command, tc.mode, tc.auto, got, tc.want)
		}
	}
}

func TestRiskModeAutoApprovesLowRiskAndSaysSo(t *testing.T) {
	s := approvalServer(t, config{"approval_mode": "risk", "auto_approve_level": 1.0}, appOptions{})
	ok, note, err := s.approve(context.Background(), "write_file", map[string]any{"path": "a.txt"}, fileChange{})
	if err != nil || !ok || note != "auto-approved · L1 low · Edit files" {
		t.Fatal(ok, note, err)
	}
	if ok, _, _ := s.approve(context.Background(), "run_command", map[string]any{"command": "npm install"}, fileChange{}); ok {
		t.Fatal("L2 is above auto_approve_level 1")
	}
}

func TestManualModeStillAsks(t *testing.T) {
	s := approvalServer(t, config{}, appOptions{})
	if ok, _, _ := s.approve(context.Background(), "write_file", map[string]any{"path": "a.txt"}, fileChange{}); ok {
		t.Fatal("manual mode must not auto-approve")
	}
	if ok, _, _ := s.approve(context.Background(), "read_file", map[string]any{"path": "a.txt"}, fileChange{}); !ok {
		t.Fatal("reads need no approval")
	}
}

func TestCriticalActionsAlwaysAskEvenWithStandingGrants(t *testing.T) {
	s := approvalServer(t, config{"approval_mode": "risk", "auto_approve_level": 2.0}, appOptions{skipPermissions: true, allowedTools: []string{"run_command"}})
	ok, reason, err := s.approve(context.Background(), "run_command", map[string]any{"command": "rm -rf build"}, fileChange{})
	if err != nil || ok || !strings.Contains(reason, "L4 critical actions always need interactive approval") {
		t.Fatal(ok, reason, err)
	}
	if ok, _, _ := s.approve(context.Background(), "run_command", map[string]any{"command": "git push"}, fileChange{}); !ok {
		t.Fatal("standing grants still cover L3")
	}
}

func TestExplicitAskPolicyIsNotAutoApproved(t *testing.T) {
	s := approvalServer(t, config{"approval_mode": "risk", "auto_approve_level": 2.0}, appOptions{})
	policy := filepath.Join(s.opts.root, "tool_policy.json")
	if err := os.WriteFile(policy, []byte(`{"ask_always":["write_file"]}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if ok, _, _ := s.approve(context.Background(), "write_file", map[string]any{"path": "a.txt"}, fileChange{}); ok {
		t.Fatal("an explicit ask policy must ask")
	}
}

func TestRiskCardMatchesTheApprovalCard(t *testing.T) {
	card := riskCard(AssessCommand("npm install"))
	want := []string{
		"Risk     L2 medium · 43/100 · reversible",
		"Network  registry.npmjs.org",
		"Files    package.json, package-lock.json",
		"Why      Changes installed dependencies (npm install)",
	}
	if strings.Join(card, "\n") != strings.Join(want, "\n") {
		t.Fatalf("%q", card)
	}
}
