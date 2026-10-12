package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	"google.golang.org/genai"
)

func TestGoogleBackendSelectionKeepsExplicitSettingsAndEnvironment(t *testing.T) {
	for _, key := range []string{"GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_CLOUD_LOCATION"} {
		t.Setenv(key, "")
	}
	if c := googleClientConfig(config{"api_key": "test-key"}); c.Backend != genai.BackendGeminiAPI || c.APIKey != "test-key" {
		t.Fatal(c.Backend)
	}
	if c := googleClientConfig(config{"gcp_project": "existing-project"}); c.Backend != genai.BackendVertexAI || c.Project != "existing-project" || c.Location != "global" {
		t.Fatal(c.Backend, c.Project, c.Location)
	}
	t.Setenv("GOOGLE_CLOUD_PROJECT", "environment-project")
	t.Setenv("GOOGLE_CLOUD_LOCATION", "europe-west2")
	if c := googleClientConfig(config{"gcp_project": "old", "gcp_location": "old"}); c.Project != "environment-project" || c.Location != "europe-west2" {
		t.Fatal(c.Project, c.Location)
	}
	if c := googleClientConfig(config{"use_vertexai": false, "api_key": "test-key"}); c.Backend != genai.BackendGeminiAPI {
		t.Fatal(c.Backend)
	}
}
func TestGoogleStreamingKeepsFunctionSignatureAndHidesThoughts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, ":streamGenerateContent") {
			t.Error(r.URL.Path)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "data: {\"candidates\":[{\"content\":{\"parts\":[{\"text\":\"private reasoning\",\"thought\":true}]}}]}\n\n")
		fmt.Fprint(w, "data: {\"candidates\":[{\"content\":{\"parts\":[{\"text\":\"你好\"},{\"functionCall\":{\"name\":\"read_file\",\"args\":{\"path\":\"note.txt\"}},\"thoughtSignature\":\"c2lnbmVkLWNhbGw=\"}]},\"finishReason\":\"STOP\"}]}\n\n")
	}))
	defer server.Close()
	client, err := genai.NewClient(context.Background(), &genai.ClientConfig{Backend: genai.BackendGeminiAPI, APIKey: "fixture", HTTPOptions: genai.HTTPOptions{BaseURL: server.URL}})
	if err != nil {
		t.Fatal(err)
	}
	p := &googleProvider{cfg: config{}, model: "gemini-test", client: client}
	var text strings.Builder
	content, err := p.Generate(context.Background(), []*genai.Content{genai.NewContentFromText("read note", genai.RoleUser)}, "Test", nil, func(s string) { text.WriteString(s) })
	if err != nil || text.String() != "你好" {
		t.Fatal(text.String(), err)
	}
	if len(content.Parts) != 2 || content.Parts[1].FunctionCall.Name != "read_file" || !reflect.DeepEqual(content.Parts[1].ThoughtSignature, []byte("signed-call")) {
		t.Fatal(content)
	}
	if content.Parts[0].Text != "你好" {
		t.Fatal("unsigned hidden prose became an empty history part")
	}
}
func TestGoogleErrorsNeverReturnConfiguredKeys(t *testing.T) {
	p := &googleProvider{cfg: config{"api_key": "fixture-secret-key"}}
	if text := p.safeError(fmt.Errorf("request rejected: fixture-secret-key")).Error(); strings.Contains(text, "fixture-secret-key") {
		t.Fatal(text)
	}
}

func TestGoogleIncompleteOrBlockedFinishCannotExecuteToolCalls(t *testing.T) {
	for _, finish := range []string{"MAX_TOKENS", "SAFETY", ""} {
		t.Run("finish_"+finish, func(t *testing.T) {
			requests := 0
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				requests++
				w.Header().Set("Content-Type", "text/event-stream")
				fmt.Fprintf(w, "data: {\"candidates\":[{\"content\":{\"parts\":[{\"functionCall\":{\"name\":\"write_file\",\"args\":{\"path\":\"note.txt\",\"content\":\"partial proposal\"}}}]},\"finishReason\":%q}]}\n\n", finish)
			}))
			defer server.Close()
			client, err := genai.NewClient(context.Background(), &genai.ClientConfig{Backend: genai.BackendGeminiAPI, APIKey: "fixture", HTTPOptions: genai.HTTPOptions{BaseURL: server.URL}})
			if err != nil {
				t.Fatal(err)
			}
			p := &googleProvider{cfg: config{}, model: "gemini-test", client: client}
			if _, err := p.Generate(context.Background(), nil, "Test", nativeTools(), func(string) {}); err == nil || requests != 1 {
				t.Fatal(requests, err)
			}
		})
	}
}

func TestGoogleSignedPartsSurvivePrivateHistoryButNeverDisplay(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "data: {\"candidates\":[{\"content\":{\"parts\":[{\"text\":\"opaque signed payload\",\"thought\":true,\"thoughtSignature\":\"c2lnbmVk\"},{\"text\":\"visible response\"}]},\"finishReason\":\"STOP\"}]}\n\n")
	}))
	defer server.Close()
	client, err := genai.NewClient(context.Background(), &genai.ClientConfig{Backend: genai.BackendGeminiAPI, APIKey: "fixture", HTTPOptions: genai.HTTPOptions{BaseURL: server.URL}})
	if err != nil {
		t.Fatal(err)
	}
	p := &googleProvider{cfg: config{}, model: "gemini-test", client: client}
	var visible strings.Builder
	content, err := p.Generate(context.Background(), nil, "Test", nil, func(text string) { visible.WriteString(text) })
	if err != nil || visible.String() != "visible response" || content.Parts[0].Text != "opaque signed payload" || string(content.Parts[0].ThoughtSignature) != "signed" {
		t.Fatal(content, visible.String(), err)
	}
}
