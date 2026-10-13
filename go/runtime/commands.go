package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
)

func nativeCommands() []string {
	return []string{"/help", "/model", "/config", "/health", "/sessions", "/new", "/resume", "/permissions"}
}
func (s *server) command(ctx context.Context, turn, text string) (string, error) {
	fields := strings.Fields(text)
	if len(fields) == 0 {
		return "", nil
	}
	switch fields[0] {
	case "/help":
		return "Aria native interface\n\nEnter sends · Ctrl+J / Alt+Enter adds a line\nEsc cancels · Ctrl+O shows operation details · F1 opens help\n\n" + strings.Join(nativeCommands(), " · "), nil
	case "/sessions":
		sessions, err := listSessions(s.opts.root, 20)
		if err != nil {
			return "", err
		}
		body, err := json.MarshalIndent(sessions, "", "  ")
		return string(body), err
	case "/permissions":
		body, err := json.MarshalIndent(map[string]any{"read_roots": s.scope.readRoots, "write_roots": s.scope.writeRoots, "session_grants": s.grants, "skip_default_prompts": s.opts.skipPermissions}, "", "  ")
		return string(body), err
	case "/new", "/resume":
		return "Use the frontend session command to start or resume a session.", nil
	case "/health":
		if p, ok := s.provider.(*openAIProvider); ok {
			if _, _, err := p.connection(ctx); err != nil {
				return "", err
			}
			return "Google Cloud Chat Completions configured. A generation request is required to verify model availability.", nil
		}
		p, ok := s.provider.(*googleProvider)
		if !ok {
			return "Provider test adapter configured.", nil
		}
		if _, err := p.getClient(ctx); err != nil {
			return "", err
		}
		return "Google credentials configured. Network and model availability are verified by a model request; no generation was performed by this check.", nil
	case "/model":
		if len(fields) == 1 {
			return fmt.Sprintf("google / %s\nUse /model <Google model name>.", s.cfg.text("model", "gemini-3.5-flash")), nil
		}
		if len(fields) != 2 {
			return "", errors.New("usage: /model <model name>")
		}
		model := strings.TrimPrefix(fields[1], "google/")
		if !strings.HasPrefix(model, "gemini-") {
			return "", errors.New("unknown Google model name")
		}
		if err := s.saveSetting("model", model); err != nil {
			return "", err
		}
		s.cfg["model"] = model
		s.provider = googleModelProvider(s.cfg)
		return "Model: " + model, nil
	case "/config":
		if len(fields) == 1 {
			return fmt.Sprintf("ui_lang=%s\nmodel=%s\nui_theme=%s", s.cfg.text("ui_lang", "en"), s.cfg.text("model", "gemini-3.5-flash"), s.cfg.text("ui_theme", "dark")), nil
		}
		if len(fields) != 3 || fields[1] != "set" {
			return "", errors.New("usage: /config set key=value")
		}
		key, value, ok := strings.Cut(fields[2], "=")
		if !ok {
			return "", errors.New("setting requires key=value")
		}
		switch key {
		case "ui_lang":
			if value != "zh" && value != "en" {
				return "", errors.New("ui_lang must be zh or en")
			}
		case "ui_theme":
			if value != "dark" && value != "light" {
				return "", errors.New("ui_theme must be dark or light")
			}
		default:
			return "", errors.New("unknown native display setting")
		}
		if err := s.saveSetting(key, value); err != nil {
			return "", err
		}
		s.cfg[key] = value
		return key + "=" + value, nil
	default:
		return "", fmt.Errorf("unknown command: %s; use /help", fields[0])
	}
}
func (s *server) saveSetting(key string, value any) error {
	// Read the latest file so another terminal's unrelated settings survive.
	cfg, err := loadConfig(s.opts.root)
	if err != nil {
		return err
	}
	cfg[key] = value
	return atomicJSON(filepath.Join(s.opts.root, "config.json"), cfg)
}
