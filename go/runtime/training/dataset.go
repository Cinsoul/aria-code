package training

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"
)

type TaskInfo struct {
	Suite        string
	Tags, Hidden []string
}
type Event struct {
	Type       string          `json:"type"`
	Tool       string          `json:"tool"`
	Params     map[string]any  `json:"params"`
	Result     json.RawMessage `json:"result"`
	Response   string          `json:"response"`
	Acceptance map[string]any  `json:"acceptance"`
	Success    *bool           `json:"success"`
	Error      string          `json:"error"`
}
type trajectory struct {
	path, suite, taskID, model, prompt string
	events                             []Event
	rawEvents                          []byte
	outcome                            string
	hash                               string
}
type DatasetOptions struct {
	Trajectories, Suites, Out string
	Holdout                   []string
	ValidationShare           float64
	System                    string
}
type Manifest struct {
	Rules        map[string]any            `json:"rules"`
	Inputs       map[string]string         `json:"inputs"`
	Models       []string                  `json:"models"`
	Examples     map[string]int            `json:"examples"`
	Tasks        map[string][]string       `json:"tasks"`
	Exposure     map[string]map[string]int `json:"exposure_by_domain"`
	Excluded     map[string]int            `json:"excluded"`
	HoldoutTasks []string                  `json:"holdout_tasks"`
}

func limitedFile(path string) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	body, err := io.ReadAll(io.LimitReader(f, 64<<20+1))
	if err != nil {
		return nil, err
	}
	if len(body) > 64<<20 {
		return nil, errors.New("training input file exceeds 64 MiB")
	}
	if !utf8.Valid(body) {
		return nil, errors.New("training input is not UTF-8")
	}
	return body, nil
}
func loadTasks(root string) (map[string]TaskInfo, error) {
	paths, err := filepath.Glob(filepath.Join(root, "*.yaml"))
	if err != nil {
		return nil, err
	}
	sort.Strings(paths)
	tasks := map[string]TaskInfo{}
	for _, path := range paths {
		body, err := limitedFile(path)
		if err != nil {
			return nil, err
		}
		var doc struct {
			Suite string `yaml:"suite"`
			Tasks []struct {
				ID     string   `yaml:"id"`
				Tags   []string `yaml:"tags"`
				Hidden []string `yaml:"hidden"`
			} `yaml:"tasks"`
		}
		if err := yaml.Unmarshal(body, &doc); err != nil {
			return nil, err
		}
		suite := doc.Suite
		if suite == "" {
			suite = strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
		}
		for _, task := range doc.Tasks {
			if task.ID == "" {
				return nil, errors.New("suite task has no ID")
			}
			tasks[task.ID] = TaskInfo{suite, task.Tags, task.Hidden}
		}
	}
	return tasks, nil
}
func loadTrajectory(path string) (trajectory, bool, error) {
	body, err := limitedFile(path)
	if err != nil {
		return trajectory{}, false, err
	}
	hash := sha256.Sum256(body)
	t := trajectory{path: path, suite: filepath.Base(filepath.Dir(path)), hash: hex.EncodeToString(hash[:])}
	scanner := bufio.NewScanner(bytes.NewReader(body))
	scanner.Buffer(make([]byte, 4096), 4<<20)
	first := true
	for scanner.Scan() {
		line := bytes.TrimSpace(scanner.Bytes())
		if len(line) == 0 || line[0] != '{' {
			continue
		}
		var header struct {
			Type    string `json:"type"`
			TaskID  string `json:"task_id"`
			Model   string `json:"model"`
			Prompt  string `json:"prompt"`
			Outcome string `json:"outcome"`
		}
		if err := json.Unmarshal(line, &header); err != nil {
			return t, false, err
		}
		if first {
			first = false
			if header.Type != "eval.task" {
				return t, false, nil
			}
			t.taskID, t.model, t.prompt = header.TaskID, header.Model, header.Prompt
			continue
		}
		if header.Type == "eval.outcome" {
			t.outcome = header.Outcome
			continue
		}
		if header.Type == "eval.task" {
			continue
		}
		var event Event
		decoder := json.NewDecoder(bytes.NewReader(line))
		decoder.UseNumber()
		if err := decoder.Decode(&event); err != nil {
			return t, false, err
		}
		t.events = append(t.events, event)
		t.rawEvents = append(t.rawEvents, line...)
	}
	if err := scanner.Err(); err != nil {
		return t, false, err
	}
	return t, !first, nil
}
func splitOf(task string, share float64) string {
	hash := sha256.Sum256([]byte(task))
	bucket := float64(binary.BigEndian.Uint32(hash[:4])) / float64(0xffffffff)
	if bucket < share {
		return "validation"
	}
	return "train"
}
func domainOf(tags []string) string {
	present := map[string]bool{}
	for _, tag := range tags {
		present[tag] = true
	}
	for _, domain := range []string{"software", "finance", "payments", "logistics"} {
		if present[domain] {
			if domain == "payments" {
				return "finance"
			}
			return domain
		}
	}
	return "other"
}
func finalEvent(t trajectory) (Event, bool) {
	for i := len(t.events) - 1; i >= 0; i-- {
		if t.events[i].Type == "turn.completed" {
			return t.events[i], true
		}
	}
	return Event{}, false
}
func shellGlob(pattern, name string) bool {
	var b strings.Builder
	b.WriteByte('^')
	for i := 0; i < len(pattern); i++ {
		switch pattern[i] {
		case '*':
			b.WriteString(".*")
		case '?':
			b.WriteByte('.')
		case '[':
			end := strings.IndexByte(pattern[i+1:], ']')
			if end < 0 {
				b.WriteString(`\[`)
				continue
			}
			end += i + 1
			part := pattern[i : end+1]
			if strings.HasPrefix(part, "[!") {
				part = "[^" + part[2:]
			}
			b.WriteString(part)
			i = end
		default:
			b.WriteString(regexp.QuoteMeta(pattern[i : i+1]))
		}
	}
	b.WriteByte('$')
	re, err := regexp.Compile(b.String())
	return err == nil && re.MatchString(name)
}
func excluded(t trajectory, info TaskInfo, known bool, holdout map[string]bool) string {
	if !known {
		return "task not in any suite"
	}
	if holdout[info.Suite] || holdout[t.suite] {
		return "locked holdout"
	}
	if t.outcome != "pass" {
		outcome := t.outcome
		if outcome == "" {
			outcome = "missing"
		}
		return "outcome " + outcome
	}
	final, ok := finalEvent(t)
	if !ok {
		return "no turn.completed"
	}
	if verified, ok := final.Acceptance["verified"].(bool); ok && !verified {
		return "its own checks failed"
	}
	graders := append(append([]string{}, info.Hidden...), "test_*_hidden.py")
	for _, event := range t.events {
		for _, value := range event.Params {
			name := filepath.Base(fmt.Sprint(value))
			for _, pattern := range graders {
				if shellGlob(pattern, name) {
					return "touched a grader"
				}
			}
		}
	}
	if bytes.Contains(t.rawEvents, []byte("eval.outcome")) || bytes.Contains(t.rawEvents, []byte("reward.json")) {
		return "grader output in the trajectory"
	}
	return ""
}

