package main

// Match the existing application's "gcloud auth login" route without starting
// gcloud (which embeds Python). Only the active account is read, in immutable
// read-only mode. Refresh credentials stay in memory and use Google's Go auth
// library; neither credential values nor account identifiers enter UI events.
import (
	"bufio"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"cloud.google.com/go/auth"
	"cloud.google.com/go/auth/credentials"
	_ "modernc.org/sqlite"
)

const cloudScope = "https://www.googleapis.com/auth/cloud-platform"

type cloudIdentity struct{ folder, account, project, credentialFile string }

func cloudFolder() string {
	if value := os.Getenv("CLOUDSDK_CONFIG"); value != "" {
		return value
	}
	if runtime.GOOS == "windows" {
		return filepath.Join(os.Getenv("APPDATA"), "gcloud")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config", "gcloud")
}
func readCloudIdentity(folder string) (cloudIdentity, error) {
	identity := cloudIdentity{folder: folder}
	active := "default"
	if b, err := os.ReadFile(filepath.Join(folder, "active_config")); err == nil {
		active = strings.TrimSpace(string(b))
	}
	if !validID.MatchString(active) {
		return identity, errors.New("invalid active Google Cloud configuration name")
	}
	f, err := os.Open(filepath.Join(folder, "configurations", "config_"+active))
	if err != nil {
		return identity, errors.New("Google Cloud active configuration is unavailable")
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	section := ""
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.ToLower(strings.Trim(line, "[]"))
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key, value = strings.ToLower(strings.TrimSpace(key)), strings.TrimSpace(value)
		if section == "core" {
			switch key {
			case "account":
				identity.account = value
			case "project":
				identity.project = value
			}
		}
		if section == "auth" && key == "credential_file_override" {
			identity.credentialFile = value
		}
	}
	if scanner.Err() != nil {
		return identity, errors.New("Google Cloud configuration could not be read")
	}
	return identity, nil
}
func hasDefaultCredentials() bool {
	if os.Getenv("GOOGLE_APPLICATION_CREDENTIALS") != "" || os.Getenv("K_SERVICE") != "" || os.Getenv("GCE_METADATA_HOST") != "" {
		return true
	}
	if _, err := os.Stat(filepath.Join(cloudFolder(), "application_default_credentials.json")); err == nil {
		return true
	}
	return false
}
func nativeCloudCredentials(ctx context.Context, identity cloudIdentity) (*auth.Credentials, error) {
	options := &credentials.DetectOptions{Scopes: []string{cloudScope}, Client: &http.Client{Timeout: 20 * time.Second, Transport: nativeTransport()}}
	if identity.credentialFile != "" {
		options.CredentialsFile = identity.credentialFile
		return credentials.DetectDefault(options)
	}
	if identity.account == "" {
		return nil, errors.New("Google Cloud configuration has no active account")
	}
	path := filepath.Join(identity.folder, "credentials.db")
	if _, err := os.Stat(path); err != nil {
		return nil, errors.New("Google Cloud login credentials are unavailable")
	}
	uri := (&url.URL{Scheme: "file", Path: filepath.ToSlash(path)}).String() + "?mode=ro&immutable=1"
	db, err := sql.Open("sqlite", uri)
	if err != nil {
		return nil, errors.New("Google Cloud credential store cannot be opened")
	}
	defer db.Close()
	var body []byte
	if err := db.QueryRowContext(ctx, "SELECT value FROM credentials WHERE account_id = ?", identity.account).Scan(&body); err != nil {
		return nil, errors.New("Google Cloud active account credentials are unavailable")
	}
	if len(body) > 1<<20 {
		return nil, errors.New("Google Cloud credential record exceeds limit")
	}
	var value map[string]any
	if json.Unmarshal(body, &value) != nil {
		return nil, errors.New("Google Cloud credential record is invalid")
	}
	// Older Cloud SDK versions serialize OAuth fields without the ADC type.
	if _, ok := value["type"]; !ok {
		if _, ok := value["refresh_token"]; !ok {
			return nil, errors.New("Google Cloud credential type is unsupported")
		}
		value["type"] = "authorized_user"
	}
	if _, ok := value["token_uri"]; !ok {
		value["token_uri"] = "https://oauth2.googleapis.com/token"
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, errors.New("Google Cloud credentials could not be decoded")
	}
	options.CredentialsJSON = encoded
	creds, err := credentials.DetectDefault(options)
	if err != nil {
		return nil, err
	}
	provider := &cloudTokenProvider{identity: identity, values: value, fallback: creds.TokenProvider}
	creds.TokenProvider = auth.NewCachedTokenProvider(provider, nil)
	return creds, nil
}

type cloudTokenProvider struct {
	identity cloudIdentity
	values   map[string]any
	fallback auth.TokenProvider
}

func (p *cloudTokenProvider) Token(ctx context.Context) (*auth.Token, error) {
	if token := p.cached(ctx); token != nil {
		return token, nil
	}
	bounded, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	return p.fallback.Token(bounded)
}
func (p *cloudTokenProvider) cached(ctx context.Context) *auth.Token {
	path := filepath.Join(p.identity.folder, "access_tokens.db")
	if _, err := os.Stat(path); err != nil {
		return nil
	}
	uri := (&url.URL{Scheme: "file", Path: filepath.ToSlash(path)}).String() + "?mode=ro&immutable=1"
	db, err := sql.Open("sqlite", uri)
	if err != nil {
		return nil
	}
	defer db.Close()
	keys := []string{p.identity.account}
	if refresh, ok := p.values["refresh_token"].(string); ok {
		sum := sha256.Sum256([]byte(refresh))
		keys = append(keys, hex.EncodeToString(sum[:]))
	}
	for _, key := range keys {
		var value string
		var expiry any
		if err := db.QueryRowContext(ctx, "SELECT access_token, token_expiry FROM access_tokens WHERE account_id = ?", key).Scan(&value, &expiry); err != nil {
			continue
		}
		var when time.Time
		switch date := expiry.(type) {
		case time.Time:
			when = date
		case string:
			for _, layout := range []string{time.RFC3339Nano, "2006-01-02 15:04:05.999999999-07:00", "2006-01-02 15:04:05.999999999", "2006-01-02 15:04:05"} {
				if result, err := time.Parse(layout, date); err == nil {
					when = result
					break
				}
			}
		}
		if value != "" && when.After(time.Now().Add(4*time.Minute)) {
			return &auth.Token{Value: value, Expiry: when}
		}
	}
	return nil
}
