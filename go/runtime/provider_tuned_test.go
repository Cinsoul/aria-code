package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"cloud.google.com/go/auth"
	"google.golang.org/genai"
)

type staticToken struct{}

func (staticToken) Token(context.Context) (*auth.Token, error) {
	return &auth.Token{Value: "fixture-token", Type: "Bearer"}, nil
}

const ariaEndpoint = "projects/123456789012/locations/us-central1/endpoints/987654321"

func TestTunedModelsAreNamedOrAliased(t *testing.T) {
	aliases := map[string]any{"aria-v1": ariaEndpoint, "broken": "gemini-3.5-flash"}
	for _, tc := range []struct {
		model, resource, location, err string
	}{
		{"aria-v1", ariaEndpoint, "us-central1", ""},
		{ariaEndpoint, ariaEndpoint, "us-central1", ""},
		{"projects/p-1/locations/us/endpoints/42", "projects/p-1/locations/us/endpoints/42", "us", ""},
		{"gemini-3.5-flash", "", "", ""},
		{"broken", "", "", "must be a Vertex endpoint name"},
		{"projects/x/locations/y/models/z", "", "", "projects/PROJECT/locations/REGION/endpoints/ID"},
		{"projects/../locations/us/endpoints/1", "", "", "projects/PROJECT"},
	} {
		got, err := resolveTunedModel(config{"model": tc.model, "tuned_models": aliases})
		switch {
		case tc.err != "":
			if err == nil || !strings.Contains(err.Error(), tc.err) {
				t.Errorf("%s: %v", tc.model, err)
			}
		case tc.resource == "":
			if got != nil || err != nil {
				t.Errorf("%s is a base model: %v %v", tc.model, got, err)
			}
		default:
			if err != nil || got.resource != tc.resource || got.location != tc.location || got.name != tc.model {
				t.Errorf("%s: %+v %v", tc.model, got, err)
			}
		}
	}
}

func TestTunedModelsTakeTheVertexSDKRoute(t *testing.T) {
	t.Setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
	t.Setenv("CLOUDSDK_CONFIG", t.TempDir()) // a gcloud login without application-default credentials
	writeProviders(t, map[string]any{})
	provider, err := modelProviderFor(config{"model": "aria-v1", "tuned_models": map[string]any{"aria-v1": ariaEndpoint}})
	if err != nil {
		t.Fatal(err)
	}
	google, ok := provider.(*googleProvider)
	if !ok || google.tuned == nil || google.model != ariaEndpoint {
		t.Fatalf("Chat Completions does not document tuned endpoints: %T", provider)
	}
	if err := google.tuned.forTuned(&genai.ClientConfig{Backend: genai.BackendGeminiAPI}); err == nil {
		t.Fatal("a Gemini API key cannot reach a Vertex endpoint")
	}
}

func TestTunedEndpointsUseTheirOwnRegion(t *testing.T) {
	creds := auth.NewCredentials(&auth.CredentialsOptions{TokenProvider: staticToken{}})
	for resource, host := range map[string]string{
		ariaEndpoint:                                    "https://us-central1-aiplatform.googleapis.com/",
		"projects/p/locations/us/endpoints/1":           "https://aiplatform.us.rep.googleapis.com/",
		"projects/p/locations/europe-west4/endpoints/2": "https://europe-west4-aiplatform.googleapis.com/",
	} {
		tuned, err := resolveTunedModel(config{"model": resource})
		if err != nil {
			t.Fatal(err)
		}
		// Configured for the base models in another region.
		options := &genai.ClientConfig{Backend: genai.BackendVertexAI, Project: "base-project", Location: "global", Credentials: creds}
		if err := tuned.forTuned(options); err != nil {
			t.Fatal(err)
		}
		client, err := genai.NewClient(context.Background(), options)
		if err != nil {
			t.Fatal(err)
		}
		if got := client.ClientConfig().HTTPOptions.BaseURL; got != host {
			t.Errorf("%s: %s", resource, got)
		}
	}
}

func TestTunedModelRequestsGoToTheEndpoint(t *testing.T) {
	var path, authorization string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path, authorization = r.URL.Path, r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "data: {\"candidates\":[{\"content\":{\"parts\":[{\"text\":\"Aria here.\"}]},\"finishReason\":\"STOP\"}]}\n\n")
	}))
	defer server.Close()
	tuned, _ := resolveTunedModel(config{"model": ariaEndpoint})
	options := &genai.ClientConfig{Backend: genai.BackendVertexAI, Credentials: auth.NewCredentials(&auth.CredentialsOptions{TokenProvider: staticToken{}}),
		HTTPOptions: genai.HTTPOptions{BaseURL: server.URL}}
	if err := tuned.forTuned(options); err != nil {
		t.Fatal(err)
	}
	client, err := genai.NewClient(context.Background(), options)
	if err != nil {
		t.Fatal(err)
	}
	p := &googleProvider{cfg: config{}, model: tuned.resource, tuned: tuned, client: client}
	var text strings.Builder
	if _, err := p.Generate(context.Background(), []*genai.Content{genai.NewContentFromText("hi", genai.RoleUser)}, "system", nil, func(s string) { text.WriteString(s) }); err != nil {
		t.Fatal(err)
	}
	if path != "/v1beta1/"+ariaEndpoint+":streamGenerateContent" && path != "/v1/"+ariaEndpoint+":streamGenerateContent" {
		t.Fatal(path)
	}
	if text.String() != "Aria here." || authorization != "Bearer fixture-token" {
		t.Fatal(text.String(), authorization)
	}
}

func TestModelCommandAcceptsTunedModels(t *testing.T) {
	writeProviders(t, map[string]any{})
	s := approvalServer(t, config{"tuned_models": map[string]any{"aria-v1": ariaEndpoint}}, appOptions{})
	ctx := context.Background()
	listing, err := s.command(ctx, "turn", "/model")
	if err != nil || !strings.Contains(listing, "Tuned models: aria-v1") {
		t.Fatal(listing, err)
	}
	for _, model := range []string{"aria-v1", ariaEndpoint} {
		if got, err := s.command(ctx, "turn", "/model "+model); err != nil || got != "Model: "+model {
			t.Fatal(got, err)
		}
		if google, ok := s.provider.(*googleProvider); !ok || google.tuned == nil {
			t.Fatalf("%s: %T", model, s.provider)
		}
	}
	if _, err := s.command(ctx, "turn", "/model aria-v9"); err == nil {
		t.Fatal("an unknown short name is refused")
	}
}
