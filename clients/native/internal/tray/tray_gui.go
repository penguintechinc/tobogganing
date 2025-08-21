//go:build !nogui && (linux || darwin || windows)

// Package tray provides system tray icon functionality for SASEWaddle client.
//
// The tray package implements a cross-platform system tray icon that allows users to:
// - Monitor connection status
// - Connect/disconnect from WireGuard tunnels
// - View connection statistics
// - Access client settings
// - Exit the application
//
// The tray icon changes appearance based on connection status and provides
// a context menu for common operations.
package tray

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"github.com/getlantern/systray"
	"github.com/pkg/browser"
)

// VPNManager interface defines the methods needed to control VPN connections
type VPNManager interface {
	Connect() error
	Disconnect() error
	IsConnected() bool
	GetStatus() string
	GetStatistics() map[string]interface{}
}

// ConfigManager interface defines methods for configuration management
type ConfigManager interface {
	GetServerURL() string
	UpdateConfiguration() error
	GetUpdateSchedule() time.Duration
}

// TrayManager manages the system tray icon and interactions
type TrayManager struct {
	vpn        VPNManager
	config     ConfigManager
	ctx        context.Context
	cancel     context.CancelFunc
	connected  bool
	lastUpdate time.Time

	// Menu items
	connectItem    *systray.MenuItem
	disconnectItem *systray.MenuItem
	statusItem     *systray.MenuItem
	statsItem      *systray.MenuItem
	updateItem     *systray.MenuItem
	settingsItem   *systray.MenuItem
	aboutItem      *systray.MenuItem
	exitItem       *systray.MenuItem
}

// NewTrayManager creates a new system tray manager
func NewTrayManager(vpn VPNManager, config ConfigManager) *TrayManager {
	ctx, cancel := context.WithCancel(context.Background())
	return &TrayManager{
		vpn:    vpn,
		config: config,
		ctx:    ctx,
		cancel: cancel,
	}
}

// Run starts the system tray and blocks until the context is cancelled
func (t *TrayManager) Run() error {
	// System tray runs on the main thread
	systray.Run(t.onReady, t.onExit)
	return nil
}

// Stop gracefully shuts down the tray manager
func (t *TrayManager) Stop() {
	t.cancel()
	systray.Quit()
}

// onReady is called when the system tray is ready
func (t *TrayManager) onReady() {
	t.setupTrayIcon()
	t.setupMenu()
	t.startStatusUpdater()
}

// onExit is called when the system tray is exiting
func (t *TrayManager) onExit() {
	log.Println("System tray exiting")
}

// setupTrayIcon configures the tray icon
func (t *TrayManager) setupTrayIcon() {
	// Set icon based on platform and theme
	iconData := t.getIconData("disconnected")
	systray.SetIcon(iconData)
	systray.SetTitle("SASEWaddle")
	systray.SetTooltip("SASEWaddle - Disconnected")
}

// setupMenu creates the context menu
func (t *TrayManager) setupMenu() {
	t.connectItem = systray.AddMenuItem("Connect", "Connect to VPN")
	t.disconnectItem = systray.AddMenuItem("Disconnect", "Disconnect from VPN")
	systray.AddSeparator()

	t.statusItem = systray.AddMenuItem("Status: Disconnected", "Current connection status")
	t.statusItem.Disable()

	t.statsItem = systray.AddMenuItem("View Statistics", "View connection statistics in browser")
	systray.AddSeparator()

	t.updateItem = systray.AddMenuItem("Update Configuration", "Pull latest configuration from server")
	t.settingsItem = systray.AddMenuItem("Settings", "Open settings")
	t.aboutItem = systray.AddMenuItem("About", "About SASEWaddle")
	systray.AddSeparator()

	t.exitItem = systray.AddMenuItem("Exit", "Exit SASEWaddle")

	// Initially disable disconnect
	t.disconnectItem.Disable()

	// Start menu handlers
	go t.handleMenuClicks()
}

// handleMenuClicks processes menu item clicks
func (t *TrayManager) handleMenuClicks() {
	for {
		select {
		case <-t.ctx.Done():
			return

		case <-t.connectItem.ClickedCh:
			t.handleConnect()

		case <-t.disconnectItem.ClickedCh:
			t.handleDisconnect()

		case <-t.statsItem.ClickedCh:
			t.handleViewStats()

		case <-t.updateItem.ClickedCh:
			t.handleUpdateConfig()

		case <-t.settingsItem.ClickedCh:
			t.handleSettings()

		case <-t.aboutItem.ClickedCh:
			t.handleAbout()

		case <-t.exitItem.ClickedCh:
			t.handleExit()
		}
	}
}

// startStatusUpdater starts a goroutine that periodically updates the tray status
func (t *TrayManager) startStatusUpdater() {
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()

		for {
			select {
			case <-t.ctx.Done():
				return
			case <-ticker.C:
				t.updateStatus()
			}
		}
	}()
}

