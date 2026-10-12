package main

import (
	"context"
	"os/exec"
	"time"

	"golang.org/x/net/http/httpproxy"
)

func systemProxySettings() httpproxy.Config {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	// macOS's own read-only tool, not a shell or Python helper. It exposes
	// manual network proxy settings; no user configuration is modified.
	body, err := exec.CommandContext(ctx, "/usr/sbin/scutil", "--proxy").Output()
	if err != nil || len(body) > 65536 {
		return httpproxy.Config{}
	}
	return parseSystemProxy(string(body))
}
