package main

// Change contracts — a port of src/aria_code/runtime/contract.py, the bounds
// a coding task runs inside, declared under `contract:` in .aria/policy.yaml
// and checked on every tool call before it runs. tests/test_native_go_contract.py
// compares this file with the Python module on the same policies and calls.

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"go.yaml.in/yaml/v3"
)

var policyFile = filepath.Join(".aria", "policy.yaml")

// mutatingCapabilities are the capabilities a contract's path rules apply to;
// reads and verification are never path-restricted.
var mutatingCapabilities = set("filesystem.write", "filesystem.delete", "git.stage", "git.commit", "git.history")

// ContractError is a policy file whose contract cannot be enforced as written.
type ContractError struct{ message string }

func (e *ContractError) Error() string { return e.message }

func contractErrorf(format string, args ...any) error {
	return &ContractError{fmt.Sprintf(format, args...)}
}

type ContractVerdict struct {
	Allowed    bool
	Reason     string
	Rule       string
	Assessment RiskAssessment
}

// toolResult is ContractVerdict.as_tool_result: what the model sees instead
// of the call's output.
func (v ContractVerdict) toolResult(tool string) toolResult {
	return toolResult{
		Error: fmt.Sprintf("Blocked by the change contract (%s): %s. The call was not run. Stay inside the contract, or tell the user what you need and why.", v.Rule, v.Reason),
		Data: map[string]any{"contract_violation": map[string]any{
			"tool": tool, "rule": v.Rule, "reason": v.Reason, "level": v.Assessment.Level,
		}},
	}
}

// contractGlob is _glob_regex: `src/**`, `**/*.sql`, `billing/*`, matched
// against a slash-separated relative path.
func contractGlob(pattern string) *regexp.Regexp {
	pattern = strings.TrimSpace(pattern)
	for strings.HasPrefix(pattern, "./") {
		pattern = pattern[2:]
	}
	if pattern == "" || pattern == "." {
		pattern = "**"
	}
	if strings.HasSuffix(pattern, "/") {
		pattern += "**"
	}
	var out strings.Builder
	for i := 0; i < len(pattern); {
		switch {
		case strings.HasPrefix(pattern[i:], "**/"):
			out.WriteString("(?:.*/)?")
			i += 3
		case strings.HasPrefix(pattern[i:], "**"):
			out.WriteString(".*")
			i += 2
		case pattern[i] == '*':
			out.WriteString("[^/]*")
			i++
		case pattern[i] == '?':
			out.WriteString("[^/]")
			i++
		default:
			r := []rune(pattern[i:])[0]
			out.WriteString(regexp.QuoteMeta(string(r)))
			i += len(string(r))
		}
	}
	// A directory pattern also covers what is inside it.
	return regexp.MustCompile("^" + out.String() + "(?:/.*)?$")
}

type ChangeContract struct {
	Root     string
	Goal     string
	Allow    []string
	Restrict []string
	Forbid   []string
	MaxLevel int
	Success  []string
	Source   string

	allowRe, restrictRe []*regexp.Regexp
}

