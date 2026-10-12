package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"google.golang.org/genai"
)

func TestCancellationKeepsResultsOfAlreadyExecutedBatchCalls(t *testing.T) {
	project := t.TempDir()
	s, err := newScope(project, nil, nil, false)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(project, "note.txt"), []byte("real evidence"), 0600); err != nil {
		t.Fatal(err)
	}
	p := providerFunc(func(context.Context, []*genai.Content, string, []*genai.Tool, func(string)) (*genai.Content, error) {
		return &genai.Content{Role: "model", Parts: []*genai.Part{call("read_file", map[string]any{"path": "note.txt"}), call("write_file", map[string]any{"path": "never.txt", "content": "declined"})}}, nil
	})
	hooks := quietHooks()
	hooks.approve = func(_ context.Context, name string, _ map[string]any, _ fileChange) (bool, string, error) {
		if name == "write_file" {
			return false, "", context.Canceled
		}
		return true, "", nil
	}
	contents, _, err := nativeTurn(context.Background(), p, s, config{}, nil, "Read then write a file", hooks)
	if !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	settled := settlePending(contents)
	success, interrupted := 0, 0
	for _, message := range settled {
		for _, part := range message.Parts {
			if response := part.FunctionResponse; response != nil {
				if response.Response["success"] == true {
					success++
				} else {
					interrupted++
				}
			}
		}
	}
	if success != 1 || interrupted != 1 {
		t.Fatal("the completed read was lost or the pending write was reported as done", success, interrupted)
	}
}
