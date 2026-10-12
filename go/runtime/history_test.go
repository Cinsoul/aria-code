package main

import (
	"encoding/json"
	"io"
	"path/filepath"
	"strings"
	"testing"
)

func TestLegacySignedCallsResultsAndAttachmentsSurviveResume(t *testing.T) {
	messages := []message{
		{"role": "user", "content": []any{map[string]any{"type": "text", "text": "read this image"}, map[string]any{"type": "image_url", "image_url": map[string]any{"url": "data:image/png;base64,aW1hZ2U="}}}, "custom": "preserve"},
		{"role": "assistant", "content": nil, "tool_calls": []any{map[string]any{"id": "saved-call", "function": map[string]any{"name": "read_file", "arguments": "{\"path\":\"note.txt\"}"}, "extra_content": map[string]any{"google": map[string]any{"thought_signature": "c2lnbmVk"}}}}},
		{"role": "tool", "name": "read_file", "content": "{\"success\":true}"},
	}
	contents, err := legacyContents(messages)
	if err != nil || len(contents) != 3 {
		t.Fatal(err, len(contents))
	}
	if contents[0].Parts[1].InlineData.MIMEType != "image/png" || string(contents[0].Parts[1].InlineData.Data) != "image" {
		t.Fatal("image lost")
	}
	if string(contents[1].Parts[0].ThoughtSignature) != "signed" || contents[2].Parts[0].FunctionResponse.ID != "saved-call" {
		t.Fatal("signature or result identity lost")
	}
	root := t.TempDir()
	if err := saveSession(root, snapshot{ID: "saved", Messages: messages}); err != nil {
		t.Fatal(err)
	}
	s, err := newServer(appOptions{root: root, workspace: t.TempDir(), resume: "saved"}, io.Discard)
	if err != nil || s.snap.Messages[0]["custom"] != "preserve" {
		t.Fatal("opaque saved field lost", err)
	}
}

func TestInvalidAttachmentResumeLeavesPriorSnapshotUntouched(t *testing.T) {
	root := t.TempDir()
	s := snapshot{ID: "saved", Messages: []message{{"role": "user", "content": []any{map[string]any{"type": "unknown"}}}}}
	if err := saveSession(root, s); err != nil {
		t.Fatal(err)
	}
	if _, err := newServer(appOptions{root: root, workspace: t.TempDir(), resume: "saved"}, io.Discard); err == nil {
		t.Fatal("unknown attachment discarded")
	}
	saved, err := loadSession(root, "saved")
	if err != nil || saved.Messages[0]["content"].([]any)[0].(map[string]any)["type"] != "unknown" {
		t.Fatal("original session changed", err)
	}
	if _, err := sessionContents(snapshot{ProviderContents: json.RawMessage(`[null]`)}); err == nil {
		t.Fatal("corrupt native history accepted")
	}
}

func TestDisplayHistoryIsBoundedWithoutTruncatingSavedConversation(t *testing.T) {
	messages := []message{}
	for i := 0; i < 80; i++ {
		messages = append(messages, message{"role": "user", "content": strings.Repeat("你", 5000)})
	}
	visible := displayMessages(messages)
	if len(visible) != 40 || len([]rune(visible[0]["content"].(string))) > 4200 {
		t.Fatal("display snapshot unbounded")
	}
	if len(messages) != 80 || len([]rune(messages[0]["content"].(string))) != 5000 {
		t.Fatal("persisted history was truncated")
	}
}

func TestResumeLastTracksTheSelectedSessionAndKeepsOtherConfiguration(t *testing.T) {
	root, project := t.TempDir(), t.TempDir()
	if err := atomicJSON(filepath.Join(root, "config.json"), config{"gcp_project": "keep-project", "ui_theme": "light"}); err != nil {
		t.Fatal(err)
	}
	s, err := newServer(appOptions{root: root, workspace: project}, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	first := s.snap.ID
	if err := s.switchSession(""); err != nil {
		t.Fatal(err)
	}
	if err := s.switchSession(first); err != nil {
		t.Fatal(err)
	}
	resumed, err := newServer(appOptions{root: root, workspace: project, resumeLast: true}, io.Discard)
	if err != nil || resumed.snap.ID != first {
		t.Fatal("last session is stale", err)
	}
	cfg, err := loadConfig(root)
	if err != nil || cfg["gcp_project"] != "keep-project" || cfg["ui_theme"] != "light" {
		t.Fatal("unrelated configuration changed", err)
	}
}
