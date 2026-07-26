package main

import (
	"context"
	"testing"
)

// TestRun_BadConfigFile exercises the LoadFromFile error path in run().
func TestRun_BadConfigFile(t *testing.T) {
	ctx := context.Background()
	err := run(ctx, "/tmp/nonexistent-tray-example-99999.yaml")
	if err == nil {
		t.Error("expected error for non-existent config file")
	}
}

// TestRun_EmptyConfigPath exercises the full run() path using a pre-cancelled context so
// tray.(*TrayManager).Run() returns immediately when the context is done.
func TestRun_EmptyConfigPath(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // pre-cancel so tray manager exits immediately
	err := run(ctx, "")
	if err != nil {
		t.Logf("run returned: %v", err)
	}
}
