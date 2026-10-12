package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
)

func changePreview(c fileChange) string {
	before := strings.Split(strings.ReplaceAll(string(c.before), "\r\n", "\n"), "\n")
	after := strings.Split(strings.ReplaceAll(string(c.after), "\r\n", "\n"), "\n")
	start := 0
	for start < len(before) && start < len(after) && before[start] == after[start] {
		start++
	}
	oldEnd, newEnd := len(before), len(after)
	for oldEnd > start && newEnd > start && before[oldEnd-1] == after[newEnd-1] {
		oldEnd--
		newEnd--
	}
	sum := sha256.Sum256(c.after)
	var b strings.Builder
	fmt.Fprintf(&b, "After SHA-256: %s\nChange preview (line %d):\n", hex.EncodeToString(sum[:]), start+1)
	for _, side := range []struct {
		prefix string
		lines  []string
	}{{"- ", before[start:oldEnd]}, {"+ ", after[start:newEnd]}} {
		limit := len(side.lines)
		if limit > 6 {
			limit = 6
		}
		for _, line := range side.lines[:limit] {
			b.WriteString(side.prefix + capText(line, 240) + "\n")
		}
		if len(side.lines) > limit {
			fmt.Fprintf(&b, "%s... %d more lines\n", side.prefix, len(side.lines)-limit)
		}
	}
	return b.String()
}
func commandOutput(data map[string]any) string {
	var b strings.Builder
	for _, key := range []string{"stdout", "stderr"} {
		if text, ok := data[key].(string); ok && text != "" {
			b.WriteString(key + ":\n" + capText(text, 6000) + "\n")
		}
	}
	return b.String()
}