// newContract is ChangeContract.__post_init__: validate and compile.
func newContract(c ChangeContract) (*ChangeContract, error) {
	var unknown []string
	for _, name := range c.Forbid {
		if !Capabilities[name] {
			unknown = appendNew(unknown, name)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		noun := "ies"
		if len(unknown) == 1 {
			noun = "y"
		}
		return nil, contractErrorf("unknown capabilit%s in forbid: %s", noun, strings.Join(unknown, ", "))
	}
	if c.MaxLevel < 0 || c.MaxLevel > 4 {
		return nil, contractErrorf("max_level must be 0-4, not %d", c.MaxLevel)
	}
	c.Root = expandUser(c.Root)
	forbid := appendNew(nil, c.Forbid...)
	sort.Strings(forbid)
	c.Forbid = forbid
	for _, p := range c.Allow {
		c.allowRe = append(c.allowRe, contractGlob(p))
	}
	for _, p := range c.Restrict {
		c.restrictRe = append(c.restrictRe, contractGlob(p))
	}
	return &c, nil
}

// pyStr is Python's str() for a YAML scalar.
func pyStr(value any) string {
	switch v := value.(type) {
	case nil:
		return "None"
	case string:
		return v
	case bool:
		if v {
			return "True"
		}
		return "False"
	case float64:
		text := strconv.FormatFloat(v, 'f', -1, 64)
		if !strings.ContainsAny(text, ".eE") {
			text += ".0"
		}
		return text
	default:
		return fmt.Sprint(v)
	}
}

// pyRepr is Python's repr() for the values a max_level error can name.
func pyRepr(value any) string {
	if text, ok := value.(string); ok {
		return "'" + strings.ReplaceAll(text, "'", `\'`) + "'"
	}
	return pyStr(value)
}

// asMapping accepts what yaml.v3 decodes a mapping to: map[string]any, or
// map[any]any when some key is not a string.
func asMapping(value any) (map[string]any, bool) {
	switch v := value.(type) {
	case map[string]any:
		return v, true
	case map[any]any:
		out := make(map[string]any, len(v))
		for key, item := range v {
			if text, ok := key.(string); ok {
				out[text] = item
			}
		}
		return out, true
	}
	return nil, false
}

// pyTruthy is Python truthiness for decoded YAML.
func pyTruthy(value any) bool {
	switch v := value.(type) {
	case nil:
		return false
	case bool:
		return v
	case string:
		return v != ""
	case int:
		return v != 0
	case float64:
		return v != 0
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	case map[any]any:
		return len(v) > 0
	}
	return true
}

// contractFromMapping is ChangeContract.from_mapping.
func contractFromMapping(data map[string]any, root, source string) (*ChangeContract, error) {
	strs := func(key string) ([]string, error) {
		value := data[key]
		if !pyTruthy(value) {
			return nil, nil
		}
		var items []any
		switch v := value.(type) {
		case string:
			items = []any{v}
		case []any:
			items = v
		case map[string]any:
			for k := range v {
				items = append(items, k)
			}
		default:
			return nil, contractErrorf("%s must be a list", key)
		}
		var out []string
		for _, item := range items {
			if text := strings.TrimSpace(pyStr(item)); text != "" {
				out = append(out, text)
			}
		}
		return out, nil
	}
	maxLevel := 4
	if raw, present := data["max_level"]; present {
		bad := contractErrorf("max_level must be 0-4, not %s", pyRepr(raw))
		switch v := raw.(type) {
		case int:
			maxLevel = v
		case bool:
			maxLevel = 0
			if v {
				maxLevel = 1
			}
		case float64:
			maxLevel = int(v)
		case string:
			n, err := strconv.Atoi(strings.TrimSpace(v))
			if err != nil {
				return nil, bad
			}
			maxLevel = n
		default:
			return nil, bad
		}
	}
	c := ChangeContract{Root: root, MaxLevel: maxLevel, Source: source}
	if pyTruthy(data["goal"]) {
		c.Goal = strings.TrimSpace(pyStr(data["goal"]))
	}
	var err error
	if c.Allow, err = strs("allow"); err != nil {
		return nil, err
	}
	if c.Restrict, err = strs("restrict"); err != nil {
		return nil, err
	}
	if c.Forbid, err = strs("forbid"); err != nil {
		return nil, err
	}
	if c.Success, err = strs("success"); err != nil {
		return nil, err
	}
	return newContract(c)
}

// LoadContract is ChangeContract.load: the project's contract from
// .aria/policy.yaml, nil if it declares none, and a *ContractError for a
// malformed file — which must not silently become no contract.
func LoadContract(root string) (*ChangeContract, error) {
	root = expandUser(root)
	path := filepath.Join(root, policyFile)
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() {
		return nil, nil
	}
	text, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var data any
	if err := yaml.Unmarshal(text, &data); err != nil {
		return nil, contractErrorf("%s: not valid YAML (%v)", path, err)
	}
	if !pyTruthy(data) {
		return nil, nil
	}
	mapping, ok := asMapping(data)
	if !ok {
		return nil, contractErrorf("%s: expected a mapping at the top level", path)
	}
	section, present := mapping["contract"]
	if !present || section == nil {
		return nil, nil
	}
	sectionMap, ok := asMapping(section)
	if !ok {
		return nil, contractErrorf("%s: 'contract' must be a mapping", path)
	}
	return contractFromMapping(sectionMap, root, path)
}

// failClosedContract is ChangeContract.fail_closed: reading and verification
// only, with the reason, when the project's contract could not be read.
func failClosedContract(root, reason string) *ChangeContract {
	c, _ := newContract(ChangeContract{Root: root, MaxLevel: 0, Source: "error: " + reason})
	return c
}

// projectContract is runtime_bridge.build_change_contract: the contract for
// one request, failing closed on any error.
func projectContract(root, goal string) *ChangeContract {
	c, err := LoadContract(root)
	if err != nil {
		var contractErr *ContractError
		if !errors.As(err, &contractErr) {
			err = fmt.Errorf("OSError: %v", err)
		}
		c = failClosedContract(root, err.Error())
	}
	if c == nil {
		return nil
	}
	return c.withGoal(goal)
}

func (c *ChangeContract) loadError() string {
	if strings.HasPrefix(c.Source, "error: ") {
		return c.Source[len("error: "):]
	}
	return ""
}

func (c *ChangeContract) withGoal(goal string) *ChangeContract {
	line := []rune(strings.Join(strings.FieldsFunc(goal, pyIsSpace), " "))
	copied := *c
	if len(line) > 200 {
		copied.Goal = string(line[:200]) + "…"
	} else {
		copied.Goal = string(line)
	}
	return &copied
}

func (c *ChangeContract) relative(path string) (string, bool) {
	candidate := expandUser(path)
	if !filepath.IsAbs(candidate) {
		candidate = filepath.Join(c.Root, candidate)
	}
	rel, err := filepath.Rel(resolveLoose(c.Root), resolveLoose(candidate))
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", false
	}
	return filepath.ToSlash(rel), true
}

