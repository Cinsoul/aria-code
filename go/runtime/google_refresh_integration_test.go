package main

import (
	"context"
	"crypto/sha256"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

	"cloud.google.com/go/auth/credentials"
)

func TestGoogleLoginRefreshIntegration(t *testing.T) {
	if os.Getenv("ARIA_VERIFY_GOOGLE_LOGIN") != "1" {
		t.Skip("live Google login refresh is explicitly enabled for local verification")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()
	identity, err := readCloudIdentity(cloudFolder())
	if err != nil {
		t.Fatal("active Google Cloud identity is unavailable")
	}
	path := filepath.Join(identity.folder, "credentials.db")
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal("credential store unavailable")
	}
	c, err := nativeCloudCredentials(ctx, identity)
	if err != nil {
		t.Fatal("native Google credential resolution failed")
	}
	// A fresh provider deliberately bypasses the CLI access-token cache. The
	// refresh secret stays in memory; test output never includes credentials.
	fresh, err := credentials.DetectDefault(&credentials.DetectOptions{CredentialsJSON: c.JSON(), Scopes: []string{cloudScope}, Client: &http.Client{Timeout: 20 * time.Second, Transport: nativeTransport()}})
	if err != nil {
		t.Fatal("native credential refresh could not be configured")
	}
	token, err := fresh.Token(ctx)
	if err != nil || !token.IsValid() {
		t.Fatal("native Google OAuth refresh failed")
	}
	after, err := os.ReadFile(path)
	if err != nil || sha256.Sum256(before) != sha256.Sum256(after) {
		t.Fatal("credential store changed during read-only validation")
	}
}
