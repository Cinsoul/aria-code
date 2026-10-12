package main

import (
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"

	"google.golang.org/genai"
)

type disconnectWriter struct{ writes int }

func (w *disconnectWriter) Write(body []byte) (int, error) {
	w.writes++
	if w.writes == 1 {
		return len(body), nil
	}
	return 0, io.ErrClosedPipe
}
func TestBrokenFrontendOutputStopsTheWorkerAndPreventsAWrite(t *testing.T) {
	project := t.TempDir()
	s, err := newServer(appOptions{root: t.TempDir(), workspace: project}, &disconnectWriter{})
	if err != nil {
		t.Fatal(err)
	}
	s.provider = providerFunc(func(ctx context.Context, _ []*genai.Content, _ string, _ []*genai.Tool, emit func(string)) (*genai.Content, error) {
		emit("Beginning")
		return &genai.Content{Role: "model", Parts: []*genai.Part{call("write_file", map[string]any{"path": "must-not-write.txt", "content": "unreviewed"})}}, nil
	})
	in, out := io.Pipe()
	defer in.Close()
	defer out.Close()
	done := make(chan error, 1)
	go func() { done <- s.run(context.Background(), in) }()
	_, err = io.WriteString(out, "\n{\"protocol\":1,\"type\":\"turn.submit\",\"turn_id\":\"test\",\"text\":\"write a file\"}\n")
	if err != nil && !errors.Is(err, io.ErrClosedPipe) {
		t.Fatal(err)
	}
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("worker kept waiting after its frontend disconnected")
	}
	if _, err := os.Stat(filepath.Join(project, "must-not-write.txt")); !os.IsNotExist(err) {
		t.Fatal("worker wrote after disconnect")
	}
}
func TestIdleWorkerStopsOnContextCancellation(t *testing.T) {
	s, err := newServer(appOptions{root: t.TempDir(), workspace: t.TempDir()}, io.Discard)
	if err != nil {
		t.Fatal(err)
	}
	in, out := io.Pipe()
	defer in.Close()
	defer out.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- s.run(ctx, in) }()
	if _, err := io.WriteString(out, "\n"); err != nil {
		t.Fatal(err)
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("idle scanner ignored cancellation")
	}
}
