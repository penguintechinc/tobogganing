//go:build !nogui

// Package gui implements the graphical user interface for the SASEWaddle native client.
package gui

import (
    "context"
    "fyne.io/fyne/v2"
    "fyne.io/fyne/v2/app"
    "fyne.io/fyne/v2/widget"
)

// App represents the GUI application
type App struct {
    fyneApp fyne.App
}

// NewApp creates a new GUI application
func NewApp() *App {
    return &App{
        fyneApp: app.New(),
    }
}

// Run starts the GUI application
func (a *App) Run(ctx context.Context) error {
    w := a.fyneApp.NewWindow("SASEWaddle Client")
    w.SetContent(widget.NewLabel("SASEWaddle Native Client"))
    w.ShowAndRun()
    return nil
}

// Stop gracefully stops the GUI application
func (a *App) Stop() error {
    if a.fyneApp != nil {
        a.fyneApp.Quit()
    }
    return nil
}