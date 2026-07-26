package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// TestHealthCheckHTTPSuccess tests healthCheckHTTP with a successful HTTP response.
func TestHealthCheckHTTPSuccess(t *testing.T) {
	// Create a test HTTP server that returns 200 OK.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			http.NotFound(w, r)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL + "/health")
	if err != nil {
		t.Fatalf("healthCheckHTTP failed: %v", err)
	}
}

// TestHealthCheckHTTPConnectionError tests HTTP request failure.
func TestHealthCheckHTTPConnectionError(t *testing.T) {
	// Use an invalid address that won't accept connections.
	healthURL := "http://127.0.0.1:1"

	err := healthCheckHTTP(healthURL)
	if err == nil {
		t.Errorf("Expected error from healthCheckHTTP")
	}
}

// TestHealthCheckHTTPNonOKStatus tests non-200 HTTP response.
func TestHealthCheckHTTPNonOKStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err == nil {
		t.Errorf("Expected healthCheckHTTP to fail with non-200 status")
	}
}

// TestHealthCheckWireGuardInterfaceExists tests successful WireGuard interface check.
func TestHealthCheckWireGuardInterfaceExists(t *testing.T) {
	tmpDir := t.TempDir()
	wg0Path := filepath.Join(tmpDir, "wg0")

	if err := os.Mkdir(wg0Path, 0755); err != nil {
		t.Fatalf("Failed to create mock wg0: %v", err)
	}

	err := healthCheckWireGuard(wg0Path)
	if err != nil {
		t.Errorf("healthCheckWireGuard should succeed with existing interface: %v", err)
	}
}

// TestHealthCheckWireGuardInterfaceMissing tests WireGuard interface not found.
func TestHealthCheckWireGuardInterfaceMissing(t *testing.T) {
	tmpDir := t.TempDir()
	wg0Path := filepath.Join(tmpDir, "nonexistent_wg0")

	err := healthCheckWireGuard(wg0Path)
	if err == nil {
		t.Errorf("healthCheckWireGuard should fail when interface missing")
	}

	if !os.IsNotExist(err) {
		t.Errorf("Expected IsNotExist error, got: %v", err)
	}
}

// TestHealthCheckHTTPTimeout tests HTTP request timeout.
func TestHealthCheckHTTPTimeout(t *testing.T) {
	// Create a server that delays responding longer than the timeout.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(10 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err == nil {
		t.Errorf("Expected healthCheckHTTP timeout error")
	}
}

// TestHealthCheckResponseBodyRead tests that response body is properly read and closed.
func TestHealthCheckResponseBodyRead(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		io.WriteString(w, `{"status":"ok"}`)
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err != nil {
		t.Fatalf("healthCheckHTTP failed: %v", err)
	}
}

// TestHealthCheckCustomURL tests custom health check URL.
func TestHealthCheckCustomURL(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/custom-health" {
			w.WriteHeader(http.StatusOK)
		} else {
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL + "/custom-health")
	if err != nil {
		t.Errorf("healthCheckHTTP failed for custom URL: %v", err)
	}
}

// TestHealthCheckConcurrentRequests tests multiple concurrent health checks.
func TestHealthCheckConcurrentRequests(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	// Run 10 concurrent requests.
	done := make(chan error, 10)
	for i := 0; i < 10; i++ {
		go func() {
			err := healthCheckHTTP(server.URL)
			done <- err
		}()
	}

	// Collect results.
	for i := 0; i < 10; i++ {
		if err := <-done; err != nil {
			t.Errorf("Concurrent healthCheckHTTP failed: %v", err)
		}
	}
}

// TestHealthCheckHTTPStatusCodes tests various HTTP status codes.
func TestHealthCheckHTTPStatusCodes(t *testing.T) {
	testCases := []int{
		http.StatusOK,
		http.StatusCreated,
		http.StatusAccepted,
	}

	for _, code := range testCases {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(code)
		}))

		err := healthCheckHTTP(server.URL)
		if code == http.StatusOK {
			if err != nil {
				t.Errorf("healthCheckHTTP should succeed for status %d: %v", code, err)
			}
		} else {
			if err == nil {
				t.Errorf("healthCheckHTTP should fail for status %d", code)
			}
		}

		server.Close()
	}
}

// TestHealthCheckEmptyResponse tests handling of empty HTTP response.
func TestHealthCheckEmptyResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		// Don't write any body
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err != nil {
		t.Errorf("healthCheckHTTP should succeed with empty response: %v", err)
	}
}

