//go:build !darwin

package main

import "golang.org/x/net/http/httpproxy"

func systemProxySettings() httpproxy.Config { return httpproxy.Config{} }
