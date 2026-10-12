package main

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func cloudFixture(t *testing.T) string {
	t.Helper()
	folder := t.TempDir()
	if err := os.MkdirAll(filepath.Join(folder, "configurations"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(folder, "active_config"), []byte("default\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(folder, "configurations", "config_default"), []byte("[core]\naccount = active@example.invalid\nproject = selected-project\n"), 0600); err != nil {
		t.Fatal(err)
	}
	db, err := sql.Open("sqlite", filepath.Join(folder, "credentials.db"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("CREATE TABLE credentials (account_id TEXT PRIMARY KEY, value BLOB)"); err != nil {
		t.Fatal(err)
	}
	for _, account := range []string{"other@example.invalid", "active@example.invalid"} {
		body, _ := json.Marshal(map[string]any{"type": "authorized_user", "client_id": "test-client", "client_secret": "fixture-client-secret", "refresh_token": "fixture-refresh-for-" + account})
		if _, err := db.Exec("INSERT INTO credentials VALUES (?, ?)", account, body); err != nil {
			t.Fatal(err)
		}
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}
	return folder
}
func TestNativeGoogleLoginUsesOnlyActiveAccountWithoutChangingStore(t *testing.T) {
	folder := cloudFixture(t)
	path := filepath.Join(folder, "credentials.db")
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	identity, err := readCloudIdentity(folder)
	if err != nil || identity.project != "selected-project" {
		t.Fatal("configuration did not resolve", err)
	}
	credential, err := nativeCloudCredentials(context.Background(), identity)
	if err != nil {
		t.Fatal(err)
	}
	var value map[string]any
	if err := json.Unmarshal(credential.JSON(), &value); err != nil {
		t.Fatal(err)
	}
	if value["refresh_token"] != "fixture-refresh-for-active@example.invalid" {
		t.Fatal("inactive account was selected")
	}
	after, err := os.ReadFile(path)
	if err != nil || sha256.Sum256(before) != sha256.Sum256(after) {
		t.Fatal("credential database changed", err)
	}
	if _, err := os.Stat(path + "-wal"); !os.IsNotExist(err) {
		t.Fatal("read-only login created a journal")
	}
}
func TestAnUnavailableActiveAccountDoesNotFallBackToAnotherAccount(t *testing.T) {
	folder := cloudFixture(t)
	identity, err := readCloudIdentity(folder)
	if err != nil {
		t.Fatal(err)
	}
	identity.account = "missing@example.invalid"
	if _, err := nativeCloudCredentials(context.Background(), identity); err == nil {
		t.Fatal("missing active account switched identity")
	}
	if err := os.WriteFile(filepath.Join(folder, "active_config"), []byte("../escape"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := readCloudIdentity(folder); err == nil {
		t.Fatal("active configuration traversed directories")
	}
}