type content struct {
	Role  string           `json:"role"`
	Parts []map[string]any `json:"parts"`
}
type Example struct {
	System   content   `json:"systemInstruction"`
	Contents []content `json:"contents"`
}

func toExample(t trajectory, system string) (Example, error) {
	contents := []content{{"user", []map[string]any{{"text": t.prompt}}}}
	pending := 0
	for _, event := range t.events {
		last := len(contents) - 1
		switch event.Type {
		case "tool.started":
			args := event.Params
			if args == nil {
				args = map[string]any{}
			}
			call := map[string]any{"functionCall": map[string]any{"name": event.Tool, "args": args}}
			if contents[last].Role == "model" && pending == 0 {
				contents[last].Parts = append(contents[last].Parts, call)
			} else {
				contents = append(contents, content{"model", []map[string]any{call}})
			}
			pending++
		case "tool.completed":
			if pending == 0 {
				continue
			}
			pending--
			raw := event.Result
			if len(raw) == 0 || bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
				success, _ := json.Marshal(event.Success)
				errorText, _ := json.Marshal(event.Error)
				raw = json.RawMessage(`{"success":` + string(success) + `,"error":` + string(errorText) + `}`)
			}
			body, err := pythonJSON(raw, false, false)
			if err != nil {
				return Example{}, err
			}
			var result any = json.RawMessage(body)
			chars := []rune(body)
			if len(chars) > 6000 {
				result = map[string]any{"truncated": true, "head": string(chars[:6000])}
			}
			response := map[string]any{"functionResponse": map[string]any{"name": event.Tool, "response": result}}
			_, hasResponse := contents[last].Parts[0]["functionResponse"]
			if contents[last].Role == "user" && hasResponse {
				contents[last].Parts = append(contents[last].Parts, response)
			} else {
				contents = append(contents, content{"user", []map[string]any{response}})
			}
		}
	}
	if final, ok := finalEvent(t); ok && strings.TrimSpace(final.Response) != "" {
		contents = append(contents, content{"model", []map[string]any{{"text": strings.TrimSpace(final.Response)}}})
	}
	return Example{content{"system", []map[string]any{{"text": system}}}, contents}, nil
}

const DefaultSystem = "You are Aria, an AI agent for coding, financial analysis and logistics operations. Read the workspace first, compute every number with code from named data, keep each client's data apart, and check your work before you finish."

