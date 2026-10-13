package main

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"
	"time"

	"cloud.google.com/go/auth"
)

type tokenFunc func(context.Context) (*auth.Token, error)

func (f tokenFunc) Token(ctx context.Context) (*auth.Token, error) { return f(ctx) }
func TestExpiredCloudLoginCacheRefreshesWithoutSelectingAnotherAccount(t *testing.T) {
	folder := cloudFixture(t)
	identity, err := readCloudIdentity(folder)
	if err != nil {
		t.Fatal(err)
	}
	db, err := sql.Open("sqlite", filepath.Join(folder, "access_tokens.db"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("CREATE TABLE access_tokens (account_id TEXT PRIMARY KEY, access_token TEXT, token_expiry TEXT)"); err != nil {
		t.Fatal(err)
	}
	for _, row := range []struct {
		account, value string
		expiry         time.Time
	}{{identity.account, "expired", time.Now().Add(-time.Minute)}, {"other@example.invalid", "must-not-use", time.Now().Add(time.Hour)}} {
		if _, err := db.Exec("INSERT INTO access_tokens VALUES (?, ?, ?)", row.account, row.value, row.expiry.UTC().Format(time.RFC3339Nano)); err != nil {
			t.Fatal(err)
		}
	}
	db.Close()
	calls := 0
	p := cloudTokenProvider{identity: identity, values: map[string]any{}, fallback: tokenFunc(func(context.Context) (*auth.Token, error) {
		calls++
		return &auth.Token{Value: "refreshed", Expiry: time.Now().Add(time.Hour)}, nil
	})}
	token, err := p.Token(context.Background())
	if err != nil || token.Value != "refreshed" || calls != 1 {
		t.Fatal("expired account cache did not use its own refresh provider")
	}
}
