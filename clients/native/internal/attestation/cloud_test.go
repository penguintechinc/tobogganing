package attestation

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCollectCloudIdentity_NoCloud_ReturnsNil(t *testing.T) {
	// On a non-cloud machine, should return nil with an error
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	cloud, err := collectCloudIdentity(ctx)
	if cloud != nil {
		// We're probably running on a cloud instance
		t.Logf("Cloud identity detected (running on cloud): provider=%s", cloud.Provider)
		return
	}
	if err == nil {
		t.Error("Expected error when no cloud provider detected")
	}
}

func TestIMDSGet_Timeout(t *testing.T) {
	// Server that never responds
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(5 * time.Second)
	}))
	defer srv.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	client := &http.Client{Timeout: 100 * time.Millisecond}
	_, err := imdsGet(ctx, client, srv.URL, nil)
	if err == nil {
		t.Error("Expected timeout error")
	}
}

func TestIMDSGet_Success(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		w.Write([]byte(`{"test": "data"}`))
	}))
	defer srv.Close()

	ctx := context.Background()
	client := &http.Client{Timeout: 5 * time.Second}
	body, err := imdsGet(ctx, client, srv.URL, nil)
	if err != nil {
		t.Fatalf("imdsGet() error: %v", err)
	}
	if string(body) != `{"test": "data"}` {
		t.Errorf("Unexpected body: %s", body)
	}
}

func TestIMDSGet_WithHeaders(t *testing.T) {
	var receivedHeader string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedHeader = r.Header.Get("Metadata-Flavor")
		w.WriteHeader(200)
		w.Write([]byte("ok"))
	}))
	defer srv.Close()

	ctx := context.Background()
	client := &http.Client{Timeout: 5 * time.Second}
	_, err := imdsGet(ctx, client, srv.URL, map[string]string{"Metadata-Flavor": "Google"})
	if err != nil {
		t.Fatalf("imdsGet() error: %v", err)
	}
	if receivedHeader != "Google" {
		t.Errorf("Expected header 'Google', got %q", receivedHeader)
	}
}

func TestExtractGCPRegion(t *testing.T) {
	tests := []struct {
		zone     string
		expected string
	}{
		{"projects/123/zones/us-central1-a", "us-central1"},
		{"us-east1-b", "us-east1"},
		{"europe-west1-c", "europe-west1"},
	}

	for _, tc := range tests {
		got := extractGCPRegion(tc.zone)
		if got != tc.expected {
			t.Errorf("extractGCPRegion(%q) = %q, want %q", tc.zone, got, tc.expected)
		}
	}
}