func BuildDataset(options DatasetOptions) (Manifest, error) {
	manifest := Manifest{Inputs: map[string]string{}, Models: []string{}, Examples: map[string]int{}, Tasks: map[string][]string{"train": {}, "validation": {}}, Exposure: map[string]map[string]int{}, Excluded: map[string]int{}, HoldoutTasks: []string{}}
	if options.ValidationShare < 0 || options.ValidationShare > 1 || math.IsNaN(options.ValidationShare) {
		return manifest, errors.New("validation_share must be between zero and one")
	}
	tasks, err := loadTasks(options.Suites)
	if err != nil {
		return manifest, err
	}
	holdout := map[string]bool{}
	for _, suite := range options.Holdout {
		holdout[suite] = true
	}
	manifest.Rules = map[string]any{"holdout_suites": options.Holdout, "split": "sha256(task_id)", "validation_share": options.ValidationShare, "eligible": "grader PASS and acceptance not failed; no grader file touched"}
	for id, info := range tasks {
		if holdout[info.Suite] {
			manifest.HoldoutTasks = append(manifest.HoldoutTasks, id)
		}
	}
	sort.Strings(manifest.HoldoutTasks)
	paths := []string{}
	err = filepath.WalkDir(options.Trajectories, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".jsonl") {
			paths = append(paths, path)
		}
		return nil
	})
	if err != nil {
		return manifest, err
	}
	sort.Strings(paths)
	if err := os.MkdirAll(options.Out, 0700); err != nil {
		return manifest, err
	}
	files := map[string]*os.File{}
	temporary := map[string]string{}
	defer func() {
		for _, file := range files {
			file.Close()
		}
		for _, name := range temporary {
			os.Remove(name)
		}
	}()
	for _, split := range []string{"train", "validation"} {
		file, err := os.CreateTemp(options.Out, ".aria-sft-*.jsonl")
		if err != nil {
			return manifest, err
		}
		files[split] = file
		temporary[split] = file.Name()
	}
	system := options.System
	if system == "" {
		system = DefaultSystem
	}
	models := map[string]bool{}
	seenTasks := map[string]map[string]bool{}
	fingerprints := map[[32]byte]bool{}
	for _, path := range paths {
		t, valid, err := loadTrajectory(path)
		if err != nil {
			return manifest, err
		}
		if !valid {
			continue
		}
		manifest.Inputs[path] = t.hash
		models[t.model] = true
		info, known := tasks[t.taskID]
		reason := excluded(t, info, known, holdout)
		if reason != "" {
			manifest.Excluded[reason]++
			continue
		}
		example, err := toExample(t, system)
		if err != nil {
			return manifest, err
		}
		contents, err := json.Marshal(example.Contents)
		if err != nil {
			return manifest, err
		}
		canonical, err := pythonJSON(contents, true, true)
		if err != nil {
			return manifest, err
		}
		fp := sha256.Sum256([]byte(canonical))
		if fingerprints[fp] {
			manifest.Excluded["duplicate"]++
			continue
		}
		fingerprints[fp] = true
		split := splitOf(t.taskID, options.ValidationShare)
		if seenTasks[split] == nil {
			seenTasks[split] = map[string]bool{}
		}
		seenTasks[split][t.taskID] = true
		if manifest.Exposure[split] == nil {
			manifest.Exposure[split] = map[string]int{}
		}
		manifest.Exposure[split][domainOf(info.Tags)]++
		manifest.Examples[split]++
		if err := json.NewEncoder(files[split]).Encode(example); err != nil {
			return manifest, err
		}
	}
	for split, ids := range seenTasks {
		manifest.Tasks[split] = []string{}
		for id := range ids {
			manifest.Tasks[split] = append(manifest.Tasks[split], id)
		}
		sort.Strings(manifest.Tasks[split])
	}
	for model := range models {
		manifest.Models = append(manifest.Models, model)
	}
	sort.Strings(manifest.Models)
	for _, file := range files {
		if err := file.Sync(); err != nil {
			return manifest, err
		}
		if err := file.Close(); err != nil {
			return manifest, err
		}
	}
	body, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return manifest, err
	}
	meta, err := os.CreateTemp(options.Out, ".aria-sft-*.json")
	if err != nil {
		return manifest, err
	}
	temporary["manifest"] = meta.Name()
	if _, err := meta.Write(body); err != nil {
		meta.Close()
		return manifest, err
	}
	if err := meta.Sync(); err != nil {
		meta.Close()
		return manifest, err
	}
	if err := meta.Close(); err != nil {
		return manifest, err
	}
	for _, split := range []string{"train", "validation"} {
		if err := os.Rename(temporary[split], filepath.Join(options.Out, split+".jsonl")); err != nil {
			return manifest, err
		}
	}
	if err := os.Rename(temporary["manifest"], filepath.Join(options.Out, "manifest.json")); err != nil {
		return manifest, err
	}
	return manifest, nil
}
