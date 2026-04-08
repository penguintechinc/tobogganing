//go:build nogui

package gui

import (
	"context"
	"testing"
)

// --- NewApp ---

func TestNewApp_ReturnsNonNil(t *testing.T) {
	app := NewApp()
	if app == nil {
		t.Fatal("NewApp() returned nil")
	}
}

// --- Start ---

func TestApp_Start_NoError(t *testing.T) {
	app := NewApp()
	ctx := context.Background()
	if err := app.Start(ctx); err != nil {
		t.Errorf("Start: %v", err)
	}
}

func TestApp_Start_CanceledContext_NoError(t *testing.T) {
	app := NewApp()
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // pre-canceled
	if err := app.Start(ctx); err != nil {
		t.Errorf("Start with canceled context: %v", err)
	}
}

// --- Stop ---

func TestApp_Stop_NoError(t *testing.T) {
	app := NewApp()
	if err := app.Stop(); err != nil {
		t.Errorf("Stop: %v", err)
	}
}

func TestApp_Stop_AfterStart_NoError(t *testing.T) {
	app := NewApp()
	ctx := context.Background()
	_ = app.Start(ctx)
	if err := app.Stop(); err != nil {
		t.Errorf("Stop after Start: %v", err)
	}
}

func TestApp_Stop_Idempotent(t *testing.T) {
	app := NewApp()
	for i := 0; i < 3; i++ {
		if err := app.Stop(); err != nil {
			t.Errorf("Stop #%d: %v", i, err)
		}
	}
}

// --- ShowWindow / HideWindow ---

func TestApp_ShowWindow_NoPanic(t *testing.T) {
	app := NewApp()
	// Should not panic.
	app.ShowWindow()
}

func TestApp_HideWindow_NoPanic(t *testing.T) {
	app := NewApp()
	// Should not panic.
	app.HideWindow()
}

func TestApp_ShowHideWindow_Cycle(t *testing.T) {
	app := NewApp()
	app.ShowWindow()
	app.HideWindow()
	app.ShowWindow()
	app.HideWindow()
}
