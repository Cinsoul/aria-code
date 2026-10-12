package main

import (
	"context"
	"errors"
	"io/fs"
	"path/filepath"
	"regexp"
	"strings"
)

func safeEntry(s *scope, parent *scopedPath, rel string) (fs.FileInfo, error) {
	p, err := s.open(filepath.Join(parent.absolute, filepath.FromSlash(rel)), false)
	if err != nil {
		return nil, err
	}
	defer p.Close()
	return p.root.Stat(p.relative)
}

func fileGlob(ctx context.Context, s *scope, params map[string]any) toolResult {
	if err := noHostFlags(params); err != nil {
		return failed(err)
	}
	p, err := s.open(str(params, "path", "."), false)
	if err != nil {
		return failed(err)
	}
	defer p.Close()
	info, err := p.root.Stat(p.relative)
	if err != nil {
		return failed(err)
	}
	if !info.IsDir() {
		return failed(errors.New("glob requires a directory"))
	}
	pattern := str(params, "pattern", "**/*")
	limit := integer(params, "limit", 200)
	if limit < 1 || limit > 1000 {
		limit = 1000
	}
	files := []string{}
	err = walk(ctx, p, pattern, 100000, func(rel string, _ fs.DirEntry) error {
		info, err := safeEntry(s, p, rel)
		if err != nil || !info.Mode().IsRegular() {
			return nil
		}
		files = append(files, filepath.FromSlash(rel))
		if len(files) >= limit {
			return fs.SkipAll
		}
		return nil
	})
	if err != nil {
		return failed(err)
	}
	return toolResult{Success: true, Data: map[string]any{"pattern": pattern, "root": p.absolute, "count": len(files), "files": files}}
}

func searchCode(ctx context.Context, s *scope, params map[string]any) toolResult {
	if err := noHostFlags(params); err != nil {
		return failed(err)
	}
	pattern := str(params, "pattern", "")
	if pattern == "" || len(pattern) > 8192 {
		return failed(errors.New("a nonempty search pattern of at most 8192 bytes is required"))
	}
	re, err := regexp.Compile("(?i)" + pattern)
	if err != nil {
		return failed(err)
	}
	p, err := s.open(str(params, "path", "."), false)
	if err != nil {
		return failed(err)
	}
	defer p.Close()
	info, err := p.root.Stat(p.relative)
	if err != nil {
		return failed(err)
	}
	if !info.IsDir() {
		return failed(errors.New("search_code requires a directory"))
	}
	matches := []map[string]any{}
	checked := 0
	err = walk(ctx, p, str(params, "glob", "**/*.py"), 100000, func(rel string, _ fs.DirEntry) error {
		if checked >= 200 {
			return fs.SkipAll
		}
		checked++
		file, err := s.open(filepath.Join(p.absolute, filepath.FromSlash(rel)), false)
		if err != nil {
			return nil
		}
		defer file.Close()
		body, err := readRegular(file, 5_000_000)
		if err != nil {
			return nil
		}
		text := strings.ToValidUTF8(string(body), "�")
		text = strings.ReplaceAll(strings.ReplaceAll(text, "\r\n", "\n"), "\r", "\n")
		for i, line := range strings.Split(text, "\n") {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			if re.MatchString(line) {
				matches = append(matches, map[string]any{"file": filepath.FromSlash(rel), "line": i + 1, "content": capText(strings.TrimSpace(line), 200)})
				if len(matches) >= 50 {
					return fs.SkipAll
				}
			}
		}
		return nil
	})
	if err != nil {
		return failed(err)
	}
	return toolResult{Success: true, Data: map[string]any{"pattern": pattern, "path": p.absolute, "count": len(matches), "matches": matches}}
}