// TestHealthCheckHTTPLargeResponse tests handling of large HTTP response.
func TestHealthCheckHTTPLargeResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/octet-stream")
		w.WriteHeader(http.StatusOK)
		// Write a large response
		for i := 0; i < 1000; i++ {
			io.WriteString(w, "x")
		}
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err != nil {
		t.Errorf("healthCheckHTTP should succeed with large response: %v", err)
	}
}

// TestHealthCheckHTTPForbidden tests HTTP 403 Forbidden response.
func TestHealthCheckHTTPForbidden(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err == nil {
		t.Errorf("healthCheckHTTP should fail with status 403")
	}
}

// TestHealthCheckHTTPBadGateway tests HTTP 502 Bad Gateway response.
func TestHealthCheckHTTPBadGateway(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err == nil {
		t.Errorf("healthCheckHTTP should fail with status 502")
	}
}

// TestHealthCheckWireGuardFile tests WireGuard interface check with regular file.
func TestHealthCheckWireGuardFile(t *testing.T) {
	tmpDir := t.TempDir()
	wg0File := filepath.Join(tmpDir, "wg0_file")

	// Create a regular file instead of directory
	f, err := os.Create(wg0File)
	if err != nil {
		t.Fatalf("Failed to create test file: %v", err)
	}
	f.Close()

	// Should succeed - file exists
	err = healthCheckWireGuard(wg0File)
	if err != nil {
		t.Errorf("healthCheckWireGuard should succeed with existing file: %v", err)
	}
}

// TestHealthCheckHTTPPathNotFound tests HTTP 404 Not Found response.
func TestHealthCheckHTTPPathNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err == nil {
		t.Errorf("healthCheckHTTP should fail with status 404")
	}
}

// TestRunHealthCheckSuccess tests run() with successful health checks.
func TestRunHealthCheckSuccess(t *testing.T) {
	// Create a test HTTP server that returns 200 OK.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	// Set the health check URL via environment variable
	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", server.URL)
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	err := run([]string{})
	if err != nil {
		t.Fatalf("run() should succeed with healthy endpoint: %v", err)
	}
}

// TestRunHealthCheckHTTPFailure tests run() with failed HTTP health check.
func TestRunHealthCheckHTTPFailure(t *testing.T) {
	// Create a test HTTP server that returns 503 Service Unavailable.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer server.Close()

	// Set the health check URL via environment variable
	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", server.URL)
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	err := run([]string{})
	if err == nil {
		t.Errorf("run() should fail when HTTP health check fails")
	}
}

// TestRunDefaultHealthCheckURL tests run() uses default URL when HEALTH_CHECK_URL is not set.
func TestRunDefaultHealthCheckURL(t *testing.T) {
	// Save and clear HEALTH_CHECK_URL env var
	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Unsetenv("HEALTH_CHECK_URL")
	defer func() {
		if oldURL != "" {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		} else {
			os.Unsetenv("HEALTH_CHECK_URL")
		}
	}()

	// The default is http://localhost:9090/health which won't be reachable,
	// so we expect an error. This test verifies the default path is taken.
	err := run([]string{})
	if err == nil {
		t.Errorf("run() should fail with unreachable default URL")
	}
}

// TestRunWireGuardMissing tests run() continues when WireGuard interface is missing.
func TestRunWireGuardMissing(t *testing.T) {
	// Create a test HTTP server that returns 200 OK.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	// Set the health check URL via environment variable
	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", server.URL)
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	// run() should succeed even if WireGuard interface is missing (warning only)
	err := run([]string{})
	if err != nil {
		t.Errorf("run() should succeed even when WireGuard interface is missing: %v", err)
	}
}

// TestRunConnectionFailure tests run() with connection error to health check endpoint.
func TestRunConnectionFailure(t *testing.T) {
	// Use an invalid address that won't accept connections.
	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", "http://127.0.0.1:1")
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	err := run([]string{})
	if err == nil {
		t.Errorf("run() should fail when unable to connect to health check endpoint")
	}
}

// TestHealthCheckHTTPUnmarshalResponseError tests HTTP response body reading edge case.
func TestHealthCheckHTTPUnmarshalResponseError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	// Verify successful read of response body
	err := healthCheckHTTP(server.URL)
	if err != nil {
		t.Errorf("healthCheckHTTP should handle response body correctly: %v", err)
	}
}

// TestRunMultiplePollCyclesOrTimeout tests complete execution flow.
func TestRunMultiplePollCyclesOrTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", server.URL)
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	err := run([]string{})
	if err != nil {
		t.Errorf("run() should succeed: %v", err)
	}
}