// updateStatus updates the tray icon and status based on VPN state
func (t *TrayManager) updateStatus() {
	connected := t.vpn.IsConnected()
	status := t.vpn.GetStatus()

	if connected != t.connected {
		t.connected = connected
		t.updateMenuItems()
		t.updateIcon()
	}

	// Update status text
	statusText := fmt.Sprintf("Status: %s", status)
	t.statusItem.SetTitle(statusText)

	// Update tooltip
	tooltip := fmt.Sprintf("SASEWaddle - %s", status)
	systray.SetTooltip(tooltip)
}

// updateMenuItems enables/disables menu items based on connection state
func (t *TrayManager) updateMenuItems() {
	if t.connected {
		t.connectItem.Disable()
		t.disconnectItem.Enable()
	} else {
		t.connectItem.Enable()
		t.disconnectItem.Disable()
	}
}

// updateIcon changes the tray icon based on connection state
func (t *TrayManager) updateIcon() {
	var iconName string
	if t.connected {
		iconName = "connected"
	} else {
		iconName = "disconnected"
	}

	iconData := t.getIconData(iconName)
	systray.SetIcon(iconData)
}

// getIconData returns the appropriate icon data for the current platform
func (t *TrayManager) getIconData(state string) []byte {
	// Get executable directory for icon files
	exePath, err := os.Executable()
	if err != nil {
		log.Printf("Failed to get executable path: %v", err)
		return getEmbeddedIcon(state)
	}

	iconDir := filepath.Join(filepath.Dir(exePath), "icons")

	// Platform-specific icon selection
	var iconFile string
	switch runtime.GOOS {
	case "darwin":
		iconFile = fmt.Sprintf("icon-%s.png", state) // macOS prefers PNG
	case "windows":
		iconFile = fmt.Sprintf("icon-%s.ico", state) // Windows ICO
	default: // Linux
		iconFile = fmt.Sprintf("icon-%s.png", state) // PNG for Linux
	}

	iconPath := filepath.Join(iconDir, iconFile)
	if data, err := os.ReadFile(iconPath); err == nil {
		return data
	}

	log.Printf("Could not load icon file %s: %v", iconPath, err)
	return getEmbeddedIcon(state)
}

// Menu handlers

func (t *TrayManager) handleConnect() {
	log.Println("Tray: Connect requested")
	if err := t.vpn.Connect(); err != nil {
		log.Printf("Failed to connect: %v", err)
		// TODO: Show error notification
	}
}

func (t *TrayManager) handleDisconnect() {
	log.Println("Tray: Disconnect requested")
	if err := t.vpn.Disconnect(); err != nil {
		log.Printf("Failed to disconnect: %v", err)
		// TODO: Show error notification
	}
}

func (t *TrayManager) handleViewStats() {
	// Open statistics page in browser
	statsURL := fmt.Sprintf("%s/client/stats", t.config.GetServerURL())
	if err := browser.OpenURL(statsURL); err != nil {
		log.Printf("Failed to open statistics URL: %v", err)
	}
}

func (t *TrayManager) handleUpdateConfig() {
	log.Println("Tray: Update configuration requested")
	if err := t.config.UpdateConfiguration(); err != nil {
		log.Printf("Failed to update configuration: %v", err)
		// TODO: Show error notification
	} else {
		log.Println("Configuration updated successfully")
		// TODO: Show success notification
	}
	t.lastUpdate = time.Now()
}

func (t *TrayManager) handleSettings() {
	// Open settings page in browser or show settings dialog
	settingsURL := fmt.Sprintf("%s/client/settings", t.config.GetServerURL())
	if err := browser.OpenURL(settingsURL); err != nil {
		log.Printf("Failed to open settings URL: %v", err)
	}
}

func (t *TrayManager) handleAbout() {
	// Open about page or show about dialog
	aboutURL := fmt.Sprintf("%s/client/about", t.config.GetServerURL())
	if err := browser.OpenURL(aboutURL); err != nil {
		log.Printf("Failed to open about URL: %v", err)
	}
}

func (t *TrayManager) handleExit() {
	log.Println("Tray: Exit requested")
	// Disconnect if connected
	if t.vpn.IsConnected() {
		log.Println("Disconnecting before exit...")
		if err := t.vpn.Disconnect(); err != nil {
			log.Printf("Failed to disconnect on exit: %v", err)
		}
		// Give a moment for cleanup
		time.Sleep(2 * time.Second)
	}
	t.Stop()
}

// getEmbeddedIcon returns a basic embedded icon as fallback
func getEmbeddedIcon(state string) []byte {
	// This would contain embedded icon data as bytes
	// For now, return a minimal PNG for the given state
	if state == "connected" {
		return getConnectedIconPNG()
	}
	return getDisconnectedIconPNG()
}

// Minimal embedded icons (would be replaced with actual icon data)
func getConnectedIconPNG() []byte {
	// Green dot icon (simplified)
	return []byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A} // PNG header
}

func getDisconnectedIconPNG() []byte {
	// Red dot icon (simplified)
	return []byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A} // PNG header
}