func (c *ChangeContract) checkPath(path string) (rule, reason string) {
	relative, ok := c.relative(path)
	if !ok {
		return "outside-workspace", path + " is outside the workspace"
	}
	for i, regex := range c.restrictRe {
		if regex.MatchString(relative) {
			return "restrict", fmt.Sprintf("%s is restricted (%s)", relative, c.Restrict[i])
		}
	}
	if len(c.Allow) > 0 {
		for _, regex := range c.allowRe {
			if regex.MatchString(relative) {
				return "", ""
			}
		}
		return "allow", fmt.Sprintf("%s is outside the allowed paths (%s)", relative, strings.Join(c.Allow, ", "))
	}
	return "", ""
}

// Check is ChangeContract.check: whether one tool call may run.
func (c *ChangeContract) Check(tool string, params map[string]any) ContractVerdict {
	if params == nil {
		params = map[string]any{}
	}
	assessment := AssessTool(tool, params, c.Root)
	var used []string
	for _, name := range c.Forbid {
		if assessment.uses(name) {
			used = append(used, name)
		}
	}
	if len(used) > 0 {
		return ContractVerdict{false, "uses " + strings.Join(used, ", "), "forbid", assessment}
	}
	if assessment.Level > c.MaxLevel {
		summary := assessment.Summary
		if summary == "" {
			summary = tool
		}
		return ContractVerdict{false, fmt.Sprintf("%s is L%d (%s); this task allows up to L%d (%s)",
			summary, assessment.Level, assessment.Name, c.MaxLevel, levelNames[c.MaxLevel]), "max_level", assessment}
	}
	mutating := false
	for _, name := range assessment.Capabilities {
		if mutatingCapabilities[name] {
			mutating = true
		}
	}
	if mutating {
		paths := assessment.Files
		if tool != "run_command" {
			paths = toolPaths(params)
		}
		for _, path := range paths {
			if rule, reason := c.checkPath(path); rule != "" {
				return ContractVerdict{false, reason, rule, assessment}
			}
		}
	}
	return ContractVerdict{Allowed: true, Assessment: assessment}
}

