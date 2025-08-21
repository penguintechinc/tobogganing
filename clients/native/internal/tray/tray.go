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
	GetStatus() ConnectionStatus
}

// ConfigManager interface defines the methods needed for configuration management
type ConfigManager interface {
	GetLastConfigUpdate() time.Time
	PullConfig() error
	GetNextScheduledUpdate() time.Time
}

// ConnectionStatus represents the current connection status
type ConnectionStatus struct {
	Connected       bool
	ServerName      string
	ConnectedSince  time.Time
	BytesSent       uint64
	BytesReceived   uint64
	LastHandshake   time.Time
	PublicKey       string
	LocalIP         string
	ServerIP        string
}

// Manager handles system tray operations with VPN control functionality
type Manager struct {
	vpnManager     VPNManager
	configManager  ConfigManager
	isConnected    bool
	lastUpdate     time.Time
	ctx            context.Context
	cancel         context.CancelFunc
	
	// Menu items
	statusItem        *systray.MenuItem
	connectItem       *systray.MenuItem
	disconnectItem    *systray.MenuItem
	configStatusItem  *systray.MenuItem
	pullConfigItem    *systray.MenuItem
	statsItem         *systray.MenuItem
	settingsItem      *systray.MenuItem
	aboutItem         *systray.MenuItem
	quitItem          *systray.MenuItem
}

// NewManager creates a new tray manager with VPN and configuration management capabilities
func NewManager(vpnManager VPNManager, configManager ConfigManager) *Manager {
	ctx, cancel := context.WithCancel(context.Background())
	
	return &Manager{
		vpnManager:    vpnManager,
		configManager: configManager,
		ctx:           ctx,
		cancel:        cancel,
	}
}

// Run starts the system tray and blocks until the application exits
func (m *Manager) Run() error {
	systray.Run(m.onReady, m.onExit)
	return nil
}

// Stop gracefully stops the system tray
func (m *Manager) Stop() error {
	m.cancel()
	systray.Quit()
	return nil
}

// onReady is called when the systray is ready to receive commands
func (m *Manager) onReady() {
	// Set initial icon and tooltip
	m.setDisconnectedIcon()
	systray.SetTooltip("SASEWaddle - Not Connected")
	
	// Create menu items
	m.createMenuItems()
	
	// Start status monitoring
	go m.monitorStatus()
	
	// Handle menu item clicks
	go m.handleMenuClicks()
}

// onExit is called when the systray is about to exit
func (m *Manager) onExit() {
	log.Println("System tray exiting, cleaning up...")
	m.cancel()
	
	// Disconnect if connected
	if m.isConnected && m.vpnManager != nil {
		log.Println("Disconnecting VPN before exit...")
		if err := m.vpnManager.Disconnect(); err != nil {
			log.Printf("Error disconnecting on exit: %v", err)
		}
	}
}

// createMenuItems creates the context menu items
func (m *Manager) createMenuItems() {
	// Status item (disabled, shows current status)
	m.statusItem = systray.AddMenuItem("Status: Disconnected", "Current connection status")
	m.statusItem.Disable()
	
	systray.AddSeparator()
	
	// Connect/Disconnect items
	m.connectItem = systray.AddMenuItem("🔌 Connect", "Connect to VPN")
	m.disconnectItem = systray.AddMenuItem("🔌 Disconnect", "Disconnect from VPN")
	m.disconnectItem.Hide() // Initially hidden
	
	systray.AddSeparator()
	
	// Configuration items
	m.configStatusItem = systray.AddMenuItem("Config: Never updated", "Last configuration update time")
	m.configStatusItem.Disable()
	
	m.pullConfigItem = systray.AddMenuItem("🔄 Update Config", "Pull latest configuration from server")
	
	systray.AddSeparator()
	
	// Statistics item
	m.statsItem = systray.AddMenuItem("📊 Statistics...", "View connection statistics")
	
	// Settings item
	m.settingsItem = systray.AddMenuItem("⚙️ Settings...", "Open settings")
	
	systray.AddSeparator()
	
	// About item
	m.aboutItem = systray.AddMenuItem("ℹ️ About", "About SASEWaddle")
	
	systray.AddSeparator()
	
	// Quit item
	m.quitItem = systray.AddMenuItem("❌ Quit", "Exit SASEWaddle")
}

