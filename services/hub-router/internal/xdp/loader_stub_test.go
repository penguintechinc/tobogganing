//go:build !xdp

package xdp

import (
	"net"
	"testing"
)

func TestStubNewDoesNotPanic(t *testing.T) {
	x := New(XDPConfig{Enabled: true})
	if x == nil {
		t.Fatal("expected non-nil stub")
	}
}

func TestStubAttachReturnsNil(t *testing.T) {
	x := New(XDPConfig{})
	if err := x.Attach("eth0"); err != nil {
		t.Fatalf("expected nil error from stub, got %v", err)
	}
}

func TestStubMethodsDoNotPanic(t *testing.T) {
	x := New(XDPConfig{})
	x.SetRateLimit(1000)
	x.SetSYNRateLimit(500)
	x.SetUDPRateLimit(500)
	x.BlockIP(net.ParseIP("1.2.3.4"))
	x.UnblockIP(net.ParseIP("1.2.3.4"))
	stats := x.Stats()
	if stats.PacketsProcessed != 0 {
		t.Fatal("expected zero stats from stub")
	}
	if x.BlocklistSize() != 0 {
		t.Fatal("expected zero blocklist size from stub")
	}
	x.Close()
}
