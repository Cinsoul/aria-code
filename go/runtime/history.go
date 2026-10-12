package main

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"google.golang.org/genai"
)

// Translate saved Python/OpenAI/Anthropic messages without changing the
// original snapshot. Unsupported blocks fail resume instead of disappearing.
func legacyContents(messages []message) ([]*genai.Content, error) {
	contents := []*genai.Content{}
	var pending []*genai.FunctionCall
	for _, m := range messages {
		role, _ := m["role"].(string)
		if role == "tool" || role == "function" {
			id, _ := m["tool_call_id"].(string)
			name, _ := m["name"].(string)
			match := -1
			for i, call := range pending {
				if (id != "" && call.ID == id) || (id == "" && (name == "" || call.Name == name)) {
					match = i
					break
				}
			}
			value := m["content"]
			var response map[string]any
			if text, ok := value.(string); ok {
				if json.Unmarshal([]byte(text), &response) != nil || response == nil {
					response = map[string]any{"output": text}
				}
			} else if result, ok := value.(map[string]any); ok {
				response = result
			} else {
				return nil, errors.New("invalid legacy tool result")
			}
			if match >= 0 {
				call := pending[match]
				pending = append(pending[:match], pending[match+1:]...)
				contents = append(contents, &genai.Content{Role: "user", Parts: []*genai.Part{{FunctionResponse: &genai.FunctionResponse{ID: call.ID, Name: call.Name, Response: response}}}})
			} else {
				body, _ := json.Marshal(response)
				contents = append(contents, genai.NewContentFromText("Result of "+name+":\n"+string(body), genai.RoleUser))
			}
			continue
		}
		// A legacy conversation can interrupt a batch before every result was
		// saved. Answer it before the next ordinary message, preserving order.
		if len(pending) > 0 {
			parts := []*genai.Part{}
			for _, call := range pending {
				parts = append(parts, &genai.Part{FunctionResponse: &genai.FunctionResponse{ID: call.ID, Name: call.Name, Response: map[string]any{"success": false, "error": "operation was not executed or was interrupted"}}})
			}
			contents = append(contents, &genai.Content{Role: "user", Parts: parts})
			pending = nil
		}
		parts, err := attachmentParts(m["content"])
		if err != nil {
			return nil, err
		}
		calls, ok := m["tool_calls"].([]any)
		if m["tool_calls"] != nil && !ok {
			return nil, errors.New("invalid saved tool calls")
		}
		for _, raw := range calls {
			value, ok := raw.(map[string]any)
			if !ok {
				return nil, errors.New("invalid saved tool call")
			}
			function, ok := value["function"].(map[string]any)
			if !ok {
				return nil, errors.New("invalid saved tool function")
			}
			name, _ := function["name"].(string)
			id, _ := value["id"].(string)
			if name == "" {
				return nil, errors.New("saved tool call has no name")
			}
			if id == "" {
				generated, err := newID()
				if err != nil {
					return nil, err
				}
				id = "native_" + generated
			}
			args := map[string]any{}
			if body, ok := function["arguments"].(string); ok {
				if json.Unmarshal([]byte(body), &args) != nil || args == nil {
					return nil, errors.New("invalid saved tool arguments")
				}
			} else if value, ok := function["arguments"].(map[string]any); ok {
				args = value
			} else {
				return nil, errors.New("invalid saved tool arguments")
			}
			call := &genai.FunctionCall{ID: id, Name: name, Args: args}
			part := &genai.Part{FunctionCall: call}
			if extra, ok := value["extra_content"].(map[string]any); ok {
				if google, ok := extra["google"].(map[string]any); ok {
					if signature, ok := google["thought_signature"].(string); ok {
						decoded, err := base64.StdEncoding.DecodeString(signature)
						if err != nil {
							return nil, errors.New("invalid saved tool signature")
						}
						part.ThoughtSignature = decoded
					}
				}
			}
			parts = append(parts, part)
			pending = append(pending, call)
		}
		if len(parts) > 0 {
			nativeRole := "user"
			if role == "assistant" {
				nativeRole = "model"
			}
			if role == "system" {
				parts = append([]*genai.Part{{Text: "Saved session instruction:\n"}}, parts...)
			}
			contents = append(contents, &genai.Content{Role: nativeRole, Parts: parts})
		}
	}
	return settlePending(contents), nil
}

