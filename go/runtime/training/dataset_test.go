package training

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestTrainingJSONMatchesUnicodeSpacingAndDecimalTypes(t *testing.T) {
	text, err := pythonJSON([]byte(`{"text":"中文😀\\u2028","score":1e0,"float":0.00001}`), false, false)
	if err != nil || text != `{"text": "中文😀\\u2028", "score": 1.0, "float": 1e-05}` {
		t.Fatal(text, err)
	}
	ascii, err := pythonJSON([]byte(`{"text":"😀中文"}`), true, true)
	if err != nil || ascii != `{"text": "\ud83d\ude00\u4e2d\u6587"}` {
		t.Fatal(ascii, err)
	}
}
func TestDatasetSplitIsStableAndGraderRulesAreEnforced(t *testing.T) {
	if splitOf("fix-a", 0.2) != splitOf("fix-a", 0.2) {
		t.Fatal("split changed")
	}
	info := TaskInfo{Suite: "core", Tags: []string{"finance"}, Hidden: []string{"test_grade.py"}}
	task := trajectory{suite: "core", outcome: "pass", events: []Event{{Type: "turn.completed"}}}
	if reason := excluded(task, info, true, map[string]bool{"hard": true}); reason != "" {
		t.Fatal(reason)
	}
	task.events = append(task.events, Event{Type: "tool.started", Params: map[string]any{"path": "/project/test_grade.py"}})
	if reason := excluded(task, info, true, map[string]bool{}); reason != "touched a grader" {
		t.Fatal(reason)
	}
	if domainOf([]string{"payments"}) != "finance" {
		t.Fatal("payment exposure domain changed")
	}
}
func TestDatasetToolResultsAreTruncatedByCharactersAndKeepFinalAnswer(t *testing.T) {
	result, _ := json.Marshal(map[string]any{"content": strings.Repeat("你", 6100)})
	task := trajectory{prompt: "task", events: []Event{{Type: "tool.started", Tool: "read_file"}, {Type: "tool.completed", Tool: "read_file", Result: result}, {Type: "turn.completed", Response: "Verified final"}}}
	example, err := toExample(task, "system")
	if err != nil {
		t.Fatal(err)
	}
	response := example.Contents[2].Parts[0]["functionResponse"].(map[string]any)["response"].(map[string]any)
	if response["truncated"] != true || len([]rune(response["head"].(string))) != 6000 {
		t.Fatal("character truncation changed")
	}
	if example.Contents[3].Parts[0]["text"] != "Verified final" {
		t.Fatal("final response lost")
	}
}
