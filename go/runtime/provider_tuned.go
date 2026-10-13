package main

// Aria's own models: Gemini tuned on Vertex AI (docs/training-protocol.md).
// A tuned model is served from its own endpoint and called by the endpoint's
// resource name, projects/PROJECT/locations/REGION/endpoints/ID, with
// generateContent in the region the tuning job ran in. The configuration may
// name it directly as the model, or give it a short name:
//
//	"tuned_models": {"aria-v1": "projects/123/locations/us-central1/endpoints/456"},
//	"model": "aria-v1"
//
// Such a model always takes the Vertex SDK route — Chat Completions does not
// document tuned endpoints — with the gcloud login or application-default
// credentials, and the endpoint's own project and region, whatever
// gcp_location or GOOGLE_CLOUD_LOCATION say for the base models.

import (
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"

	"google.golang.org/genai"
)

var tunedEndpointName = regexp.MustCompile(`^projects/([a-z0-9][a-z0-9-]{0,62})/locations/([a-z0-9-]{1,40})/endpoints/([0-9]{1,30})$`)

type tunedModel struct {
	name     string // what the configuration calls it: a short name or the resource name
	resource string // projects/PROJECT/locations/REGION/endpoints/ID
	project  string
	location string
}

// resolveTunedModel is the tuned endpoint the configuration's model names,
// nil when it names a base model, or an error for a short name that does not
// lead to an endpoint.
func resolveTunedModel(c config) (*tunedModel, error) {
	name := strings.TrimSpace(c.text("model", ""))
	resource := name
	aliases, _ := asMapping(c["tuned_models"])
	if target, ok := aliases[name]; ok {
		text, _ := target.(string)
		resource = strings.TrimSpace(text)
		if !tunedEndpointName.MatchString(resource) {
			return nil, fmt.Errorf("tuned_models[%q] must be a Vertex endpoint name: projects/PROJECT/locations/REGION/endpoints/ID", name)
		}
	}
	m := tunedEndpointName.FindStringSubmatch(resource)
	if m == nil {
		if strings.HasPrefix(name, "projects/") {
			return nil, errors.New("a tuned model is named projects/PROJECT/locations/REGION/endpoints/ID")
		}
		return nil, nil
	}
	return &tunedModel{name: name, resource: resource, project: m[1], location: m[2]}, nil
}

// tunedModelNames are the short names the configuration declares, sorted.
func tunedModelNames(c config) []string {
	aliases, _ := asMapping(c["tuned_models"])
	names := make([]string, 0, len(aliases))
	for name := range aliases {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

// forTuned points a Vertex client configuration at the tuned endpoint's
// project and region: the SDK picks the host from the location and uses the
// resource name as the path.
func (t *tunedModel) forTuned(options *genai.ClientConfig) error {
	if options.Backend != genai.BackendVertexAI {
		return errors.New("a tuned model is served by Vertex AI: sign in with gcloud or set application-default credentials")
	}
	options.Project, options.Location = t.project, t.location
	return nil
}
