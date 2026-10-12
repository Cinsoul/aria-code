package main

import (
	"net/url"
	"testing"
)

func TestMacProxyConfigurationAndExceptions(t *testing.T) {
	c := parseSystemProxy(`<dictionary> {
 HTTPEnable : 1
 HTTPPort : 8100
 HTTPProxy : 127.0.0.1
 HTTPSEnable : 1
 HTTPSPort : 8200
 HTTPSProxy : ::1
 ExceptionsList : <array> {
  0 : *.internal.invalid
  1 : 192.0.2.0/24
 }
}`)
	proxy := c.ProxyFunc()
	for _, row := range []struct{ target, expected string }{
		{"https://aiplatform.googleapis.com/", "http://[::1]:8200"},
		{"http://example.invalid/", "http://127.0.0.1:8100"},
		{"https://project.internal.invalid/", ""},
		{"https://192.0.2.20/", ""},
		{"http://localhost:4567/", ""},
	} {
		u, _ := url.Parse(row.target)
		got, err := proxy(u)
		value := ""
		if got != nil {
			value = got.String()
		}
		if err != nil || value != row.expected {
			t.Fatal(row.target, value, err)
		}
	}
	if disabled := parseSystemProxy("HTTPEnable : 0\nHTTPProxy : localhost\nHTTPPort : 8100\n"); disabled.HTTPProxy != "" {
		t.Fatal("disabled system proxy was enabled")
	}
}