// Render is the contract as the model and the user read it.
func (c *ChangeContract) Render() string {
	lines := []string{"CHANGE CONTRACT"}
	if reason := c.loadError(); reason != "" {
		lines = append(lines, "", fmt.Sprintf("⚠ %s could not be read: %s", filepath.ToSlash(policyFile), reason),
			"  Nothing may be changed until it is fixed; reading and verifying still work.")
	}
	if c.Goal != "" {
		lines = append(lines, "", "Goal", "  "+c.Goal)
	}
	lines = append(lines, "", "Allowed")
	if len(c.Allow) == 0 {
		lines = append(lines, "  ✓ modify files in the workspace")
	}
	for _, p := range c.Allow {
		lines = append(lines, "  ✓ modify "+p)
	}
	var restricted []string
	for _, p := range c.Restrict {
		restricted = append(restricted, "  × modify "+p)
	}
	for _, name := range c.Forbid {
		restricted = append(restricted, "  × "+name)
	}
	if c.MaxLevel < 4 {
		restricted = append(restricted, fmt.Sprintf("  × actions above L%d (%s risk)", c.MaxLevel, levelNames[c.MaxLevel]))
	}
	if len(restricted) > 0 {
		lines = append(append(lines, "", "Restricted"), restricted...)
	}
	if len(c.Success) > 0 {
		lines = append(lines, "", "Success criteria")
		for _, item := range c.Success {
			lines = append(lines, "  ✓ "+item)
		}
	}
	return strings.Join(lines, "\n")
}

func (c *ChangeContract) PromptBlock() string {
	return "[Change contract]\n" +
		"This task runs under the contract below. The runtime refuses any tool call " +
		"that breaks it, so plan inside it; if the task cannot be done within it, " +
		"stop and say which rule is in the way.\n\n" + c.Render()
}

// contractCommand answers `aria-runtime contract`: {"root", "goal", "calls":
// [{"tool", "params"}]} on stdin; the contract (null when the project has
// none), its rendering and a verdict per call on stdout.
func contractCommand(stdin io.Reader, stdout, stderr io.Writer) int {
	var request struct {
		Root  string `json:"root"`
		Goal  string `json:"goal"`
		Calls []struct {
			Tool   string         `json:"tool"`
			Params map[string]any `json:"params"`
		} `json:"calls"`
	}
	if err := json.NewDecoder(io.LimitReader(stdin, 1<<20)).Decode(&request); err != nil {
		fmt.Fprintln(stderr, "contract: expected a JSON request:", err)
		return 2
	}
	c := projectContract(request.Root, request.Goal)
	out := map[string]any{"contract": nil}
	if c != nil {
		verdicts := []map[string]any{}
		for _, call := range request.Calls {
			v := c.Check(call.Tool, call.Params)
			entry := map[string]any{"allowed": v.Allowed, "rule": v.Rule, "reason": v.Reason, "level": v.Assessment.Level}
			if !v.Allowed {
				entry["error"] = v.toolResult(call.Tool).Error
			}
			verdicts = append(verdicts, entry)
		}
		out["contract"] = map[string]any{
			"goal": c.Goal, "allow": orEmpty(c.Allow), "restrict": orEmpty(c.Restrict), "forbid": orEmpty(c.Forbid),
			"max_level": c.MaxLevel, "success": orEmpty(c.Success), "load_error": c.loadError(),
			"render": c.Render(), "prompt_block": c.PromptBlock(),
		}
		out["verdicts"] = verdicts
	}
	if err := json.NewEncoder(stdout).Encode(out); err != nil {
		return 2
	}
	return 0
}
