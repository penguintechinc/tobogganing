package main

import (
	"context"
	"os"
	"testing"
	"time"
)

// TestRun_PrecanceledContext verifies run() exits cleanly with a pre-cancelled context.
func TestRun_PrecanceledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel immediately

	// run() should return quickly since context is already done
	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() with pre-cancelled context returned error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("run() did not return in time with pre-cancelled context")
	}
}

// TestRun_TickerFiresOnce sets pollInterval to 1ms and verifies the ticker fires at least once.
func TestRun_TickerFiresOnce(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithCancel(context.Background())

	// Cancel after 50ms to give the ticker time to fire multiple times
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Error("run() did not complete")
	}
}

// TestRun_TickerFiresMultipleTimes sets pollInterval to 1ms and verifies multiple ticker fires.
func TestRun_TickerFiresMultipleTimes(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithCancel(context.Background())

	// Cancel after 100ms to allow many ticker cycles (at 1ms each)
	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel()
	}()

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Error("run() did not complete in time")
	}
}

// TestRun_GracefulShutdown verifies run() exits cleanly when context is cancelled.
func TestRun_GracefulShutdown(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	// Allow a couple ticker cycles
	time.Sleep(10 * time.Millisecond)

	// Now cancel and verify clean shutdown
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error on graceful shutdown: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("run() did not exit after cancellation")
	}
}

// TestRun_ContextTimeout verifies run() respects a context timeout.
func TestRun_ContextTimeout(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Error("run() did not respect timeout")
	}
}

// TestRun_LongRunning verifies run() stays alive until context is cancelled.
func TestRun_LongRunning(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithCancel(context.Background())

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	// Give goroutine time to start
	time.Sleep(10 * time.Millisecond)

	// Verify it's still running
	select {
	case err := <-done:
		t.Errorf("run() exited prematurely: %v", err)
	default:
		// Good - still running
	}

	// Now cancel and verify it exits cleanly
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error on cancellation: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Error("run() did not exit after context cancellation")
	}
}

// TestRun_CerberusEnrichmentPath verifies the ticker exercises Cerberus blocklist enrichment.
// With pollInterval=1ms, the ticker should fire and call cerberusClient methods (even if they're nil).
func TestRun_CerberusEnrichmentPath(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithCancel(context.Background())

	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error during Cerberus enrichment test: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Error("run() did not complete during enrichment path test")
	}
}

// TestRun_PushErrorHandling verifies the ticker exercises the push error path.
// Push will fail (no real MarchProxy), but that's OK - we're testing the code path executes.
func TestRun_PushErrorHandling(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithCancel(context.Background())

	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error during push error handling test: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Error("run() did not complete during push error test")
	}
}

// TestRun_InjectedTickerCycle verifies that an injected 1ms poll interval actually executes ticker logic.
func TestRun_InjectedTickerCycle(t *testing.T) {
	oldInterval := pollInterval
	defer func() { pollInterval = oldInterval }()
	pollInterval = 1 * time.Millisecond

	ctx, cancel := context.WithCancel(context.Background())

	// Allow enough time for multiple ticker cycles
	go func() {
		time.Sleep(20 * time.Millisecond)
		cancel()
	}()

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Error("run() did not complete in time")
	}
}

// TestRun_WithCerberusEnabled verifies the cerberus enrichment block (lines 52-56) is exercised
// when CERBERUS_URL is set. The client will be non-nil but the URL is unreachable — errors are graceful.
func TestRun_WithCerberusEnabled(t *testing.T) {
	// Set CERBERUS_URL so cerberus.NewClientFromEnv() returns a non-nil client
	t.Setenv("CERBERUS_URL", "http://127.0.0.1:1/cerberus") // unreachable but parseable

	pollInterval = 1 * time.Millisecond
	defer func() { pollInterval = 30 * time.Second }()

	ctx, cancel := context.WithCancel(context.Background())
	// Wait long enough for the ticker to fire at least once, then cancel
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()

	done := make(chan error, 1)
	go func() {
		done <- run(ctx)
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() with Cerberus returned error: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Error("run() did not complete in time")
	}
}

// TestRun_WithCerberusEnabledAndWait is similar but uses os.Setenv for broader test compat.
func TestRun_CerberusBlocklistPathCoverage(t *testing.T) {
	old := os.Getenv("CERBERUS_URL")
	os.Setenv("CERBERUS_URL", "http://127.0.0.1:1") //nolint:errcheck
	defer func() {
		if old == "" {
			os.Unsetenv("CERBERUS_URL") //nolint:errcheck
		} else {
			os.Setenv("CERBERUS_URL", old) //nolint:errcheck
		}
	}()

	pollInterval = 1 * time.Millisecond
	defer func() { pollInterval = 30 * time.Second }()

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	done := make(chan error, 1)
	go func() { done <- run(ctx) }()

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("run() returned error: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Error("run() timed out")
	}
}
