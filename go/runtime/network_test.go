package main

import (
	"context"
	"errors"
	"net"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestAddressRaceDoesNotWaitForAnUnreachableFirstAddress(t *testing.T) {
	client, peer := net.Pipe()
	defer peer.Close()
	var wg sync.WaitGroup
	wg.Add(1)
	got, err := raceConnections(context.Background(), "tcp", "443", []net.IPAddr{{IP: net.ParseIP("192.0.2.1")}, {IP: net.ParseIP("192.0.2.2")}}, func(ctx context.Context, network, address string) (net.Conn, error) {
		if strings.Contains(address, "192.0.2.1") {
			defer wg.Done()
			<-ctx.Done()
			return nil, ctx.Err()
		}
		return client, nil
	})
	if err != nil || got != client {
		t.Fatal("reachable address was not selected", err)
	}
	got.Close()
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("losing connection was not cancelled")
	}
}

func TestAddressRacePropagatesCancellationAndFailures(t *testing.T) {
	ips := []net.IPAddr{{IP: net.ParseIP("192.0.2.1")}}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := raceConnections(ctx, "tcp", "443", ips, func(ctx context.Context, _, _ string) (net.Conn, error) { return nil, ctx.Err() }); err == nil {
		t.Fatal("cancellation disappeared")
	}
	failure := errors.New("refused")
	if _, err := raceConnections(context.Background(), "tcp", "443", ips, func(context.Context, string, string) (net.Conn, error) { return nil, failure }); !errors.Is(err, failure) {
		t.Fatal(err)
	}
	if _, err := raceConnections(context.Background(), "tcp", "443", nil, func(context.Context, string, string) (net.Conn, error) { return nil, nil }); err == nil {
		t.Fatal("empty address list accepted")
	}
}
