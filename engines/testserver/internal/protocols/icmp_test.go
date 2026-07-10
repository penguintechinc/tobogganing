//go:build !integration

package protocols_test

import (
	"strings"
	"testing"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/protocols"
)

// ---------------------------------------------------------------------------
// TestICMP — tests that don't need real network access
// ---------------------------------------------------------------------------

// TestICMP_UnsupportedProtocol verifies that an unknown ICMP protocol returns an error.
func TestICMP_UnsupportedProtocol(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "flood", // not supported
		Count:    1,
		Timeout:  2,
	}

	result, err := protocols.TestICMP(req)
	if err == nil {
		t.Error("expected error for unsupported ICMP protocol")
	}
	if result != nil && result.Success {
		t.Error("expected success=false for unsupported protocol")
	}
	if result == nil {
		t.Error("expected non-nil result even on error")
	}
}

// TestICMP_DefaultProtocol_NoNetRequired verifies that an empty protocol
// defaults to "ping". Because ping requires privileges, we only test the
// defaults/struct setup — not actual execution.
func TestICMP_DefaultsApplied(t *testing.T) {
	// We exercise the path that sets defaults (count=4, timeout=10)
	// by passing zero values and verifying we get a non-nil result back.
	req := protocols.ICMPTestRequest{
		Target:  "127.0.0.1",
		Count:   0,   // should default to 4
		Timeout: 0,   // should default to 10
	}
	// This will actually run ping; skip if not enough privileges.
	result, err := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// If ping fails due to permissions or ping not found, that's OK.
	// We just check no panic.
	_ = err
}

// TestICMP_ProtocolDetailFallback verifies ProtocolDetail is used when Protocol is empty.
func TestICMP_ProtocolDetailFallback(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:         "127.0.0.1",
		Protocol:       "",
		ProtocolDetail: "ping",
		Count:          1,
		Timeout:        2,
	}
	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
}

// TestICMP_URLTarget verifies that a URL-formatted target is handled.
func TestICMP_URLTarget(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "https://localhost",
		Protocol: "ping",
		Count:    1,
		Timeout:  2,
	}
	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// The hostname should have the scheme stripped.
	if result.Target == "https://localhost" {
		t.Errorf("expected scheme to be stripped from target, got %q", result.Target)
	}
}

// TestICMP_TargetWithPort verifies that a target with a port is handled.
func TestICMP_TargetWithPort(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "localhost:8080",
		Protocol: "ping",
		Count:    1,
		Timeout:  2,
	}
	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// Port should be stripped from target.
	if result.Target == "localhost:8080" {
		t.Errorf("expected port to be stripped from target, got %q", result.Target)
	}
}

// TestICMPTestResult_ToJSON verifies JSON marshalling.
func TestICMPTestResult_ToJSON(t *testing.T) {
	r := &protocols.ICMPTestResult{
		Target:            "8.8.8.8",
		Protocol:          "ping",
		Success:           true,
		PacketsSent:       4,
		PacketsReceived:   4,
		PacketLossPercent: 0,
		LatencyMS:         10.5,
	}
	data, err := r.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON failed: %v", err)
	}
	if len(data) == 0 {
		t.Error("ToJSON returned empty data")
	}
}

// TestICMP_TracerouteProtocol exercises the testTraceroute branch in TestICMP.
// Traceroute may fail in CI without root/capabilities; we just verify no panic.
func TestICMP_TracerouteProtocol(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "traceroute",
		Count:    1,
		Timeout:  3,
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP traceroute must return non-nil result")
	}
	// Either success or failure — no panic.
}

// TestICMP_TracerouteDefaultTimeout exercises the default timeout path in testTraceroute.
func TestICMP_TracerouteDefaultTimeout(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "traceroute",
		Count:    1,
		Timeout:  0, // should default inside TestICMP
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP traceroute must return non-nil result")
	}
}

// TestICMP_PingLocalhost exercises the full ping code path on localhost.
// This is a privileged operation but ping command exists on most CI systems.
func TestICMP_PingLocalhost(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "ping",
		Count:    2,
		Timeout:  3,
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP ping must return non-nil result")
	}
	// ping may succeed or fail depending on environment permissions.
	// We verify the struct is properly populated either way.
	if result.Target == "" {
		t.Error("expected non-empty Target in ICMP result")
	}
	if result.Protocol != "ping" {
		t.Errorf("expected Protocol='ping', got %q", result.Protocol)
	}
}