// handleMenuClicks handles clicks on menu items
func (m *Manager) handleMenuClicks() {
	for {
		select {
		case <-m.ctx.Done():
			return
			
		case <-m.connectItem.ClickedCh:
			go m.handleConnect()
			
		case <-m.disconnectItem.ClickedCh:
			go m.handleDisconnect()
			
		case <-m.pullConfigItem.ClickedCh:
			go m.handlePullConfig()
			
		case <-m.statsItem.ClickedCh:
			go m.showStatistics()
			
		case <-m.settingsItem.ClickedCh:
			go m.showSettings()
			
		case <-m.aboutItem.ClickedCh:
			go m.showAbout()
			
		case <-m.quitItem.ClickedCh:
			log.Println("User requested application exit")
			systray.Quit()
			return
		}
	}
}

// monitorStatus monitors the VPN connection status and updates the tray icon
func (m *Manager) monitorStatus() {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	
	for {
		select {
		case <-m.ctx.Done():
			return
		case <-ticker.C:
			m.updateStatus()
		}
	}
}

// updateStatus updates the tray icon and menu based on current VPN status
func (m *Manager) updateStatus() {
	if m.vpnManager == nil {
		return
	}
	
	connected := m.vpnManager.IsConnected()
	
	if connected != m.isConnected {
		m.isConnected = connected
		
		if connected {
			status := m.vpnManager.GetStatus()
			m.setConnectedIcon()
			systray.SetTooltip(fmt.Sprintf("SASEWaddle - Connected to %s", status.ServerName))
			m.statusItem.SetTitle(fmt.Sprintf("Status: Connected to %s", status.ServerName))
			m.connectItem.Hide()
			m.disconnectItem.Show()
			log.Printf("VPN connected to %s", status.ServerName)
		} else {
			m.setDisconnectedIcon()
			systray.SetTooltip("SASEWaddle - Disconnected")
			m.statusItem.SetTitle("Status: Disconnected")
			m.connectItem.Show()
			m.disconnectItem.Hide()
			log.Println("VPN disconnected")
		}
		
		m.lastUpdate = time.Now()
	}
	
	// Update configuration status
	m.updateConfigStatus()
}

// updateConfigStatus updates the configuration status display
func (m *Manager) updateConfigStatus() {
	if m.configManager == nil {
		return
	}
	
	lastUpdate := m.configManager.GetLastConfigUpdate()
	nextUpdate := m.configManager.GetNextScheduledUpdate()
	
	if lastUpdate.IsZero() {
		m.configStatusItem.SetTitle("Config: Never updated")
	} else {
		timeSince := time.Since(lastUpdate)
		var timeStr string
		
		if timeSince < time.Minute {
			timeStr = "just now"
		} else if timeSince < time.Hour {
			timeStr = fmt.Sprintf("%dm ago", int(timeSince.Minutes()))
		} else if timeSince < 24*time.Hour {
			timeStr = fmt.Sprintf("%dh ago", int(timeSince.Hours()))
		} else {
			timeStr = fmt.Sprintf("%dd ago", int(timeSince.Hours()/24))
		}
		
		// Calculate time until next update
		var nextStr string
		if !nextUpdate.IsZero() {
			timeUntil := time.Until(nextUpdate)
			if timeUntil > 0 {
				if timeUntil < time.Minute {
					nextStr = " (next: <1m)"
				} else if timeUntil < time.Hour {
					nextStr = fmt.Sprintf(" (next: %dm)", int(timeUntil.Minutes()))
				} else {
					nextStr = fmt.Sprintf(" (next: %dh %dm)", int(timeUntil.Hours()), int(timeUntil.Minutes())%60)
				}
			}
		}
		
		m.configStatusItem.SetTitle(fmt.Sprintf("Config: Updated %s%s", timeStr, nextStr))
	}
}

// handleConnect handles the connect menu item click
func (m *Manager) handleConnect() {
	if m.vpnManager == nil {
		m.showError("VPN manager not available")
		return
	}
	
	log.Println("User initiated VPN connection")
	
	// Update status to show connecting
	m.statusItem.SetTitle("Status: Connecting...")
	systray.SetTooltip("SASEWaddle - Connecting...")
	m.setConnectingIcon()
	
	// Attempt to connect
	err := m.vpnManager.Connect()
	if err != nil {
		log.Printf("Failed to connect: %v", err)
		m.showError(fmt.Sprintf("Failed to connect: %v", err))
		
		// Reset status on failure
		m.setDisconnectedIcon()
		systray.SetTooltip("SASEWaddle - Disconnected")
		m.statusItem.SetTitle("Status: Disconnected")
		return
	}
	
	log.Println("VPN connection initiated successfully")
}

