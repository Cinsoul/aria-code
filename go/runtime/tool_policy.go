package main

import (
	"fmt"
	"os"
	"path/filepath"
)

// Denials always win, including over explicit invocation grants. Read the
// current policy for every operation so another terminal's changes take effect.
func persistentToolPolicy(root, name string) (string, error) {
	policy := struct {
		Allowed, Denied []string
		AskAlways       []string `json:"ask_always"`
	}{}
	if err := readJSON(filepath.Join(root, "tool_policy.json"), &policy); err != nil && !os.IsNotExist(err) {
		return "", fmt.Errorf("tool policy: %w", err)
	}
	for _, group := range []struct {
		values  []string
		verdict string
	}{
		{policy.Denied, "deny"}, {policy.AskAlways, "ask"}, {policy.Allowed, "allow"},
	} {
		for _, tool := range group.values {
			if tool == name {
				return group.verdict, nil
			}
		}
	}
	return "default", nil
}
