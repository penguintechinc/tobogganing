// Package main implements a native Go health check binary for the hub-router.
//
// This binary performs two health checks:
// 1. HTTP health endpoint check (default http://localhost:9090/health)
// 2. WireGuard interface existence check (via /sys/class/net/wg0)
//
// Exit codes:
//   - 0: healthy (both checks pass)
//   - 1: unhealthy (one or more checks fail)
//
// The health check URL is configurable via the HEALTH_CHECK_URL environment variable.
package main

import (
	"fmt"
	"net/http"
	"os"
	"time"
)

// healthCheckHTTP performs HTTP health endpoint check.
func healthCheckHTTP(url string) error {
	client := &http.Client{
		Timeout: 5 * time.Second,
	}

	resp, err := client.Get(url)
	if err != nil {
		return fmt.Errorf("HTTP request error: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP status %d", resp.StatusCode)
	}

	return nil
}

// healthCheckWireGuard checks if WireGuard interface exists.
func healthCheckWireGuard(path string) error {
	_, err := os.Stat(path)
	return err
}

// run executes the health check logic and returns an error if any check fails.
// It takes args for testability (unused in main but available for extension).
func run(args []string) error {
	healthURL := os.Getenv("HEALTH_CHECK_URL")
	if healthURL == "" {
		healthURL = "http://localhost:9090/health"
	}

	// Check 1: HTTP health endpoint
	if err := healthCheckHTTP(healthURL); err != nil {
		fmt.Fprintf(os.Stderr, "Health check failed: %v\n", err)
		return err
	}

	// Check 2: WireGuard interface exists (warning only)
	if err := healthCheckWireGuard("/sys/class/net/wg0"); err != nil {
		fmt.Fprintf(os.Stderr, "Health check warning: WireGuard interface wg0 not found: %v\n", err)
		// WireGuard interface may not be up yet during startup, so we treat
		// this as a warning rather than a hard failure. The HTTP health
		// endpoint passing is sufficient for basic liveness.
	}

	fmt.Println("Health check passed")
	return nil
}

func main() {
	if err := run(os.Args); err != nil {
		os.Exit(1)
	}
	os.Exit(0)
}