// handleDisconnect handles the disconnect menu item click
func (m *Manager) handleDisconnect() {
	if m.vpnManager == nil {
		m.showError("VPN manager not available")
		return
	}
	
	log.Println("User initiated VPN disconnection")
	
	// Update status to show disconnecting
	m.statusItem.SetTitle("Status: Disconnecting...")
	systray.SetTooltip("SASEWaddle - Disconnecting...")
	m.setConnectingIcon()
	
	// Attempt to disconnect
	err := m.vpnManager.Disconnect()
	if err != nil {
		log.Printf("Failed to disconnect: %v", err)
		m.showError(fmt.Sprintf("Failed to disconnect: %v", err))
		return
	}
	
	log.Println("VPN disconnection initiated successfully")
}

// handlePullConfig handles the pull config menu item click
func (m *Manager) handlePullConfig() {
	if m.configManager == nil {
		m.showError("Configuration manager not available")
		return
	}
	
	log.Println("User initiated manual configuration update")
	
	// Update menu item to show pulling status
	originalTitle := "🔄 Update Config"
	m.pullConfigItem.SetTitle("🔄 Updating...")
	m.pullConfigItem.Disable()
	
	// Attempt to pull config
	err := m.configManager.PullConfig()
	
	// Reset menu item
	m.pullConfigItem.SetTitle(originalTitle)
	m.pullConfigItem.Enable()
	
	if err != nil {
		log.Printf("Failed to pull configuration: %v", err)
		m.showError(fmt.Sprintf("Failed to update config: %v", err))
		return
	}
	
	log.Println("Configuration updated successfully")
	
	// Update the status display
	m.updateConfigStatus()
	
	// Show success message temporarily in tooltip
	systray.SetTooltip("SASEWaddle - Configuration updated successfully")
	
	go func() {
		time.Sleep(3 * time.Second)
		systray.SetTooltip("SASEWaddle - Ready")
	}()
}

// showStatistics shows connection statistics in the default browser
func (m *Manager) showStatistics() {
	log.Println("User requested statistics view")
	
	var status ConnectionStatus
	if m.vpnManager != nil {
		status = m.vpnManager.GetStatus()
	}
	
	// Create a simple HTML page with statistics
	statsHTML := m.generateStatsHTML(status)
	
	// Write to temporary file and open in browser
	tmpDir := os.TempDir()
	tmpFile := filepath.Join(tmpDir, "sasewaddle-stats.html")
	
	if err := os.WriteFile(tmpFile, []byte(statsHTML), 0644); err != nil {
		log.Printf("Failed to write stats file: %v", err)
		m.showError("Failed to generate statistics")
		return
	}
	
	if err := browser.OpenFile(tmpFile); err != nil {
		log.Printf("Failed to open browser: %v", err)
		m.showError("Failed to open statistics in browser")
	}
}

// showSettings opens the settings interface
func (m *Manager) showSettings() {
	log.Println("User requested settings")
	
	// Create a simple settings HTML page
	settingsHTML := m.generateSettingsHTML()
	
	tmpDir := os.TempDir()
	tmpFile := filepath.Join(tmpDir, "sasewaddle-settings.html")
	
	if err := os.WriteFile(tmpFile, []byte(settingsHTML), 0644); err != nil {
		log.Printf("Failed to write settings file: %v", err)
		m.showError("Failed to open settings")
		return
	}
	
	if err := browser.OpenFile(tmpFile); err != nil {
		log.Printf("Failed to open browser: %v", err)
		m.showError("Failed to open settings in browser")
	}
}

// showAbout shows the about dialog
func (m *Manager) showAbout() {
	log.Println("User requested about information")
	
	aboutHTML := m.generateAboutHTML()
	
	tmpDir := os.TempDir()
	tmpFile := filepath.Join(tmpDir, "sasewaddle-about.html")
	
	if err := os.WriteFile(tmpFile, []byte(aboutHTML), 0644); err != nil {
		log.Printf("Failed to write about file: %v", err)
		m.showError("Failed to show about information")
		return
	}
	
	if err := browser.OpenFile(tmpFile); err != nil {
		log.Printf("Failed to open browser: %v", err)
		m.showError("Failed to open about page in browser")
	}
}

// Icon management functions

// setDisconnectedIcon sets the tray icon for disconnected state
func (m *Manager) setDisconnectedIcon() {
	iconData := getDisconnectedIconData()
	systray.SetIcon(iconData)
}

// setConnectedIcon sets the tray icon for connected state
func (m *Manager) setConnectedIcon() {
	iconData := getConnectedIconData()
	systray.SetIcon(iconData)
}

// setConnectingIcon sets the tray icon for connecting/disconnecting state
func (m *Manager) setConnectingIcon() {
	iconData := getConnectingIconData()
	systray.SetIcon(iconData)
}

// Utility functions

