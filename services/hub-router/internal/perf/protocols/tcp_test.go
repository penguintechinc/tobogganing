package protocols

import (
	"net"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

// startTCPListener creates a TCP listener on a random port and returns it.
// The caller is responsible for closing the listener when done.
func startTCPListener(t *testing.T) net.Listener {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to create test TCP listener: %v", err)
	}
	return ln
}

// ---------------------------------------------------------------------------
// RunTCPTest — successful connection
// ---------------------------------------------------------------------------

func TestRunTCPTest_Success(t *testing.T) {
	ln := startTCPListener(t)
	defer ln.Close()

	// Accept connections in the background so the dial can complete.
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	result := RunTCPTest(ln.Addr().String(), 5*time.Second)

	if !result.Success {
		t.Errorf("expected Success=true for open port, got false (error: %q)", result.Error)
	}
	if result.Target != ln.Addr().String() {
		t.Errorf("expected Target %q, got %q", ln.Addr().String(), result.Target)
	}
	if result.LatencyMs <= 0 {
		t.Errorf("expected positive LatencyMs, got %f", result.LatencyMs)
	}
	if result.Error != "" {
		t.Errorf("expected empty Error on success, got %q", result.Error)
	}
}

func TestRunTCPTest_TargetFieldSet(t *testing.T) {
	ln := startTCPListener(t)
	defer ln.Close()

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	addr := ln.Addr().String()
	result := RunTCPTest(addr, 5*time.Second)

	if result.Target != addr {
		t.Errorf("Target field: got %q, want %q", result.Target, addr)
	}
}

// ---------------------------------------------------------------------------
// RunTCPTest — connection refused
// ---------------------------------------------------------------------------

func TestRunTCPTest_ConnectionRefused(t *testing.T) {
	// Bind a listener, get the port, close it immediately so the port is free
	// but not listening.
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to bind: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close()

	result := RunTCPTest(addr, 2*time.Second)

	if result.Success {
		t.Error("expected Success=false for connection-refused port")
	}
	if result.Error == "" {
		t.Error("expected non-empty Error on connection refused")
	}
	if result.LatencyMs <= 0 {
		t.Errorf("expected positive LatencyMs even on failure, got %f", result.LatencyMs)
	}
}

func TestRunTCPTest_InvalidAddress(t *testing.T) {
	result := RunTCPTest("127.0.0.1:99999", 500*time.Millisecond)

	if result.Success {
		t.Error("expected Success=false for invalid port number")
	}
	if result.Error == "" {
		t.Error("expected non-empty Error for invalid address")
	}
}

func TestRunTCPTest_UnresolvableHost(t *testing.T) {
	result := RunTCPTest("nonexistent.invalid:443", 500*time.Millisecond)

	if result.Success {
		t.Error("expected Success=false for unresolvable host")
	}
	if result.Error == "" {
		t.Error("expected non-empty Error for unresolvable host")
	}
}

// ---------------------------------------------------------------------------
// RunTCPTest — timeout
// ---------------------------------------------------------------------------

func TestRunTCPTest_Timeout(t *testing.T) {
	// Listen but never accept, so the connection will be established but
	// we mostly care that an unreachable host times out correctly.
	// Use a non-routable address to simulate a connection that hangs.
	// 192.0.2.0/24 is documentation-only and should not be routable.
	result := RunTCPTest("192.0.2.1:9999", 100*time.Millisecond)

	if result.Success {
		t.Error("expected Success=false on timeout")
	}
	// LatencyMs should be at least the timeout duration.
	if result.LatencyMs <= 0 {
		t.Errorf("expected positive LatencyMs on timeout, got %f", result.LatencyMs)
	}
	if result.Error == "" {
		t.Error("expected non-empty Error on timeout")
	}
}

// ---------------------------------------------------------------------------
// RunTCPTest — result struct integrity
// ---------------------------------------------------------------------------

func TestRunTCPTest_LatencyIsPositiveOnSuccess(t *testing.T) {
	ln := startTCPListener(t)
	defer ln.Close()

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	result := RunTCPTest(ln.Addr().String(), 5*time.Second)
	if result.LatencyMs <= 0 {
		t.Errorf("LatencyMs should be > 0 on success, got %f", result.LatencyMs)
	}
}

func TestRunTCPTest_SuccessFalseByDefault(t *testing.T) {
	// For any failure path Success must be false (zero value for bool).
	result := RunTCPTest("127.0.0.1:1", 200*time.Millisecond)
	if result.Success {
		t.Error("expected Success=false for connection to port 1")
	}
}

// ---------------------------------------------------------------------------
// Table-driven: multiple failure scenarios
// ---------------------------------------------------------------------------

func TestRunTCPTest_FailureCases(t *testing.T) {
	tests := []struct {
		name    string
		target  string
		timeout time.Duration
	}{
		{"connection refused", "127.0.0.1:1", 500 * time.Millisecond},
		{"invalid port", "127.0.0.1:99999", 500 * time.Millisecond},
		{"unresolvable host", "this.host.does.not.exist.invalid:80", 500 * time.Millisecond},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			result := RunTCPTest(tt.target, tt.timeout)
			if result.Success {
				t.Errorf("%s: expected Success=false, got true", tt.name)
			}
			if result.Error == "" {
				t.Errorf("%s: expected non-empty Error, got empty string", tt.name)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// Multiple concurrent connections
// ---------------------------------------------------------------------------

func TestRunTCPTest_ConcurrentCalls(t *testing.T) {
	ln := startTCPListener(t)
	defer ln.Close()

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			conn.Close()
		}
	}()

	addr := ln.Addr().String()
	results := make(chan TCPTestResult, 5)

	for i := 0; i < 5; i++ {
		go func() {
			results <- RunTCPTest(addr, 5*time.Second)
		}()
	}

	for i := 0; i < 5; i++ {
		r := <-results
		if !r.Success {
			t.Errorf("concurrent call %d: expected Success=true, got false (error: %q)", i, r.Error)
		}
	}
}
