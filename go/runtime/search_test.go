package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestNativeGlobSearchAndHiddenDirectoryListing(t *testing.T) {
	root, outside := t.TempDir(), t.TempDir()
	s, err := newScope(root, nil, nil, false)
	if err != nil {
		t.Fatal(err)
	}
	for _, dir := range []string{"src", ".git", "node_modules"} {
		if err := os.MkdirAll(filepath.Join(root, dir), 0755); err != nil {
			t.Fatal(err)
		}
	}
	for _, path := range []string{"src/a.py", "root.py", "src/skip.txt"} {
		if err := os.WriteFile(filepath.Join(root, path), []byte("first\r\nTARGET source\r\n"), 0644); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(outside, "secret.py"), []byte("target must stay outside"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(outside, "secret.py"), filepath.Join(root, "leak.py")); err != nil && os.PathSeparator != '\\' {
		t.Fatal(err)
	}
	listed := fileList(context.Background(), s, map[string]any{"path": "."})
	if !listed.Success || listed.Data["count"] != 4 {
		t.Fatal("visible entries were silently hidden or symlink escaped", listed)
	}
	glob := fileGlob(context.Background(), s, map[string]any{"pattern": "**/*.py"})
	if !glob.Success || glob.Data["count"] != 2 {
		t.Fatal(glob)
	}
	search := searchCode(context.Background(), s, map[string]any{"pattern": "target", "glob": "**/*.py"})
	if !search.Success || search.Data["count"] != 2 {
		t.Fatal(search)
	}
	for _, match := range search.Data["matches"].([]map[string]any) {
		if match["line"] != 2 {
			t.Fatal("line evidence is incorrect", match)
		}
	}
}

func TestNativeMultiEditCommitsAllOrNoneAndPreservesCRLF(t *testing.T) {
	root := t.TempDir()
	s, err := newScope(root, nil, nil, false)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(root, "note.txt")
	original := "old\r\nunchanged\r\n"
	if err := os.WriteFile(path, []byte(original), 0644); err != nil {
		t.Fatal(err)
	}
	params := map[string]any{"path": "note.txt", "edits": []any{map[string]any{"old_string": "old", "new_string": "new"}, map[string]any{"old_string": "missing", "new_string": "bad"}}}
	if _, err := propose(s, "multi_edit", params); err == nil {
		t.Fatal("missing edit was accepted")
	}
	body, _ := os.ReadFile(path)
	if string(body) != original {
		t.Fatal("a failed batch partially changed the file")
	}
	params["edits"] = []any{map[string]any{"old_string": "old", "new_string": "new"}, map[string]any{"old_string": "new\nunchanged", "new_string": "final\nunchanged"}}
	change, err := propose(s, "multi_edit", params)
	if err != nil {
		t.Fatal(err)
	}
	if result := applyChange(s, change); !result.Success {
		t.Fatal(result)
	}
	body, _ = os.ReadFile(path)
	if string(body) != "final\r\nunchanged\r\n" {
		t.Fatal("ordered edits or CRLF lost", string(body))
	}
}