// formatBytes formats byte counts into human-readable strings
func (m *Manager) formatBytes(bytes uint64) string {
	const unit = 1024
	if bytes < unit {
		return fmt.Sprintf("%d B", bytes)
	}
	
	div, exp := uint64(unit), 0
	for n := bytes / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	
	return fmt.Sprintf("%.1f %cB", float64(bytes)/float64(div), "KMGTPE"[exp])
}

// formatDuration formats a duration into a human-readable string
func (m *Manager) formatDuration(d time.Duration) string {
	if d < time.Minute {
		return fmt.Sprintf("%ds", int(d.Seconds()))
	}
	if d < time.Hour {
		return fmt.Sprintf("%dm %ds", int(d.Minutes()), int(d.Seconds())%60)
	}
	if d < 24*time.Hour {
		return fmt.Sprintf("%dh %dm", int(d.Hours()), int(d.Minutes())%60)
	}
	return fmt.Sprintf("%dd %dh", int(d.Hours()/24), int(d.Hours())%24)
}

// generateStatsHTML generates an HTML page with connection statistics
func (m *Manager) generateStatsHTML(status ConnectionStatus) string {
	if !status.Connected {
		return `<!DOCTYPE html>
<html>
<head>
    <title>SASEWaddle Statistics</title>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 600px; margin: 0 auto; }
        .status { color: #dc3545; font-weight: bold; font-size: 18px; }
        .info { color: #666; margin-top: 20px; }
        h1 { color: #333; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 SASEWaddle Connection Statistics</h1>
        <div class="status">Status: Not Connected</div>
        <div class="info">Connect to a VPN server to view detailed statistics.</div>
    </div>
</body>
</html>`
	}
	
	uptime := time.Since(status.ConnectedSince)
	handshakeAgo := time.Since(status.LastHandshake)
	
	return fmt.Sprintf(`<!DOCTYPE html>
<html>
<head>
    <title>SASEWaddle Statistics</title>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="5">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 800px; margin: 0 auto; }
        .status { color: #28a745; font-weight: bold; font-size: 18px; margin-bottom: 20px; }
        .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
        .stat { background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #007bff; }
        .stat-label { font-weight: 600; color: #495057; font-size: 14px; }
        .stat-value { font-size: 18px; color: #212529; margin-top: 5px; }
        .server-info { background: #e3f2fd; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .refresh-info { color: #666; font-size: 12px; margin-top: 20px; text-align: center; }
        h1 { color: #333; margin-bottom: 20px; }
        .mono { font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, monospace; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 SASEWaddle Connection Statistics</h1>
        <div class="status">✅ Status: Connected</div>
        
        <div class="server-info">
            <div class="stat-label">Connected Server</div>
            <div class="stat-value">%s</div>
            <div style="margin-top: 10px; font-size: 14px; color: #666;">
                Local IP: %s → Server IP: %s
            </div>
        </div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-label">Connected Since</div>
                <div class="stat-value">%s</div>
            </div>
            <div class="stat">
                <div class="stat-label">Connection Duration</div>
                <div class="stat-value">%s</div>
            </div>
            <div class="stat">
                <div class="stat-label">Data Sent</div>
                <div class="stat-value">📤 %s</div>
            </div>
            <div class="stat">
                <div class="stat-label">Data Received</div>
                <div class="stat-value">📥 %s</div>
            </div>
            <div class="stat">
                <div class="stat-label">Last Handshake</div>
                <div class="stat-value">%s ago</div>
            </div>
            <div class="stat">
                <div class="stat-label">Public Key</div>
                <div class="stat-value mono">%s...</div>
            </div>
        </div>
        
        <div class="refresh-info">
            📊 This page refreshes automatically every 5 seconds
        </div>
    </div>
</body>
</html>`,
		status.ServerName,
		status.LocalIP,
		status.ServerIP,
		status.ConnectedSince.Format("2006-01-02 15:04:05"),
		m.formatDuration(uptime),
		m.formatBytes(status.BytesSent),
		m.formatBytes(status.BytesReceived),
		m.formatDuration(handshakeAgo),
		status.PublicKey[:32], // Show first 32 characters
	)
}

