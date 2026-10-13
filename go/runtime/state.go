package main

// The native application uses the existing config/session formats. There is
// no Python process and no automatic relocation of a user's saved state.
import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const maxState = 16 << 20

var validID = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`)

type config map[string]any

func (c config) text(key, fallback string) string {
	if s, ok := c[key].(string); ok && strings.TrimSpace(s) != "" {
		return s
	}
	return fallback
}
func (c config) boolean(key string, fallback bool) bool {
	if value, ok := c[key].(bool); ok {
		return value
	}
	return fallback
}
func (c config) number(key string, fallback int) int {
	if value, ok := c[key].(float64); ok && value >= 0 && value < 1<<31 {
		return int(value)
	}
	return fallback
}

func stateRoot() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	if path := os.Getenv("ARIA_HOME"); path != "" {
		if path == "~" {
			path = home
		} else if strings.HasPrefix(path, "~/") {
			path = filepath.Join(home, path[2:])
		}
		return filepath.Abs(path)
	}
	legacy := filepath.Join(home, ".arthera")
	if _, err := os.Stat(legacy); err == nil {
		return legacy, nil
	}
	return filepath.Join(home, ".aria-code"), nil
}

func readJSON(path string, target any) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	bytes, err := io.ReadAll(io.LimitReader(f, maxState+1))
	if err != nil {
		return err
	}
	if len(bytes) > maxState {
		return errors.New("state file exceeds 16 MiB")
	}
	return json.Unmarshal(bytes, target)
}

func atomicJSON(path string, data any) error {
	body, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	if len(body) > maxState {
		return errors.New("state file exceeds 16 MiB")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(path), ".native-state-*.tmp")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if err := f.Chmod(0600); err != nil {
		f.Close()
		return err
	}
	if _, err := f.Write(body); err != nil {
		f.Close()
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(name, path)
}

func loadConfig(root string) (config, error) {
	c := config{}
	err := readJSON(filepath.Join(root, "config.json"), &c)
	if err != nil && !os.IsNotExist(err) {
		return nil, fmt.Errorf("configuration: %w", err)
	}
	if c == nil {
		return nil, errors.New("configuration must be a JSON object")
	}
	return c, nil
}

// Preserve attachment blocks and unknown legacy message fields during resume.
type message map[string]any
type snapshot struct {
	ID        string         `json:"id"`
	Messages  []message      `json:"messages"`
	Metadata  map[string]any `json:"metadata"`
	UpdatedAt string         `json:"updated_at"`
	// Native provider messages retain Gemini function-call thought signatures.
	// Older sessions omit this optional field and remain resumable.
	ProviderContents json.RawMessage `json:"provider_contents,omitempty"`
}

func newID() (string, error) {
	bytes := make([]byte, 16)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}
func sessionPath(root, id string) (string, error) {
	if !validID.MatchString(id) {
		return "", errors.New("invalid session ID")
	}
	return filepath.Join(root, "sessions", id+".json"), nil
}
func saveSession(root string, s snapshot) error {
	path, err := sessionPath(root, s.ID)
	if err != nil {
		return err
	}
	if s.Metadata == nil {
		s.Metadata = map[string]any{}
	}
	if _, ok := s.Metadata["created_at"]; !ok {
		s.Metadata["created_at"] = time.Now().UTC().Format(time.RFC3339Nano)
	}
	if _, ok := s.Metadata["title"]; !ok {
		for _, m := range s.Messages {
			if m["role"] == "user" {
				text, _ := m["content"].(string)
				chars := []rune(text)
				if len(chars) > 60 {
					chars = chars[:60]
				}
				s.Metadata["title"] = string(chars)
				break
			}
		}
	}
	s.UpdatedAt = time.Now().UTC().Format(time.RFC3339Nano)
	if s.Messages == nil {
		s.Messages = []message{}
	}
	return atomicJSON(path, s)
}
func loadSession(root, id string) (snapshot, error) {
	path, err := sessionPath(root, id)
	if err != nil {
		return snapshot{}, err
	}
	var s snapshot
	if err := readJSON(path, &s); err != nil {
		return s, err
	}
	if s.ID != id || s.Messages == nil {
		return s, errors.New("invalid session snapshot")
	}
	for _, m := range s.Messages {
		if m["role"] != "user" && m["role"] != "assistant" && m["role"] != "system" && m["role"] != "tool" && m["role"] != "function" {
			return s, errors.New("invalid message role")
		}
	}
	return s, nil
}
func listSessions(root string, limit int) ([]map[string]any, error) {
	files, err := os.ReadDir(filepath.Join(root, "sessions"))
	if os.IsNotExist(err) {
		return []map[string]any{}, nil
	}
	if err != nil {
		return nil, err
	}
	results := []map[string]any{}
	for _, file := range files {
		if file.IsDir() || !strings.HasSuffix(file.Name(), ".json") {
			continue
		}
		s, err := loadSession(root, strings.TrimSuffix(file.Name(), ".json"))
		if err != nil {
			continue
		}
		results = append(results, map[string]any{"id": s.ID, "title": s.Metadata["title"], "messages": len(s.Messages), "updated": s.UpdatedAt})
	}
	sort.Slice(results, func(i, j int) bool { return fmt.Sprint(results[i]["updated"]) > fmt.Sprint(results[j]["updated"]) })
	if limit > 0 && len(results) > limit {
		results = results[:limit]
	}
	return results, nil
}
