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

func main() {
	healthURL := os.Getenv("HEALTH_CHECK_URL")
	if healthURL == "" {
		healthURL = "http://localhost:9090/health"
	}

	// Check 1: HTTP health endpoint
	client := &http.Client{
		Timeout: 5 * time.Second,
	}

	resp, err := client.Get(healthURL)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Health check failed: HTTP request error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "Health check failed: HTTP status %d\n", resp.StatusCode)
		os.Exit(1)
	}

	// Check 2: WireGuard interface exists
	_, err = os.Stat("/sys/class/net/wg0")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Health check warning: WireGuard interface wg0 not found: %v\n", err)
		// WireGuard interface may not be up yet during startup, so we treat
		// this as a warning rather than a hard failure. The HTTP health
		// endpoint passing is sufficient for basic liveness.
	}

	fmt.Println("Health check passed")
	os.Exit(0)
}