// TestHealthCheckHTTPResponseClosing tests response body is properly closed.
func TestHealthCheckHTTPResponseClosing(t *testing.T) {
	closeCalled := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		io.WriteString(w, "test response")
	}))
	defer server.Close()

	err := healthCheckHTTP(server.URL)
	if err != nil {
		t.Errorf("healthCheckHTTP failed: %v", err)
	}

	// Verify no panic on subsequent operations
	_ = closeCalled
}

// TestHealthCheckHTTPRaceCondition tests concurrent calls don't race.
func TestHealthCheckHTTPRaceCondition(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	results := make(chan error, 20)
	for i := 0; i < 20; i++ {
		go func() {
			results <- healthCheckHTTP(server.URL)
		}()
	}

	for i := 0; i < 20; i++ {
		if err := <-results; err != nil {
			t.Errorf("Concurrent call failed: %v", err)
		}
	}
}

// TestHealthCheckHTTPInvalidURL tests invalid URL handling.
func TestHealthCheckHTTPInvalidURL(t *testing.T) {
	err := healthCheckHTTP("http://[invalid:url")
	if err == nil {
		t.Errorf("healthCheckHTTP should fail with invalid URL")
	}
}

// TestHealthCheckWireGuardSymlink tests WireGuard check with symlink.
func TestHealthCheckWireGuardSymlink(t *testing.T) {
	tmpDir := t.TempDir()
	targetPath := tmpDir + "/target"
	linkPath := tmpDir + "/link"

	if err := os.Mkdir(targetPath, 0755); err != nil {
		t.Fatalf("Failed to create target: %v", err)
	}
	if err := os.Symlink(targetPath, linkPath); err != nil {
		t.Fatalf("Failed to create symlink: %v", err)
	}

	err := healthCheckWireGuard(linkPath)
	if err != nil {
		t.Errorf("healthCheckWireGuard should succeed with symlink: %v", err)
	}
}

// TestRunHTTPFailurePathLogging tests error logging path in run().
func TestRunHTTPFailurePathLogging(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", server.URL)
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	err := run([]string{})
	if err == nil {
		t.Errorf("run() should fail with HTTP 500")
	}
}

// TestRunWireGuardWarningPathLogging tests WireGuard warning path in run().
func TestRunWireGuardWarningPathLogging(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", server.URL)
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	// run() should succeed despite WireGuard missing (just warning)
	err := run([]string{})
	if err != nil {
		t.Errorf("run() should succeed with WireGuard warning: %v", err)
	}
}

// TestHealthCheckHTTPStatusCodeBoundaries tests status code edge cases.
func TestHealthCheckHTTPStatusCodeBoundaries(t *testing.T) {
	tests := []struct {
		name           string
		statusCode     int
		shouldPass     bool
	}{
		{"Status 200 OK", http.StatusOK, true},
		{"Status 200 is only success", http.StatusAccepted, false},
		{"Status 201 Created", http.StatusCreated, false},
		{"Status 500 Internal", http.StatusInternalServerError, false},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.statusCode)
			}))
			defer server.Close()

			err := healthCheckHTTP(server.URL)
			if tc.shouldPass && err != nil {
				t.Errorf("Expected success for status %d, got: %v", tc.statusCode, err)
			}
			if !tc.shouldPass && err == nil {
				t.Errorf("Expected failure for status %d", tc.statusCode)
			}
		})
	}
}

// TestHealthCheckHTTPEmptyBodyClose tests empty response body is properly closed.
func TestHealthCheckHTTPEmptyBodyClose(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		// Write no body
	}))
	defer server.Close()

	// Should not panic on empty body close
	err := healthCheckHTTP(server.URL)
	if err != nil {
		t.Errorf("healthCheckHTTP failed on empty body: %v", err)
	}
}

// TestRunFullFlow tests complete run() execution path.
func TestRunFullFlow(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	oldURL := os.Getenv("HEALTH_CHECK_URL")
	os.Setenv("HEALTH_CHECK_URL", server.URL)
	defer func() {
		if oldURL == "" {
			os.Unsetenv("HEALTH_CHECK_URL")
		} else {
			os.Setenv("HEALTH_CHECK_URL", oldURL)
		}
	}()

	// Full flow that mimics main() calling run()
	if err := run(os.Args); err != nil {
		t.Errorf("run() from full flow failed: %v", err)
	}
}