func attachmentParts(value any) ([]*genai.Part, error) {
	if value == nil {
		return nil, nil
	}
	if text, ok := value.(string); ok {
		if text == "" {
			return nil, nil
		}
		return []*genai.Part{{Text: text}}, nil
	}
	blocks, ok := value.([]any)
	if !ok {
		return nil, errors.New("saved message content must be text or attachment blocks")
	}
	parts := []*genai.Part{}
	for _, raw := range blocks {
		block, ok := raw.(map[string]any)
		if !ok {
			return nil, errors.New("invalid saved attachment block")
		}
		kind, _ := block["type"].(string)
		switch kind {
		case "text", "input_text":
			text, ok := block["text"].(string)
			if !ok {
				return nil, errors.New("saved text block is invalid")
			}
			parts = append(parts, &genai.Part{Text: text})
		case "image_url", "input_image":
			uri, _ := block["image_url"].(string)
			if object, ok := block["image_url"].(map[string]any); ok {
				uri, _ = object["url"].(string)
			}
			if uri == "" {
				return nil, errors.New("saved image has no URL")
			}
			if strings.HasPrefix(uri, "data:") {
				mime, data, ok := strings.Cut(strings.TrimPrefix(uri, "data:"), ";base64,")
				if !ok {
					return nil, errors.New("image data URL must use base64")
				}
				part, err := inlinePart(mime, data)
				if err != nil {
					return nil, err
				}
				parts = append(parts, part)
			} else if strings.HasPrefix(uri, "https://") || strings.HasPrefix(uri, "gs://") {
				parts = append(parts, &genai.Part{FileData: &genai.FileData{FileURI: uri, MIMEType: "image/jpeg"}})
			} else {
				return nil, errors.New("unsupported saved image URL")
			}
		case "image", "document":
			source, ok := block["source"].(map[string]any)
			if !ok || source["type"] != "base64" {
				return nil, errors.New("unsupported saved attachment source")
			}
			mime, _ := source["media_type"].(string)
			data, _ := source["data"].(string)
			part, err := inlinePart(mime, data)
			if err != nil {
				return nil, err
			}
			parts = append(parts, part)
		default:
			return nil, fmt.Errorf("unsupported saved attachment block: %s", kind)
		}
	}
	return parts, nil
}
func inlinePart(mime, data string) (*genai.Part, error) {
	if mime == "" || len(data) > 12<<20 {
		return nil, errors.New("attachment MIME type missing or data exceeds limit")
	}
	decoded, err := base64.StdEncoding.DecodeString(data)
	if err != nil || len(decoded) > 8<<20 {
		return nil, errors.New("invalid attachment base64 data or attachment exceeds 8 MiB")
	}
	return &genai.Part{InlineData: &genai.Blob{MIMEType: mime, Data: decoded}}, nil
}
func sessionContents(s snapshot) ([]*genai.Content, error) {
	if len(s.ProviderContents) == 0 {
		return legacyContents(s.Messages)
	}
	var contents []*genai.Content
	if err := json.Unmarshal(s.ProviderContents, &contents); err != nil {
		return nil, errors.New("invalid native provider history")
	}
	for _, content := range contents {
		if content == nil || (content.Role != "user" && content.Role != "model") {
			return nil, errors.New("invalid provider content role")
		}
		for _, part := range content.Parts {
			if part == nil {
				return nil, errors.New("invalid nil provider part")
			}
		}
	}
	return settlePending(contents), nil
}

func displayMessages(messages []message) []message {
	if len(messages) > 40 {
		messages = messages[len(messages)-40:]
	}
	visible := make([]message, 0, len(messages))
	for _, m := range messages {
		text, ok := m["content"].(string)
		if !ok {
			var lines []string
			if blocks, ok := m["content"].([]any); ok {
				for _, raw := range blocks {
					if block, ok := raw.(map[string]any); ok {
						if value, ok := block["text"].(string); ok {
							lines = append(lines, value)
						} else {
							lines = append(lines, "[attachment]")
						}
					}
				}
			}
			text = strings.Join(lines, "\n")
		}
		visible = append(visible, message{"role": m["role"], "content": capText(text, 4096)})
	}
	return visible
}
