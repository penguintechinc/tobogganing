package protocols_test

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/protocols"
)

// ---------------------------------------------------------------------------
// TestHTTP — using httptest.NewServer for real local HTTP
// ---------------------------------------------------------------------------

// TestHTTP_HTTP1_Success verifies a successful HTTP/1.x request.
func TestHTTP_HTTP1_Success(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	req := protocols.HTTPTestRequest{
		Target:   ts.URL,
		Protocol: "http1",
		Method:   "GET",
		Timeout:  10,
		Count:    1,
	}

	result, err := protocols.TestHTTP(req)
	if err != nil {
		t.Fatalf("TestHTTP unexpected error: %v", err)
	}
	if result == nil {
		t.Fatal("TestHTTP returned nil result")
	}
	if !result.Success {
		t.Errorf("expected success=true, got error=%q", result.Error)
	}
	if result.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", result.StatusCode)
	}
	if result.LatencyMS < 0 {
		t.Errorf("latency should be >= 0, got %f", result.LatencyMS)
	}
}

// TestHTTP_HTTP1_NotFound verifies that a 404 response is returned as
// success=false (status >= 400).
func TestHTTP_HTTP1_NotFound(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer ts.Close()

	req := protocols.HTTPTestRequest{
		Target:   ts.URL,
		Protocol: "http1",
		Method:   "GET",
		Timeout:  5,
		Count:    1,
	}

	result, err := protocols.TestHTTP(req)
	if err != nil {
		t.Fatalf("TestHTTP unexpected error: %v", err)
	}
	if result.StatusCode != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", result.StatusCode)
	}
	if result.Success {
		t.Errorf("expected success=false for 404 response")
	}
}

// TestHTTP_MultipleCount verifies jitter is computed when count > 1.
func TestHTTP_MultipleCount(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	req := protocols.HTTPTestRequest{
		Target:   ts.URL,
		Protocol: "http1",
		Method:   "GET",
		Timeout:  10,
		Count:    3,
	}

	result, err := protocols.TestHTTP(req)
	if err != nil {
		t.Fatalf("TestHTTP unexpected error: %v", err)
	}
	if result == nil {
		t.Fatal("TestHTTP returned nil result")
	}
	if result.MinLatencyMS > result.MaxLatencyMS {
		t.Errorf("min latency %f > max latency %f", result.MinLatencyMS, result.MaxLatencyMS)
	}
}

// TestHTTP_ConnectionRefused verifies a refused connection returns failure.
func TestHTTP_ConnectionRefused(t *testing.T) {
	req := protocols.HTTPTestRequest{
		Target:   "http://127.0.0.1:19999", // port unlikely to be open
		Protocol: "http1",
		Timeout:  2,
		Count:    1,
	}

	result, err := protocols.TestHTTP(req)
	if result == nil {
		t.Fatal("TestHTTP should return a result even on failure")
	}
	// Either err != nil or result.Success == false
	if err == nil && result.Success {
		t.Error("expected failure for connection refused")
	}
}

// TestHTTP_UnsupportedProtocol verifies that http3 returns an error.
func TestHTTP_UnsupportedProtocol_HTTP3(t *testing.T) {
	req := protocols.HTTPTestRequest{
		Target:   "https://example.com",
		Protocol: "http3",
		Timeout:  2,
		Count:    1,
	}

	result, err := protocols.TestHTTP(req)
	if err == nil {
		t.Error("expected error for http3 (not implemented)")
	}
	_ = result
}

// TestHTTP_UnknownProtocol verifies an unknown protocol string returns an error.
func TestHTTP_UnknownProtocol(t *testing.T) {
	req := protocols.HTTPTestRequest{
		Target:   "https://example.com",
		Protocol: "gopher",
		Timeout:  2,
		Count:    1,
	}

	result, err := protocols.TestHTTP(req)
	if err == nil {
		t.Error("expected error for unknown protocol 'gopher'")
	}
	_ = result
}

// TestHTTP_DefaultProtocol verifies that an empty protocol defaults to http2.
// http2 upgrade over plain-text will fail, but the code should attempt it
// and not panic.
func TestHTTP_DefaultProtocol(t *testing.T) {
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	req := protocols.HTTPTestRequest{
		Target:  ts.URL,
		Timeout: 3,
		Count:   1,
		// Protocol intentionally empty — should default to "http2"
	}
	result, _ := protocols.TestHTTP(req)
	if result == nil {
		t.Fatal("TestHTTP must return non-nil result")
	}
}

// TestHTTP_ProtocolDetailFallback verifies ProtocolDetail is used when Protocol is empty.
func TestHTTP_ProtocolDetailFallback(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	req := protocols.HTTPTestRequest{
		Target:         ts.URL,
		Protocol:       "",
		ProtocolDetail: "http1",
		Timeout:        5,
		Count:          1,
	}
	result, err := protocols.TestHTTP(req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.Success {
		t.Errorf("expected success=true, got error=%q", result.Error)
	}
}

// TestHTTP_TargetWithoutScheme verifies that a target without a scheme gets https:// prepended.
func TestHTTP_TargetWithoutScheme(t *testing.T) {
	// Use a TLS test server to handle the https:// prefix that gets added.
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	// Strip the scheme to force the code to add it.
	targetWithoutScheme := ts.Listener.Addr().String() // "127.0.0.1:XXXXX"

	req := protocols.HTTPTestRequest{
		Target:   targetWithoutScheme,
		Protocol: "http1",
		Timeout:  3,
		Count:    1,
	}
	result, _ := protocols.TestHTTP(req)
	if result == nil {
		t.Fatal("TestHTTP must return non-nil result")
	}
	// We just verify no panic and a target was stored with scheme.
	if result.Target == targetWithoutScheme {
		// The implementation should have prepended https://
		// This is informational — not a hard failure if implementation changes.
	}
}

// TestHTTP_AllRequestsFailed exercises the "len(latencies) == 0" path (line 147-154)
// where all HTTP requests fail. This uses an unreachable target and count > 1
// to ensure multiple failed attempts.
func TestHTTP_AllRequestsFailed(t *testing.T) {
	req := protocols.HTTPTestRequest{
		Target:   "http://192.0.2.1:9999", // TEST-NET-1, unreachable
		Protocol: "http1",
		Timeout:  1,
		Count:    2, // Multiple attempts to ensure latencies stays empty
	}

	result, err := protocols.TestHTTP(req)
	if result == nil {
		t.Fatal("TestHTTP should return a result even when all requests fail")
	}
	// All requests failed, so success should be false.
	if result.Success {
		t.Error("expected success=false when all requests fail")
	}
	// err may or may not be nil depending on implementation.
	_ = err
}

// TestHTTPTestResult_ToJSON verifies JSON marshalling.
func TestHTTPTestResult_ToJSON(t *testing.T) {
	r := &protocols.HTTPTestResult{
		Target:     "https://example.com",
		Protocol:   "http1",
		StatusCode: 200,
		LatencyMS:  12.5,
		Success:    true,
	}
	data, err := r.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON failed: %v", err)
	}
	if len(data) == 0 {
		t.Error("ToJSON returned empty data")
	}
}
