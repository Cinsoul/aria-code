package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestStateRootsKeepExistingUsersAndHonourExplicitHome(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home)
	t.Setenv("ARIA_HOME", "")
	root, err := stateRoot()
	if err != nil || root != filepath.Join(home, ".aria-code") {
		t.Fatal(root, err)
	}
	if err := os.Mkdir(filepath.Join(home, ".arthera"), 0700); err != nil {
		t.Fatal(err)
	}
	root, err = stateRoot()
	if err != nil || root != filepath.Join(home, ".arthera") {
		t.Fatal(root, err)
	}
	t.Setenv("ARIA_HOME", "~/native-state")
	root, err = stateRoot()
	if err != nil || root != filepath.Join(home, "native-state") {
		t.Fatal(root, err)
	}
}
func TestSessionReadsExistingFormatAndKeepsSignatureBytes(t *testing.T) {
	root := t.TempDir()
	id := "old-session"
	path, err := sessionPath(root, id)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	legacy := `{"id":"old-session","messages":[{"role":"user","content":"你好"}],"metadata":{"title":"Existing"},"updated_at":"2026-10-11"}`
	if err := os.WriteFile(path, []byte(legacy), 0600); err != nil {
		t.Fatal(err)
	}
	s, err := loadSession(root, id)
	if err != nil || s.Messages[0]["content"] != "你好" {
		t.Fatal(s, err)
	}
	s.ProviderContents = json.RawMessage(`[{"role":"model","parts":[{"thoughtSignature":"signed-call"}]}]`)
	if err := saveSession(root, s); err != nil {
		t.Fatal(err)
	}
	s, err = loadSession(root, id)
	if err != nil || s.Metadata["title"] != "Existing" {
		t.Fatal(s, err)
	}
	var contents, expected any
	if err := json.Unmarshal(s.ProviderContents, &contents); err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal([]byte(`[{"role":"model","parts":[{"thoughtSignature":"signed-call"}]}]`), &expected); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(contents, expected) {
		t.Fatal("provider signature lost", contents)
	}
	if err := os.WriteFile(filepath.Join(root, "sessions", "broken.json"), []byte("{bad"), 0600); err != nil {
		t.Fatal(err)
	}
	listed, err := listSessions(root, 20)
	if err != nil || len(listed) != 1 || listed[0]["id"] != id {
		t.Fatal(listed, err)
	}
}
func TestInvalidSessionIDsNeverCreateOrOverwriteOutsideState(t *testing.T) {
	root := t.TempDir()
	for _, id := range []string{"../outside", "/absolute", "a/b", "a\\b", "", "x\n"} {
		if _, err := sessionPath(root, id); err == nil {
			t.Fatalf("accepted %q", id)
		}
		if err := saveSession(root, snapshot{ID: id}); err == nil {
			t.Fatalf("saved %q", id)
		}
	}
}
