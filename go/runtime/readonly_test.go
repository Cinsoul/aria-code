package main

import (
	"io"
	"os"
	"path/filepath"
	"testing"
)

func TestReadOnlyCannotBeOverriddenBySkipPromptsOrAdditionalRoots(t *testing.T) {
	root, project := t.TempDir(), t.TempDir()
	if err := atomicJSON(filepath.Join(root, "config.json"), config{"permission_mode": "read-only"}); err != nil {
		t.Fatal(err)
	}
	s, err := newServer(appOptions{root: root, workspace: project, skipPermissions: true, writeRoots: []string{project}}, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	if !s.scope.readOnly {
		t.Fatal("read-only configuration was ignored")
	}
	if _, err := propose(s.scope, "write_file", map[string]any{"path": "note.txt", "content": "must not be written"}); err == nil {
		t.Fatal("skipping prompts bypassed read-only")
	}
	if _, err := os.Stat(filepath.Join(project, "note.txt")); !os.IsNotExist(err) {
		t.Fatal("read-only write occurred")
	}
}
