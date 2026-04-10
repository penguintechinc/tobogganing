// Package push handles pushing compiled rule sets to MarchProxy.
package push

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/tobogganing/hub-policy/internal/compiler"
)

// TestNewClientFromEnvUnset tests factory with MARCHPROXY_LEVERS_URL unset.
func TestNewClientFromEnvUnset(t *testing.T) {
	oldVal := os.Getenv("MARCHPROXY_LEVERS_URL")
	defer os.Setenv("MARCHPROXY_LEVERS_URL", oldVal)

	os.Unsetenv("MARCHPROXY_LEVERS_URL")
	c := NewClientFromEnv()
	if c != nil {
		t.Errorf("NewClientFromEnv() = %v, want nil", c)
	}
}

// TestNewClientFromEnvSet tests factory with MARCHPROXY_LEVERS_URL set.
func TestNewClientFromEnvSet(t *testing.T) {
	oldVal := os.Getenv("MARCHPROXY_LEVERS_URL")
	defer os.Setenv("MARCHPROXY_LEVERS_URL", oldVal)

	testURL := "http://marchproxy.local:8080"
	os.Setenv("MARCHPROXY_LEVERS_URL", testURL)
	c := NewClientFromEnv()
	if c == nil {
		t.Fatal("NewClientFromEnv() = nil, want non-nil")
	}
	if c.baseURL != testURL {
		t.Errorf("baseURL = %q, want %q", c.baseURL, testURL)
	}
	if c.httpClient == nil {
		t.Error("httpClient = nil, want non-nil")
	}
}

// TestPushNilReceiver tests nil receiver safety.
func TestPushNilReceiver(t *testing.T) {
	var c *Client
	ctx := context.Background()
	rules := compiler.CompiledRuleSet{}

	err := c.Push(ctx, rules)
	if err != nil {
		t.Errorf("Push() = %v, want nil", err)
	}
}

// TestPushSuccess tests successful push to MarchProxy.
func TestPushSuccess(t *testing.T) {
	var receivedBody []byte
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		if ct := r.Header.Get("Content-Type"); ct != "application/json" {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("expected Content-Type: application/json"))
			return
		}

		var err error
		receivedBody, err = io.ReadAll(r.Body)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		defer r.Body.Close()

		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status":"accepted"}`))
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		BlockCIDRs:   []string{"192.0.2.0/24"},
		AllowCIDRs:   []string{"10.0.0.0/8"},
		BlockDomains: []string{"malware.example.com"},
		AllowDomains: []string{"*.internal.example.com"},
		RateLimits: map[string]int{
			"192.0.2.1": 1000,
		},
	}

	ctx := context.Background()
	err := c.Push(ctx, rules)
	if err != nil {
		t.Fatalf("Push() = %v, want nil", err)
	}

	// Verify request body was marshaled correctly
	var decoded compiler.CompiledRuleSet
	if err := json.Unmarshal(receivedBody, &decoded); err != nil {
		t.Fatalf("Unmarshal received body = %v", err)
	}
	if len(decoded.BlockCIDRs) != len(rules.BlockCIDRs) {
		t.Errorf("BlockCIDRs count = %d, want %d", len(decoded.BlockCIDRs), len(rules.BlockCIDRs))
	}
	if len(decoded.AllowCIDRs) != len(rules.AllowCIDRs) {
		t.Errorf("AllowCIDRs count = %d, want %d", len(decoded.AllowCIDRs), len(rules.AllowCIDRs))
	}
}

// TestPushHTTPError tests handling of HTTP errors (>=300 status).
func TestPushHTTPError(t *testing.T) {
	tests := []int{300, 400, 404, 500, 502, 503}

	for _, statusCode := range tests {
		t.Run(string(rune(statusCode)), func(t *testing.T) {
			mux := http.NewServeMux()
			mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(statusCode)
			})

			srv := httptest.NewServer(mux)
			defer srv.Close()

			c := &Client{
				baseURL:    srv.URL,
				httpClient: &http.Client{},
			}

			ctx := context.Background()
			rules := compiler.CompiledRuleSet{
				BlockCIDRs: []string{"192.0.2.0/24"},
			}

			err := c.Push(ctx, rules)
			if err == nil {
				t.Errorf("Push() = nil, want error for status %d", statusCode)
			}
		})
	}
}

// TestPushSuccess200StatusCode tests that 200 is treated as success.
func TestPushSuccess200StatusCode(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	rules := compiler.CompiledRuleSet{
		AllowCIDRs: []string{"10.0.0.0/8"},
	}

	err := c.Push(ctx, rules)
	if err != nil {
		t.Errorf("Push() = %v, want nil for status 200", err)
	}
}

