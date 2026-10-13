package main

import (
	"context"
	"errors"
	"net"
	"net/http"
	"time"
)

// Some networks can reach only part of a DNS answer. Race bounded TCP connects,
// not HTTP requests: no request body or credential is sent before a winner is
// selected, and a failed address cannot stall a model for the full request timeout.
func nativeTransport() *http.Transport {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nativeProxy()
	transport.DialContext = dialContext
	transport.TLSHandshakeTimeout = 10 * time.Second
	transport.ResponseHeaderTimeout = 30 * time.Second
	return transport
}
func dialContext(ctx context.Context, network, address string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(address)
	if err != nil {
		return nil, err
	}
	dialer := &net.Dialer{Timeout: 8 * time.Second, KeepAlive: 30 * time.Second}
	if net.ParseIP(host) != nil {
		return dialer.DialContext(ctx, network, address)
	}
	lookup, cancel := context.WithTimeout(ctx, 5*time.Second)
	ips, err := net.DefaultResolver.LookupIPAddr(lookup, host)
	cancel()
	if err != nil {
		return nil, err
	}
	if len(ips) == 0 {
		return nil, errors.New("host has no addresses")
	}
	if len(ips) > 8 {
		ips = ips[:8]
	}
	return raceConnections(ctx, network, port, ips, dialer.DialContext)
}
func raceConnections(ctx context.Context, network, port string, ips []net.IPAddr, dial func(context.Context, string, string) (net.Conn, error)) (net.Conn, error) {
	if len(ips) == 0 {
		return nil, errors.New("host has no addresses")
	}
	bounded, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	type outcome struct {
		conn net.Conn
		err  error
	}
	results := make(chan outcome)
	for _, ip := range ips {
		go func(ip net.IPAddr) {
			conn, err := dial(bounded, network, net.JoinHostPort(ip.String(), port))
			select {
			case results <- outcome{conn, err}:
			case <-bounded.Done():
				if conn != nil {
					conn.Close()
				}
			}
		}(ip)
	}
	var last error
	for range ips {
		select {
		case r := <-results:
			if r.err == nil {
				return r.conn, nil
			}
			last = r.err
		case <-bounded.Done():
			return nil, bounded.Err()
		}
	}
	return nil, last
}