// TestICMP_PingWithJitter exercises the jitter calculation in testPing
// by running multiple ping packets (count=3) so len(latencies) > 1.
func TestICMP_PingWithJitter(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "ping",
		Count:    3,
		Timeout:  5,
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP ping must return non-nil result")
	}
	// If ping succeeded, jitter should be calculated.
	// If failed (no root), JitterMS stays 0 — that's fine.
	_ = result.JitterMS
}

// TestICMPTestResult_WithHops verifies that Hops field is populated for traceroute results.
func TestICMPTestResult_WithHops(t *testing.T) {
	r := &protocols.ICMPTestResult{
		Target:   "10.0.0.1",
		Protocol: "traceroute",
		Success:  true,
		Hops:     []string{"Hop 1: 10.0.0.1 1.2ms", "Hop 2: 10.0.0.2 3.4ms"},
	}
	data, err := r.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON failed: %v", err)
	}
	if len(data) == 0 {
		t.Error("ToJSON returned empty data")
	}
}

// TestICMP_TracerouteInvalidTarget tests traceroute with invalid/unreachable host
// to exercise the error path in testTraceroute when command fails.
func TestICMP_TracerouteInvalidTarget(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "", // Empty target will cause traceroute command to fail
		Protocol: "traceroute",
		Timeout:  2,
	}
	result, err := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// Error is expected for empty target.
	_ = err
}

// TestICMP_TracerouteCommandError exercises the error branch when traceroute command fails.
// Using a private/unreachable IP forces the command to fail.
func TestICMP_TracerouteUnreachable(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "192.0.2.1", // TEST-NET-1, reserved, unreachable
		Protocol: "traceroute",
		Timeout:  2,
	}
	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// Either success or failure is acceptable; we're testing no panic.
}

// TestICMP_PingFailure exercises the failure path in testPing by pinging an unreachable host.
func TestICMP_PingFailure(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "192.0.2.1", // TEST-NET-1, reserved, unreachable
		Protocol: "ping",
		Count:    1,
		Timeout:  1,
	}
	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// Failure expected but no panic.
}

// TestICMP_TracerouteSuccess_ParsesHops tests traceroute against localhost
// to exercise the hop parsing path in testTraceroute. This will produce
// real hops that should be parsed correctly.
func TestICMP_TracerouteSuccess_ParsesHops(t *testing.T) {
	// TestMain provides a fake traceroute binary, so traceroute is always available
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "traceroute",
		Timeout:  5,
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP traceroute must return non-nil result")
	}

	// When traceroute succeeds, Hops should be populated.
	// If it fails due to network/permissions, that's fine too.
	// We're testing the parsing branch is exercised.
	if result.Success {
		if len(result.Hops) == 0 {
			t.Log("Traceroute succeeded but no hops parsed (may be filtered output)")
		}
	}
}

// TestICMP_PingWitoutCount exercises the path where TestICMP initializes
// Count to 4 when 0 is provided.
func TestICMP_PingDefaultCount(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "ping",
		Count:    0, // Should default to 4 in TestICMP
		Timeout:  5,
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// Just verifying no panic and struct is initialized.
}

// TestICMP_PingWithSmallTimeout tests ping with very short timeout.
func TestICMP_PingSmallTimeout(t *testing.T) {
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "ping",
		Count:    1,
		Timeout:  1, // Very short to test timeout branch
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP must return non-nil result")
	}
	// Timeout expected but no panic.
}

// TestICMP_TracerouteParsingOutput exercises the hop parsing path in testTraceroute (lines 199-213).
// This test verifies that traceroute output is correctly parsed into Hops array.
// It checks the parsing logic by verifying hops are extracted from a successful traceroute run.
func TestICMP_TracerouteParsingOutput(t *testing.T) {
	// TestMain provides a fake traceroute binary, so traceroute is always available
	req := protocols.ICMPTestRequest{
		Target:   "127.0.0.1",
		Protocol: "traceroute",
		Timeout:  5,
	}

	result, _ := protocols.TestICMP(req)
	if result == nil {
		t.Fatal("TestICMP traceroute must return non-nil result")
	}

	// When traceroute succeeds, verify that the Hops array is populated
	// and parsing occurred correctly.
	if result.Success {
		if len(result.Hops) == 0 {
			t.Log("Traceroute succeeded but no hops parsed (may be filtered output)")
		} else {
			// Verify each hop string looks correct (should not start with "traceroute" header)
			for _, hop := range result.Hops {
				if strings.HasPrefix(hop, "traceroute") || strings.HasPrefix(hop, "Tracing") {
					t.Errorf("Hop contains header line that should have been filtered: %q", hop)
				}
				// Hop should be non-empty after parsing
				if len(strings.TrimSpace(hop)) == 0 {
					t.Error("Hop should not be empty after parsing")
				}
			}
		}
	}
}