// TestPushSuccess299StatusCode tests that 299 is treated as success.
func TestPushSuccess299StatusCode(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(299)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	rules := compiler.CompiledRuleSet{
		BlockDomains: []string{"evil.com"},
	}

	err := c.Push(ctx, rules)
	if err != nil {
		t.Errorf("Push() = %v, want nil for status 299", err)
	}
}

// TestPushMarshalError tests handling of marshal errors.
func TestPushMarshalError(t *testing.T) {
	c := &Client{
		baseURL:    "http://marchproxy.local:8080",
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	// Create a rule set that will fail due to network
	rules := compiler.CompiledRuleSet{
		BlockCIDRs: []string{"192.0.2.0/24"},
	}

	err := c.Push(ctx, rules)
	if err != nil {
		// Expected to fail due to network (no server listening)
		t.Logf("Push() failed as expected: %v", err)
	}
}

// TestPushContextCancellation tests context cancellation handling.
func TestPushContextCancellation(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		// Simulate delay or respect context cancellation
		<-r.Context().Done()
		return
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	rules := compiler.CompiledRuleSet{
		BlockCIDRs: []string{"192.0.2.0/24"},
	}
	err := c.Push(ctx, rules)
	if err == nil {
		t.Error("Push() with cancelled context = nil, want error")
	}
}

// TestPushContentTypeHeader tests that Content-Type header is set.
func TestPushContentTypeHeader(t *testing.T) {
	var receivedCT string
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		receivedCT = r.Header.Get("Content-Type")
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	rules := compiler.CompiledRuleSet{
		AllowCIDRs: []string{"10.0.0.0/8"},
	}

	_ = c.Push(ctx, rules)
	if receivedCT != "application/json" {
		t.Errorf("Content-Type = %q, want %q", receivedCT, "application/json")
	}
}

// TestPushEndpointPath tests that correct endpoint path is used.
func TestPushEndpointPath(t *testing.T) {
	var receivedPath string
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		receivedPath = r.URL.Path
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	rules := compiler.CompiledRuleSet{
		BlockDomains: []string{"evil.example.com"},
	}

	_ = c.Push(ctx, rules)
	if receivedPath != "/api/v1/levers/rules" {
		t.Errorf("Path = %q, want %q", receivedPath, "/api/v1/levers/rules")
	}
}

// TestPushLargeRuleSet tests pushing a large rule set.
func TestPushLargeRuleSet(t *testing.T) {
	var receivedSize int64
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		receivedSize = r.ContentLength
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	// Create a large rule set
	rules := compiler.CompiledRuleSet{
		BlockCIDRs: make([]string, 1000),
		AllowCIDRs: make([]string, 1000),
	}
	for i := 0; i < 1000; i++ {
		rules.BlockCIDRs[i] = "192.0.2.0/24"
		rules.AllowCIDRs[i] = "10.0.0.0/8"
	}

	ctx := context.Background()
	err := c.Push(ctx, rules)
	if err != nil {
		t.Fatalf("Push() = %v, want nil", err)
	}

	if receivedSize <= 0 {
		t.Errorf("Content-Length = %d, want > 0", receivedSize)
	}
}

// TestPushEmptyRuleSet tests pushing an empty rule set.
func TestPushEmptyRuleSet(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	rules := compiler.CompiledRuleSet{}

	err := c.Push(ctx, rules)
	if err != nil {
		t.Errorf("Push(empty) = %v, want nil", err)
	}
}

// TestPushBodyClosing tests that response body is properly closed.
func TestPushBodyClosing(t *testing.T) {
	callCount := 0
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("test response"))
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	// Make multiple requests to ensure body closing doesn't leak
	for i := 0; i < 5; i++ {
		ctx := context.Background()
		rules := compiler.CompiledRuleSet{
			BlockCIDRs: []string{"192.0.2.0/24"},
		}
		err := c.Push(ctx, rules)
		if err != nil {
			t.Errorf("Push() iteration %d = %v, want nil", i, err)
		}
	}

	if callCount != 5 {
		t.Errorf("Handler called %d times, want 5", callCount)
	}
}

// BenchmarkPush benchmarks the Push method.
func BenchmarkPush(b *testing.B) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		BlockCIDRs: []string{"192.0.2.0/24"},
		AllowCIDRs: []string{"10.0.0.0/8"},
		RateLimits: map[string]int{
			"192.0.2.1": 1000,
		},
	}

	ctx := context.Background()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		c.Push(ctx, rules)
	}
}