// generateSettingsHTML generates a settings page
func (m *Manager) generateSettingsHTML() string {
	return `<!DOCTYPE html>
<html>
<head>
    <title>SASEWaddle Settings</title>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 600px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 20px; }
        .setting { margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; }
        .setting-label { font-weight: 600; margin-bottom: 8px; }
        .setting-desc { color: #666; font-size: 14px; margin-bottom: 10px; }
        .coming-soon { color: #ffc107; font-weight: 600; }
        .info { background: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ SASEWaddle Settings</h1>
        
        <div class="setting">
            <div class="setting-label">Auto-Connect</div>
            <div class="setting-desc">Automatically connect to VPN when application starts</div>
            <div class="coming-soon">Coming Soon</div>
        </div>
        
        <div class="setting">
            <div class="setting-label">Server Selection</div>
            <div class="setting-desc">Choose preferred VPN server location</div>
            <div class="coming-soon">Coming Soon</div>
        </div>
        
        <div class="setting">
            <div class="setting-label">Connection Notifications</div>
            <div class="setting-desc">Show desktop notifications for connection status changes</div>
            <div class="coming-soon">Coming Soon</div>
        </div>
        
        <div class="setting">
            <div class="setting-label">Start with System</div>
            <div class="setting-desc">Launch SASEWaddle automatically when system starts</div>
            <div class="coming-soon">Coming Soon</div>
        </div>
        
        <div class="info">
            <strong>Configuration File Location:</strong><br>
            The client configuration is stored in your system's application data folder.<br>
            <em>Settings interface will be available in a future update.</em>
        </div>
    </div>
</body>
</html>`
}

// generateAboutHTML generates an about page
func (m *Manager) generateAboutHTML() string {
	return fmt.Sprintf(`<!DOCTYPE html>
<html>
<head>
    <title>About SASEWaddle</title>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 600px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 10px; }
        .version { color: #666; font-size: 16px; margin-bottom: 20px; }
        .description { line-height: 1.6; margin-bottom: 20px; }
        .features { margin: 20px 0; }
        .feature { margin: 10px 0; padding-left: 20px; }
        .links { margin-top: 30px; }
        .link { display: inline-block; margin-right: 20px; color: #007bff; text-decoration: none; }
        .link:hover { text-decoration: underline; }
        .system-info { background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 20px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 SASEWaddle</h1>
        <div class="version">Version: Development Build</div>
        
        <div class="description">
            <strong>Secure Access Service Edge (SASE) VPN Client</strong><br><br>
            SASEWaddle provides secure, fast, and reliable VPN connectivity using modern WireGuard technology
            with enterprise-grade security features and zero-trust architecture.
        </div>
        
        <div class="features">
            <strong>Key Features:</strong>
            <div class="feature">🔐 WireGuard-based VPN tunneling</div>
            <div class="feature">🌍 Global server network</div>
            <div class="feature">⚡ High-performance encryption</div>
            <div class="feature">📊 Real-time connection monitoring</div>
            <div class="feature">🖥️ Cross-platform support</div>
            <div class="feature">🔄 Automatic failover and reconnection</div>
            <div class="feature">🛡️ Zero-trust network architecture</div>
        </div>
        
        <div class="links">
            <a href="https://github.com/sasewaddle/sasewaddle" class="link" target="_blank">📚 Documentation</a>
            <a href="https://github.com/sasewaddle/sasewaddle/issues" class="link" target="_blank">🐛 Report Issues</a>
        </div>
        
        <div class="system-info">
            <strong>System Information:</strong><br>
            Platform: %s<br>
            Architecture: %s<br>
            Go Version: %s
        </div>
        
        <div style="margin-top: 30px; text-align: center; color: #666; font-size: 14px;">
            Copyright © 2024 SASEWaddle Project<br>
            Open Source Software under MIT License
        </div>
    </div>
</body>
</html>`, runtime.GOOS, runtime.GOARCH, runtime.Version())
}

// showError shows an error notification to the user
func (m *Manager) showError(message string) {
	log.Printf("Error: %s", message)
	
	// Update tray tooltip to show error temporarily
	systray.SetTooltip(fmt.Sprintf("SASEWaddle - Error: %s", message))
	
	// Reset tooltip after 5 seconds
	go func() {
		time.Sleep(5 * time.Second)
		systray.SetTooltip("SASEWaddle - Ready")
	}()
}

// Icon data functions - these would contain actual icon bytes in a real implementation

// getDisconnectedIconData returns icon data for disconnected state (red/gray)
func getDisconnectedIconData() []byte {
	// This would contain actual PNG/ICO data for a red/gray disconnected icon
	// For now, return empty slice (systray will use default)
	return []byte{}
}

// getConnectedIconData returns icon data for connected state (green)
func getConnectedIconData() []byte {
	// This would contain actual PNG/ICO data for a green connected icon
	// For now, return empty slice (systray will use default)
	return []byte{}
}

// getConnectingIconData returns icon data for connecting/transitional state (yellow/orange)
func getConnectingIconData() []byte {
	// This would contain actual PNG/ICO data for a yellow/orange connecting icon
	// For now, return empty slice (systray will use default)
	return []byte{}
}