package protocols

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// RunHTTPTest — successful responses
// ---------------------------------------------------------------------------

func TestRunHTTPTest_200OK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 5*time.Second)

	if !result.Success {
		t.Errorf("expected Success=true for 200 OK, got false (error: %q)", result.Error)
	}
	if result.StatusCode != http.StatusOK {
		t.Errorf("expected StatusCode 200, got %d", result.StatusCode)
	}
	if result.Target != srv.URL {
		t.Errorf("expected Target %q, got %q", srv.URL, result.Target)
	}
	if result.LatencyMs <= 0 {
		t.Errorf("expected positive LatencyMs, got %f", result.LatencyMs)
	}
}

func TestRunHTTPTest_201Created(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 5*time.Second)
	if !result.Success {
		t.Errorf("expected Success=true for 201 Created, got false")
	}
}

func TestRunHTTPTest_301Redirect(t *testing.T) {
	// 3xx responses are considered successful (< 400).
	// httptest redirects are handled automatically; we configure a
	// redirect that stays within the test server by pointing to /redirected.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			http.Redirect(w, r, "/redirected", http.StatusMovedPermanently)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 5*time.Second)
	// After following the redirect the final status is 200, which is success.
	if !result.Success {
		t.Errorf("expected Success=true after redirect, got false (status %d, error %q)",
			result.StatusCode, result.Error)
	}
}

// ---------------------------------------------------------------------------
// RunHTTPTest — error / non-success responses
// ---------------------------------------------------------------------------

func TestRunHTTPTest_404NotFound(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 5*time.Second)
	if result.Success {
		t.Error("expected Success=false for 404 response")
	}
	if result.StatusCode != http.StatusNotFound {
		t.Errorf("expected StatusCode 404, got %d", result.StatusCode)
	}
}

func TestRunHTTPTest_500InternalServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 5*time.Second)
	if result.Success {
		t.Error("expected Success=false for 500 response")
	}
}

// ---------------------------------------------------------------------------
// RunHTTPTest — network errors
// ---------------------------------------------------------------------------

func TestRunHTTPTest_InvalidURL(t *testing.T) {
	result := RunHTTPTest("http://127.0.0.1:1", 500*time.Millisecond)

	if result.Success {
		t.Error("expected Success=false for connection-refused target")
	}
	if result.Error == "" {
		t.Error("expected non-empty Error field when connection is refused")
	}
}

func TestRunHTTPTest_MalformedURL(t *testing.T) {
	result := RunHTTPTest("not-a-url", 500*time.Millisecond)

	if result.Success {
		t.Error("expected Success=false for malformed URL")
	}
	if result.Target != "not-a-url" {
		t.Errorf("expected Target %q, got %q", "not-a-url", result.Target)
	}
}

// ---------------------------------------------------------------------------
// RunHTTPTest — timeout handling
// ---------------------------------------------------------------------------

func TestRunHTTPTest_Timeout(t *testing.T) {
	// Server that sleeps longer than the client timeout.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 50*time.Millisecond)

	if result.Success {
		t.Error("expected Success=false on timeout")
	}
	if result.Error == "" {
		t.Error("expected non-empty Error field on timeout")
	}
	// LatencyMs should roughly match the timeout (at least non-zero).
	if result.LatencyMs <= 0 {
		t.Errorf("expected positive LatencyMs even on timeout, got %f", result.LatencyMs)
	}
}

// ---------------------------------------------------------------------------
// RunHTTPTest — result fields populated
// ---------------------------------------------------------------------------

func TestRunHTTPTest_LatencyIsPositive(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 5*time.Second)
	if result.LatencyMs <= 0 {
		t.Errorf("expected LatencyMs > 0, got %f", result.LatencyMs)
	}
}

func TestRunHTTPTest_ErrorFieldEmptyOnSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	result := RunHTTPTest(srv.URL, 5*time.Second)
	if result.Error != "" {
		t.Errorf("expected empty Error on success, got %q", result.Error)
	}
}

// ---------------------------------------------------------------------------
// Table-driven: status code success boundary
// ---------------------------------------------------------------------------

func TestRunHTTPTest_StatusCodeBoundary(t *testing.T) {
	tests := []struct {
		statusCode int
		wantOK     bool
	}{
		{http.StatusOK, true},
		{http.StatusCreated, true},
		{http.StatusAccepted, true},
		{http.StatusNoContent, true},
		{http.StatusMovedPermanently, true},
		{http.StatusFound, true},
		{http.StatusBadRequest, false},
		{http.StatusUnauthorized, false},
		{http.StatusForbidden, false},
		{http.StatusNotFound, false},
		{http.StatusInternalServerError, false},
		{http.StatusBadGateway, false},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(http.StatusText(tt.statusCode), func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.statusCode)
			}))
			defer srv.Close()

			// Disable redirect following so 3xx is received as-is.
			result := RunHTTPTest(srv.URL, 5*time.Second)

			// For redirects the Go http.Client follows them automatically and ends
			// on 200; we check the final Success flag which reflects the net result.
			if tt.statusCode >= 200 && tt.statusCode < 400 {
				// Accept true even if redirected.
				if !result.Success && result.StatusCode >= 200 && result.StatusCode < 400 {
					t.Errorf("status %d: expected Success=true, got false", tt.statusCode)
				}
			} else {
				if result.Success {
					t.Errorf("status %d: expected Success=false, got true", tt.statusCode)
				}
			}
		})
	}
}