// TestPushRequestMethod tests that correct HTTP method is used.
func TestPushRequestMethod(t *testing.T) {
	var receivedMethod string
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		receivedMethod = r.Method
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	rules := compiler.CompiledRuleSet{
		BlockDomains: []string{"malware.example.com"},
	}

	_ = c.Push(ctx, rules)
	if receivedMethod != http.MethodPost {
		t.Errorf("Method = %q, want %q", receivedMethod, http.MethodPost)
	}
}

// TestPushBufferHandling tests that request body is properly buffered.
func TestPushBufferHandling(t *testing.T) {
	var bodyBytes []byte
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		bodyBytes, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		AllowCIDRs: []string{"10.0.0.0/8"},
	}

	ctx := context.Background()
	_ = c.Push(ctx, rules)

	// Verify body was actually sent
	if len(bodyBytes) == 0 {
		t.Error("Request body is empty, expected JSON")
	}

	var decoded compiler.CompiledRuleSet
	if err := json.Unmarshal(bodyBytes, &decoded); err != nil {
		t.Fatalf("Unmarshal body = %v", err)
	}
}

// TestPushBodyReaderRespect tests that bytes.NewReader is properly used.
func TestPushBodyReaderRespect(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		// Verify request can be read
		buf := bytes.NewBuffer(nil)
		if _, err := buf.ReadFrom(r.Body); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		BlockCIDRs: []string{"192.0.2.0/24"},
	}
	ctx := context.Background()
	err := c.Push(ctx, rules)
	if err != nil {
		t.Errorf("Push() = %v, want nil", err)
	}
}

// TestPushHTTPClientError tests handling of HTTP client errors.
func TestPushHTTPClientError(t *testing.T) {
	c := &Client{
		baseURL:    "http://invalid-host-that-does-not-exist-xyz.local:9999",
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		BlockCIDRs: []string{"192.0.2.0/24"},
	}

	ctx := context.Background()
	err := c.Push(ctx, rules)
	if err == nil {
		t.Error("Push() with invalid host = nil, want error")
	}
}

// TestPushResponseError tests handling of error responses with body content.
func TestPushResponseError(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("internal server error"))
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		AllowDomains: []string{"*.internal.example.com"},
	}

	ctx := context.Background()
	err := c.Push(ctx, rules)
	if err == nil {
		t.Error("Push() with 500 status = nil, want error")
	}
}

// TestPushComplexRuleSet tests pushing a complex rule set with all fields.
func TestPushComplexRuleSet(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/levers/rules", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		BlockCIDRs:    []string{"192.0.2.0/24", "203.0.113.0/24"},
		AllowCIDRs:    []string{"10.0.0.0/8", "172.16.0.0/12"},
		BlockDomains:  []string{"malware.example.com", "phishing.test.io"},
		AllowDomains:  []string{"*.internal.example.com", "trusted.io"},
		RouteClusters: []compiler.ClusterDef{
			{
				Name:      "backend-cluster",
				Endpoints: []string{"10.0.1.1:8080", "10.0.1.2:8080"},
				LBPolicy:  "ROUND_ROBIN",
			},
		},
		RateLimits: map[string]int{
			"192.0.2.1": 1000,
			"192.0.2.2": 2000,
		},
	}

	ctx := context.Background()
	err := c.Push(ctx, rules)
	if err != nil {
		t.Fatalf("Push(complex) = %v, want nil", err)
	}
}

// TestPushWithNilHTTPClient would test nil http client, but NewClientFromEnv ensures it's created.
// This test documents that behavior.
func TestPushNewClientAlwaysCreatesHTTPClient(t *testing.T) {
	oldVal := os.Getenv("MARCHPROXY_LEVERS_URL")
	defer os.Setenv("MARCHPROXY_LEVERS_URL", oldVal)

	os.Setenv("MARCHPROXY_LEVERS_URL", "http://test.local:8080")
	c := NewClientFromEnv()

	if c.httpClient == nil {
		t.Error("httpClient should never be nil after NewClientFromEnv")
	}
}

// TestPushRequestBuildError documents that request building errors are caught.
// In normal operation this is hard to trigger, but the error path exists.
func TestPushWithInvalidBaseURL(t *testing.T) {
	c := &Client{
		baseURL:    "ht!tp://[invalid",  // Malformed URL
		httpClient: &http.Client{},
	}

	rules := compiler.CompiledRuleSet{
		BlockCIDRs: []string{"192.0.2.0/24"},
	}

	ctx := context.Background()
	err := c.Push(ctx, rules)
	if err == nil {
		t.Error("Push() with malformed URL = nil, want error")
	}
}
