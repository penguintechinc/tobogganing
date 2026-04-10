//go:build nogui

package gui

import (
	"context"
	"testing"
)

// TestNewApp_CreatesApp verifies NewApp returns a non-nil App.
func TestNewApp_CreatesApp(t *testing.T) {
	app := NewApp()
	if app == nil {
		t.Fatal("NewApp() returned nil")
	}
}

// TestApp_StartReturnsNoError verifies Start returns nil with background context.
func TestApp_StartReturnsNoError(t *testing.T) {
	app := NewApp()
	ctx := context.Background()
	err := app.Start(ctx)
	if err != nil {
		t.Errorf("Start() returned unexpected error: %v", err)
	}
}

// TestApp_StartWithCancelledContext verifies Start handles cancelled context.
func TestApp_StartWithCancelledContext(t *testing.T) {
	app := NewApp()
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Pre-cancel

	err := app.Start(ctx)
	if err != nil {
		t.Errorf("Start() with cancelled context returned error: %v", err)
	}
}

// TestApp_StopReturnsNoError verifies Stop is callable and returns nil.
func TestApp_StopReturnsNoError(t *testing.T) {
	app := NewApp()
	err := app.Stop()
	if err != nil {
		t.Errorf("Stop() returned unexpected error: %v", err)
	}
}

// TestApp_StopAfterStartReturnsNoError verifies Stop after Start works.
func TestApp_StopAfterStartReturnsNoError(t *testing.T) {
	app := NewApp()
	ctx := context.Background()
	_ = app.Start(ctx)
	err := app.Stop()
	if err != nil {
		t.Errorf("Stop() after Start() returned error: %v", err)
	}
}

// TestApp_StopIsIdempotent verifies Stop can be called multiple times.
func TestApp_StopIsIdempotent(t *testing.T) {
	app := NewApp()
	for i := 0; i < 3; i++ {
		err := app.Stop()
		if err != nil {
			t.Errorf("Stop() call #%d returned error: %v", i, err)
		}
	}
}

// TestApp_ShowWindowNoPanic verifies ShowWindow doesn't panic.
func TestApp_ShowWindowNoPanic(t *testing.T) {
	app := NewApp()
	// Should not panic (this is a no-op in nogui build)
	app.ShowWindow()
}

// TestApp_HideWindowNoPanic verifies HideWindow doesn't panic.
func TestApp_HideWindowNoPanic(t *testing.T) {
	app := NewApp()
	// Should not panic (this is a no-op in nogui build)
	app.HideWindow()
}

// TestApp_ShowHideWindowSequence verifies Show/Hide sequence is safe.
func TestApp_ShowHideWindowSequence(t *testing.T) {
	app := NewApp()
	for i := 0; i < 3; i++ {
		app.ShowWindow()
		app.HideWindow()
	}
	// If we got here without panic, the test passes
}
