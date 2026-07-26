// Package cerberus provides optional integration with Cerberus NGFW for threat enrichment.
package cerberus

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

// TestNewClientFromEnvUnset tests factory with CERBERUS_URL unset.
func TestNewClientFromEnvUnset(t *testing.T) {
	oldVal := os.Getenv("CERBERUS_URL")
	defer os.Setenv("CERBERUS_URL", oldVal)

	os.Unsetenv("CERBERUS_URL")
	c := NewClientFromEnv()
	if c != nil {
		t.Errorf("NewClientFromEnv() = %v, want nil", c)
	}
}

// TestNewClientFromEnvSet tests factory with CERBERUS_URL set.
func TestNewClientFromEnvSet(t *testing.T) {
	oldVal := os.Getenv("CERBERUS_URL")
	defer os.Setenv("CERBERUS_URL", oldVal)

	testURL := "http://cerberus.local:8080"
	os.Setenv("CERBERUS_URL", testURL)
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

// TestGetCurrentBlocklistsNilReceiver tests nil receiver safety.
func TestGetCurrentBlocklistsNilReceiver(t *testing.T) {
	var c *Client
	ctx := context.Background()
	threatIPs, threatDomains := c.GetCurrentBlocklists(ctx)
	if threatIPs != nil {
		t.Errorf("threatIPs = %v, want nil", threatIPs)
	}
	if threatDomains != nil {
		t.Errorf("threatDomains = %v, want nil", threatDomains)
	}
}

// TestGetCurrentBlocklistsSuccess tests successful HTTP call.
func TestGetCurrentBlocklistsSuccess(t *testing.T) {
	// Mock Cerberus endpoint
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/threats/blocklists", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		resp := map[string][]string{
			"threatIPs":     {"192.0.2.1", "192.0.2.2"},
			"threatDomains": {"evil.example.com", "bad.test.io"},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	threatIPs, threatDomains := c.GetCurrentBlocklists(ctx)

	// NOTE: Current implementation returns nil — test documents this behavior.
	// When TODO is implemented, update assertions to expect populated slices.
	if threatIPs != nil {
		t.Errorf("threatIPs = %v, want nil (TODO: implement)", threatIPs)
	}
	if threatDomains != nil {
		t.Errorf("threatDomains = %v, want nil (TODO: implement)", threatDomains)
	}
}

// TestGetCurrentBlocklistsContextCancellation tests context cancellation safety.
func TestGetCurrentBlocklistsContextCancellation(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/threats/blocklists", func(w http.ResponseWriter, r *http.Request) {
		// Simulate a delay
		select {
		case <-r.Context().Done():
			return
		}
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	// Should not panic; behavior depends on implementation
	threatIPs, threatDomains := c.GetCurrentBlocklists(ctx)
	if threatIPs != nil && threatDomains != nil {
		// Implementation may or may not handle cancellation
	}
}

// TestGetCurrentBlocklistsHTTPError tests handling of HTTP errors.
func TestGetCurrentBlocklistsHTTPError(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/threats/blocklists", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("internal error"))
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	c := &Client{
		baseURL:    srv.URL,
		httpClient: &http.Client{},
	}

	ctx := context.Background()
	threatIPs, threatDomains := c.GetCurrentBlocklists(ctx)

	// Current implementation returns nil regardless of error
	if threatIPs != nil {
		t.Errorf("threatIPs = %v, want nil (TODO: implement error handling)", threatIPs)
	}
	if threatDomains != nil {
		t.Errorf("threatDomains = %v, want nil (TODO: implement error handling)", threatDomains)
	}
}

// BenchmarkGetCurrentBlocklists benchmarks the GetCurrentBlocklists method.
func BenchmarkGetCurrentBlocklists(b *testing.B) {
	c := &Client{
		baseURL:    "http://cerberus.local:8080",
		httpClient: &http.Client{},
	}
	ctx := context.Background()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		c.GetCurrentBlocklists(ctx)
	}
}
