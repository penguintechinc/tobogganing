package ports

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// ─── NewConfigClient ──────────────────────────────────────────────────────────

func TestNewConfigClient(t *testing.T) {
	cc := NewConfigClient("http://manager:8080", "mytoken", "headend-1", "cluster-1")
	if cc == nil {
		t.Fatal("expected non-nil config client")
	}
	if cc.managerURL != "http://manager:8080" {
		t.Errorf("unexpected managerURL: %s", cc.managerURL)
	}
	if cc.authToken != "mytoken" {
		t.Errorf("unexpected authToken: %s", cc.authToken)
	}
	if cc.headendID != "headend-1" {
		t.Errorf("unexpected headendID: %s", cc.headendID)
	}
	if cc.clusterID != "cluster-1" {
		t.Errorf("unexpected clusterID: %s", cc.clusterID)
	}
}

// ─── FetchConfig ─────────────────────────────────────────────────────────────

func TestFetchConfig_Success(t *testing.T) {
	config := PortConfig{
		HeadendID:  "headend-1",
		ClusterID:  "cluster-1",
		TCPRanges:  "8000-8100",
		UDPRanges:  "9000-9100",
		UpdatedAt:  "2025-01-01T00:00:00Z",
	}
	body, _ := json.Marshal(config)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer mytoken" {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(body)
	}))
	defer ts.Close()

	cc := NewConfigClient(ts.URL, "mytoken", "headend-1", "cluster-1")
	cfg, err := cc.FetchConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.HeadendID != "headend-1" {
		t.Errorf("unexpected HeadendID: %s", cfg.HeadendID)
	}
	if cfg.TCPRanges != "8000-8100" {
		t.Errorf("unexpected TCPRanges: %s", cfg.TCPRanges)
	}
}

func TestFetchConfig_HTTPError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer ts.Close()

	cc := NewConfigClient(ts.URL, "tok", "h1", "c1")
	_, err := cc.FetchConfig()
	if err == nil {
		t.Error("expected error for non-200 response")
	}
}

func TestFetchConfig_ConnectionRefused(t *testing.T) {
	cc := NewConfigClient("http://127.0.0.1:1", "tok", "h1", "c1")
	_, err := cc.FetchConfig()
	if err == nil {
		t.Error("expected error for connection refused")
	}
}

func TestFetchConfig_InvalidJSON(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not-json"))
	}))
	defer ts.Close()

	cc := NewConfigClient(ts.URL, "tok", "h1", "c1")
	_, err := cc.FetchConfig()
	if err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestFetchConfig_IncludesAuthHeader(t *testing.T) {
	var gotAuth string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		cfg := PortConfig{HeadendID: "h1", TCPRanges: "8080"}
		body, _ := json.Marshal(cfg)
		w.Write(body)
	}))
	defer ts.Close()

	cc := NewConfigClient(ts.URL, "secret-token", "h1", "c1")
	cc.FetchConfig()

	if gotAuth != "Bearer secret-token" {
		t.Errorf("unexpected auth header: %s", gotAuth)
	}
}

func TestFetchConfig_URLBuilding(t *testing.T) {
	var gotPath string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.String()
		cfg := PortConfig{HeadendID: "myheadend", TCPRanges: "8080"}
		body, _ := json.Marshal(cfg)
		w.Write(body)
	}))
	defer ts.Close()

	cc := NewConfigClient(ts.URL, "tok", "myheadend", "mycluster")
	cc.FetchConfig()

	expectedPath := "/api/v1/headend/myheadend/ports?cluster_id=mycluster"
	if gotPath != expectedPath {
		t.Errorf("unexpected path: %s, want: %s", gotPath, expectedPath)
	}
}

// ─── ValidateConfig ───────────────────────────────────────────────────────────

func TestValidateConfig_Valid(t *testing.T) {
	cc := NewConfigClient("http://x", "t", "headend-1", "cluster-1")
	cfg := &PortConfig{
		HeadendID: "headend-1",
		TCPRanges: "8000-8100",
	}
	if err := cc.ValidateConfig(cfg); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestValidateConfig_HeadendIDMismatch(t *testing.T) {
	cc := NewConfigClient("http://x", "t", "headend-1", "cluster-1")
	cfg := &PortConfig{
		HeadendID: "headend-2", // wrong
		TCPRanges: "8000-8100",
	}
	if err := cc.ValidateConfig(cfg); err == nil {
		t.Error("expected error for headend ID mismatch")
	}
}

func TestValidateConfig_NoPortRanges(t *testing.T) {
	cc := NewConfigClient("http://x", "t", "headend-1", "cluster-1")
	cfg := &PortConfig{
		HeadendID: "headend-1",
		// no TCP or UDP ranges
	}
	if err := cc.ValidateConfig(cfg); err == nil {
		t.Error("expected error for empty port ranges")
	}
}

func TestValidateConfig_OnlyUDPRanges(t *testing.T) {
	cc := NewConfigClient("http://x", "t", "headend-1", "cluster-1")
	cfg := &PortConfig{
		HeadendID: "headend-1",
		UDPRanges: "9000-9100",
	}
	// UDP ranges alone are fine
	if err := cc.ValidateConfig(cfg); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}
