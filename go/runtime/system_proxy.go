package main

import (
	"bufio"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"

	"golang.org/x/net/http/httpproxy"
)

// Go's environment proxy support does not read macOS Network settings.
// Python did, so a native migration must preserve the configured OS route.
func nativeProxy() func(*http.Request) (*url.URL, error) {
	for _, key := range []string{"HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"} {
		if _, set := os.LookupEnv(key); set {
			return http.ProxyFromEnvironment
		}
	}
	settings := systemProxySettings()
	settings.NoProxy = first(os.Getenv("NO_PROXY"), os.Getenv("no_proxy"), settings.NoProxy)
	proxy := settings.ProxyFunc()
	return func(req *http.Request) (*url.URL, error) { return proxy(req.URL) }
}

func parseSystemProxy(text string) httpproxy.Config {
	values := map[string]string{}
	var exceptions []string
	insideExceptions := false
	scanner := bufio.NewScanner(strings.NewReader(text))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "ExceptionsList :") {
			insideExceptions = true
			continue
		}
		if line == "}" {
			insideExceptions = false
			continue
		}
		key, value, ok := strings.Cut(line, " : ")
		if !ok {
			continue
		}
		if insideExceptions {
			if _, err := strconv.Atoi(key); err == nil {
				exceptions = append(exceptions, value)
			}
			continue
		}
		values[key] = value
	}
	endpoint := func(prefix string) string {
		if values[prefix+"Enable"] != "1" || values[prefix+"Proxy"] == "" {
			return ""
		}
		port, err := strconv.Atoi(values[prefix+"Port"])
		if err != nil || port < 1 || port > 65535 {
			return ""
		}
		return "http://" + net.JoinHostPort(values[prefix+"Proxy"], strconv.Itoa(port))
	}
	return httpproxy.Config{HTTPProxy: endpoint("HTTP"), HTTPSProxy: endpoint("HTTPS"), NoProxy: strings.Join(exceptions, ",")}
}
