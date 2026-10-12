package main

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func bridgeRequest(name string, args map[string]any) []byte {
	body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": "请求-1", "method": "tools.call", "params": map[string]any{"name": name, "arguments": args}})
	return body
}
func TestNativeBridgeProtocolAndExactIDs(t *testing.T) {
	root, workspace := t.TempDir(), t.TempDir()
	for _, c := range []struct {
		raw  string
		code int
	}{
		{"null", -32600}, {"[]", -32600}, {"true", -32600}, {"{bad", -32700}, {"[{bad", -32700},
		{`{"jsonrpc":"1.0","method":"tools.call","id":1}`, -32600},
		{`{"jsonrpc":"2.0","method":"tools.call","id":true}`, -32600},
		{`{"jsonrpc":"2.0","method":"tools.call","id":1.5}`, -32600},
		{`{"jsonrpc":"2.0","method":"unknown","id":1}`, -32601},
		{`{"jsonrpc":"2.0","method":"tools.call","id":null,"params":[]}`, -32602},
		{`{"jsonrpc":"2.0","method":"tools.call","id":1} {}`, -32700},
	} {
		response := bridgeDispatch(context.Background(), []byte(c.raw), workspace, root, "")
		if response["error"].(map[string]any)["code"] != c.code {
			t.Fatalf("%s: %v", c.raw, response)
		}
	}
	if err := os.WriteFile(filepath.Join(workspace, "note.txt"), []byte("你好\n"), 0644); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{`null`, `"request-你好"`, `123456789012345678901234567890`} {
		raw := `{"jsonrpc":"2.0","method":"tools.call","id":` + id + `,"params":{"name":"read_file","arguments":{"path":"note.txt"}}}`
		response := bridgeDispatch(context.Background(), []byte(raw), workspace, root, "")
		if !response["result"].(toolResult).Success {
			t.Fatal(response)
		}
		got, _ := json.Marshal(response["id"])
		if string(got) != id {
			t.Fatal("request ID changed", string(got), id)
		}
	}
}
func TestNativeBridgeNotificationsAndHostGrantCannotEscapeWorkspace(t *testing.T) {
	root, base := t.TempDir(), t.TempDir()
	workspace := filepath.Join(base, "project")
	if err := os.Mkdir(workspace, 0755); err != nil {
		t.Fatal(err)
	}
	note := filepath.Join(base, "private.txt")
	if err := os.WriteFile(note, []byte("private evidence"), 0644); err != nil {
		t.Fatal(err)
	}
	notification := map[string]any{}
	json.Unmarshal(bridgeRequest("write_file", map[string]any{"path": "new.txt", "content": "complete new file"}), &notification)
	delete(notification, "id")
	raw, _ := json.Marshal(notification)
	if response := bridgeDispatch(context.Background(), raw, workspace, root, "write_file"); response != nil {
		t.Fatal(response)
	}
	if _, err := os.Stat(filepath.Join(workspace, "new.txt")); !os.IsNotExist(err) {
		t.Fatal(err)
	}
	for _, c := range []struct {
		name, approved string
		args           map[string]any
	}{
		{"read_file", "", map[string]any{"path": "../private.txt"}},
		{"write_file", "write_file", map[string]any{"path": "../private.txt", "content": "overwrite"}},
		{"write_file", "", map[string]any{"path": "new.txt", "content": "forged", "approved": true}},
		{"read_file", "", map[string]any{"path": "../private.txt", "_allowed_read_roots": []string{base}}},
		{"run_command", "", map[string]any{"command": "echo should not execute"}},
	} {
		result := bridgeTool(context.Background(), workspace, root, c.approved, c.name, c.args)
		if result.Success || result.Error == "" {
			t.Fatal(result)
		}
	}
	body, _ := os.ReadFile(note)
	if string(body) != "private evidence" {
		t.Fatal(string(body))
	}
	if err := os.Symlink(note, filepath.Join(workspace, "link.txt")); err == nil {
		if result := bridgeTool(context.Background(), workspace, root, "write_file", "write_file", map[string]any{"path": "link.txt", "content": "overwrite"}); result.Success {
			t.Fatal(result)
		}
	}
}
func TestNativeBridgeExplicitWriteAndPersistentPolicy(t *testing.T) {
	root, workspace := t.TempDir(), t.TempDir()
	policy := filepath.Join(root, "tool_policy.json")
	args := map[string]any{"path": "note.txt", "content": "complete native file\r\n"}
	if result := bridgeTool(context.Background(), workspace, root, "edit_file", "write_file", args); result.Success {
		t.Fatal(result)
	}
	atomicJSON(policy, map[string]any{"denied": []string{"write_file"}, "allowed": []string{"write_file"}})
	if result := bridgeTool(context.Background(), workspace, root, "write_file", "write_file", args); result.Success {
		t.Fatal(result)
	}
	atomicJSON(policy, map[string]any{"ask_always": []string{"write_file", "read_file"}})
	if result := bridgeTool(context.Background(), workspace, root, "write_file", "write_file", args); !result.Success {
		t.Fatal(result)
	}
	if result := bridgeTool(context.Background(), workspace, root, "", "read_file", map[string]any{"path": "note.txt"}); result.Success {
		t.Fatal(result)
	}
	atomicJSON(policy, map[string]any{})
	result := bridgeTool(context.Background(), workspace, root, "edit_file", "edit_file", map[string]any{"path": "note.txt", "old_string": "native", "new_string": "verified"})
	if !result.Success {
		t.Fatal(result)
	}
	body, _ := os.ReadFile(filepath.Join(workspace, "note.txt"))
	if string(body) != "complete verified file\r\n" {
		t.Fatal(string(body))
	}
}
func TestNativeBridgeFrameBoundsAndNotificationOutput(t *testing.T) {
	t.Setenv("ARIA_HOME", t.TempDir())
	workspace := t.TempDir()
	for _, raw := range []string{"\n{bad\n", "\n" + strings.Repeat("x", maxMessage+1)} {
		var out, diagnostics bytes.Buffer
		if code := bridgeCommand(context.Background(), []string{"--workspace", workspace}, strings.NewReader(raw), &out, &diagnostics); code != 0 {
			t.Fatal(code, diagnostics.String())
		}
		var response map[string]any
		if err := json.Unmarshal(out.Bytes(), &response); err != nil {
			t.Fatal(err)
		}
		if response["error"] == nil {
			t.Fatal(response)
		}
	}
	var out, diagnostics bytes.Buffer
	if code := bridgeCommand(context.Background(), []string{"--workspace", workspace}, strings.NewReader("\n{\"jsonrpc\":\"2.0\",\"method\":\"unknown\"}\n"), &out, &diagnostics); code != 0 || out.Len() != 0 {
		t.Fatal(code, out.String())
	}
	if code := bridgeCommand(context.Background(), []string{"--workspace", workspace}, strings.NewReader("{bad\n"), &out, &diagnostics); code != 2 {
		t.Fatal("missing containment barrier", code)
	}
}
