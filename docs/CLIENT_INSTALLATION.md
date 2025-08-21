# 🖥️ SASEWaddle Client Installation Guide

> **Complete guide for installing and configuring SASEWaddle clients across all platforms**

## 📋 Table of Contents

- [🎯 Client Types](#-client-types)
- [🖼️ Desktop GUI Installation](#️-desktop-gui-installation)
- [🖥️ Headless Installation](#️-headless-installation)
- [🐳 Docker Installation](#-docker-installation)
- [⚙️ Configuration](#️-configuration)
- [🚀 Usage Examples](#-usage-examples)
- [🔧 Troubleshooting](#-troubleshooting)

---

## 🎯 Client Types

SASEWaddle offers two distinct client types optimized for different use cases:

### 🖼️ **Desktop GUI Clients**
**Perfect for end users who want the best experience**

| Platform | Binary Name | Features |
|----------|-------------|----------|
| **macOS Universal** | `sasewaddle-client-darwin-universal` | Intel + Apple Silicon |
| **macOS Intel** | `sasewaddle-client-darwin-amd64` | Intel Macs |
| **macOS Apple Silicon** | `sasewaddle-client-darwin-arm64` | M1/M2/M3 Macs |
| **Linux AMD64** | `sasewaddle-client-linux-amd64` | Desktop Linux |
| **Linux ARM64** | `sasewaddle-client-linux-arm64` | ARM64 Linux |
| **Windows** | `sasewaddle-client-windows-amd64.exe` | Windows 10/11 |

**GUI Features:**
- ✅ **System Tray Integration** - Native tray icon on all platforms
- ✅ **One-Click Connect** - Connect/disconnect with single click
- ✅ **Real-Time Status** - Visual connection status indicators
- ✅ **Statistics Viewer** - Connection stats and performance metrics
- ✅ **Auto-Updates** - Automatic configuration updates from manager
- ✅ **Settings Access** - Easy access to configuration and preferences
- ✅ **Graceful Shutdown** - Automatic disconnection on exit

### 🖥️ **Headless Clients**
**Optimized for servers, containers, and automation**

| Platform | Binary Name | Use Case |
|----------|-------------|----------|
| **All Desktop Platforms** | `*-headless` variants | Server deployments |
| **Linux ARM v7** | `sasewaddle-client-linux-armv7-headless` | Raspberry Pi, embedded |
| **Linux ARM v6** | `sasewaddle-client-linux-armv6-headless` | Older ARM devices |
| **Linux MIPS** | `sasewaddle-client-linux-mips-headless` | Router firmware |
| **Linux MIPSLE** | `sasewaddle-client-linux-mipsle-headless` | Little-endian MIPS |

**Headless Features:**
- ✅ **CLI Interface** - Command-line only, no GUI dependencies
- ✅ **Daemon Mode** - Background operation for servers
- ✅ **Docker Ready** - Perfect for containerized deployments
- ✅ **Automation Friendly** - Script and systemd integration
- ✅ **Small Footprint** - Minimal resource usage
- ✅ **Cross-Platform** - Wide embedded platform support

---

## 🖼️ Desktop GUI Installation

### 🍎 macOS Installation

#### Quick Install
```bash
# Install GUI version with system tray
curl -sSL https://github.com/penguintechinc/sasewaddle/releases/latest/download/install-gui.sh | bash
```

#### Manual Install
```bash
# Universal Binary (recommended - works on Intel + Apple Silicon)
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-darwin-universal -o /usr/local/bin/sasewaddle-client
chmod +x /usr/local/bin/sasewaddle-client

# Or download specific architecture
# Intel Macs
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-darwin-amd64 -o /usr/local/bin/sasewaddle-client

# Apple Silicon Macs (M1/M2/M3)
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-darwin-arm64 -o /usr/local/bin/sasewaddle-client

chmod +x /usr/local/bin/sasewaddle-client
```

#### macOS App Bundle (Future)
```bash
# Download .app bundle for native macOS experience
# Coming in v1.2.0
```

### 🐧 Linux Installation

#### Ubuntu/Debian
```bash
# Install GUI dependencies
sudo apt-get update
sudo apt-get install libayatana-appindicator3-1 libgtk-3-0

# Install SASEWaddle GUI client
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-amd64 -o /usr/local/bin/sasewaddle-client
sudo chmod +x /usr/local/bin/sasewaddle-client

# For ARM64 systems
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-arm64 -o /usr/local/bin/sasewaddle-client
sudo chmod +x /usr/local/bin/sasewaddle-client
```

#### RHEL/CentOS/Fedora
```bash
# Install GUI dependencies
sudo dnf install libayatana-appindicator-gtk3 gtk3

# Install SASEWaddle GUI client
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-amd64 -o /usr/local/bin/sasewaddle-client
sudo chmod +x /usr/local/bin/sasewaddle-client
```

#### Arch Linux
```bash
# Install GUI dependencies
sudo pacman -S libayatana-appindicator gtk3

# Install SASEWaddle GUI client
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-amd64 -o /usr/local/bin/sasewaddle-client
sudo chmod +x /usr/local/bin/sasewaddle-client
```

### 🪟 Windows Installation

#### Manual Install
```powershell
# Download Windows GUI client
Invoke-WebRequest -Uri "https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-windows-amd64.exe" -OutFile "C:\Program Files\SASEWaddle\sasewaddle-client.exe"

# Add to PATH
$env:PATH += ";C:\Program Files\SASEWaddle"
```

#### Windows Installer (Future)
```powershell
# Download MSI installer for native Windows experience  
# Coming in v1.2.0
```

---

## 🖥️ Headless Installation

### Server & Container Deployments

#### Linux Servers
```bash
# Download headless version for your architecture
# AMD64 (most common)
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-amd64-headless -o /usr/local/bin/sasewaddle-client
sudo chmod +x /usr/local/bin/sasewaddle-client

# ARM64 servers
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-arm64-headless -o /usr/local/bin/sasewaddle-client
sudo chmod +x /usr/local/bin/sasewaddle-client
```

#### macOS Servers
```bash
# Headless version for macOS servers
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-darwin-universal-headless -o /usr/local/bin/sasewaddle-client
chmod +x /usr/local/bin/sasewaddle-client
```

#### Windows Servers
```powershell
# Headless version for Windows servers
Invoke-WebRequest -Uri "https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-windows-amd64-headless.exe" -OutFile "C:\Program Files\SASEWaddle\sasewaddle-client.exe"
```

### Embedded Systems & IoT

#### Raspberry Pi
```bash
# Raspberry Pi 4/5 (ARM v7)
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-armv7-headless -o /usr/local/bin/sasewaddle-client

# Raspberry Pi Zero/1 (ARM v6)
curl -L https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-armv6-headless -o /usr/local/bin/sasewaddle-client

sudo chmod +x /usr/local/bin/sasewaddle-client
```

#### Router Firmware
```bash
# MIPS routers (OpenWrt, DD-WRT)
wget https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-mips-headless -O /usr/bin/sasewaddle-client

# Little-endian MIPS
wget https://github.com/penguintechinc/sasewaddle/releases/latest/download/sasewaddle-client-linux-mipsle-headless -O /usr/bin/sasewaddle-client

chmod +x /usr/bin/sasewaddle-client
```

---

## 🐳 Docker Installation

### Official Docker Images

```bash
# Pull official image
docker pull ghcr.io/penguintechinc/sasewaddle-client:latest

# Run with configuration
docker run -d \
  --name sasewaddle-client \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -e MANAGER_URL=https://manager.example.com \
  -e API_KEY=your-api-key \
  ghcr.io/penguintechinc/sasewaddle-client:latest
```

### Custom Dockerfile

```dockerfile
FROM alpine:latest

# Install runtime dependencies
RUN apk add --no-cache ca-certificates iptables

# Copy headless binary
COPY sasewaddle-client-linux-amd64-headless /usr/bin/sasewaddle-client
RUN chmod +x /usr/bin/sasewaddle-client

# Configuration
ENV MANAGER_URL=""
ENV API_KEY=""
ENV LOG_LEVEL="info"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD /usr/bin/sasewaddle-client status || exit 1

ENTRYPOINT ["/usr/bin/sasewaddle-client"]
CMD ["connect", "--daemon"]
```

### Docker Compose

```yaml
version: '3.8'
services:
  sasewaddle-client:
    image: ghcr.io/penguintechinc/sasewaddle-client:latest
    container_name: sasewaddle-client
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun
    environment:
      - MANAGER_URL=https://manager.example.com
      - API_KEY=your-api-key
      - LOG_LEVEL=info
    restart: unless-stopped
    networks:
      - sasewaddle
    volumes:
      - sasewaddle-config:/etc/sasewaddle

volumes:
  sasewaddle-config:

networks:
  sasewaddle:
    external: true
```

---

## ⚙️ Configuration

### Initial Setup

```bash
# Initialize client configuration
sasewaddle-client init \
  --manager-url https://manager.example.com:8000 \
  --api-key YOUR_TEMPORARY_API_KEY \
  --auto-update \
  --log-level info
```

### Configuration File

The client creates a configuration file at:
- **Linux/macOS**: `~/.sasewaddle/config.yaml`
- **Windows**: `%APPDATA%\SASEWaddle\config.yaml`

```yaml
# ~/.sasewaddle/config.yaml
manager:
  url: "https://manager.example.com:8000"
  api_key: "your-api-key"
  timeout: "30s"

client:
  log_level: "info"
  auto_connect: true
  auto_update: true
  update_interval: "1h"
  system_tray: true  # GUI builds only

wireguard:
  interface: "wg-sasewaddle"
  dns: ["1.1.1.1", "8.8.8.8"]
  mtu: 1420

network:
  routes:
    - "0.0.0.0/0"  # Route all traffic through VPN
  exclude_routes:
    - "192.168.0.0/16"  # Exclude local networks
```

### Environment Variables

```bash
# Core configuration
export SASEWADDLE_MANAGER_URL="https://manager.example.com:8000"
export SASEWADDLE_API_KEY="your-api-key"
export SASEWADDLE_LOG_LEVEL="info"

# GUI-specific (GUI builds only)
export SASEWADDLE_SYSTEM_TRAY="true"
export SASEWADDLE_AUTO_UPDATE="true"

# Headless-specific
export SASEWADDLE_DAEMON_MODE="true"
export SASEWADDLE_PID_FILE="/var/run/sasewaddle.pid"
```

---

## 🚀 Usage Examples

### 🖼️ Desktop GUI Usage

```bash
# Start GUI with system tray
sasewaddle-client gui

# Start minimized to system tray
sasewaddle-client gui --minimize

# Start GUI and auto-connect
sasewaddle-client gui --auto-connect

# Force configuration update
sasewaddle-client update-config
```

**System Tray Operations:**
- **Left Click**: Show/hide status window
- **Right Click**: Context menu with connect/disconnect
- **Double Click**: Toggle connection state

### 🖥️ Headless Usage

```bash
# Connect and run as daemon
sasewaddle-client connect --daemon

# Connect in foreground
sasewaddle-client connect

# Check connection status
sasewaddle-client status

# View detailed statistics
sasewaddle-client stats

# Disconnect
sasewaddle-client disconnect

# Update configuration
sasewaddle-client update-config

# View logs
sasewaddle-client logs --tail=100
```

### Systemd Service

```ini
# /etc/systemd/system/sasewaddle.service
[Unit]
Description=SASEWaddle Client
After=network.target
Wants=network.target

[Service]
Type=forking
ExecStart=/usr/local/bin/sasewaddle-client connect --daemon
ExecStop=/usr/local/bin/sasewaddle-client disconnect
Restart=always
RestartSec=5
User=sasewaddle
Group=sasewaddle

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl enable sasewaddle
sudo systemctl start sasewaddle
sudo systemctl status sasewaddle
```

---

## 🔧 Troubleshooting

### GUI Issues

#### Linux System Tray Not Working
```bash
# Check if system supports app indicators
echo $XDG_CURRENT_DESKTOP

# Install missing dependencies
sudo apt-get install libayatana-appindicator3-1

# For GNOME, install extension
sudo apt-get install gnome-shell-extension-appindicator
```

#### macOS System Tray Missing
```bash
# Check if running on supported macOS version
sw_vers

# Ensure binary has proper permissions
codesign -v /usr/local/bin/sasewaddle-client
```

#### Windows System Tray Issues
```powershell
# Run as administrator if needed
Start-Process sasewaddle-client -Verb RunAs

# Check Windows version compatibility
Get-ComputerInfo | Select WindowsProductName, WindowsVersion
```

### Connection Issues

#### Cannot Connect to Manager
```bash
# Test connectivity
curl -k https://manager.example.com:8000/health

# Check DNS resolution
nslookup manager.example.com

# Test with debug logging
SASEWADDLE_LOG_LEVEL=debug sasewaddle-client connect
```

#### WireGuard Interface Issues
```bash
# Check WireGuard status
sudo wg show

# Check interface configuration
ip addr show wg-sasewaddle

# Check routing table
ip route show
```

#### Certificate Issues
```bash
# Check certificate validity
sasewaddle-client cert-info

# Force certificate renewal
sasewaddle-client renew-cert

# Reset client configuration
sasewaddle-client reset --confirm
```

### Performance Issues

#### High CPU Usage
```bash
# Check process stats
top -p $(pgrep sasewaddle-client)

# Reduce log level
export SASEWADDLE_LOG_LEVEL=warning

# Check for update loops
sasewaddle-client logs | grep "update"
```

#### Network Performance
```bash
# Test VPN speed
speedtest-cli

# Check MTU settings
ping -M do -s 1472 8.8.8.8

# Adjust MTU if needed
sasewaddle-client config set wireguard.mtu 1380
```

---

## 📚 Additional Resources

- [Architecture Guide](./ARCHITECTURE.md)
- [API Documentation](./API.md)
- [Feature Documentation](./FEATURES.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)
- [GitHub Releases](https://github.com/penguintechinc/sasewaddle/releases)

---

**Need Help?** Open an issue on [GitHub](https://github.com/penguintechinc/sasewaddle/issues) or join our [Discord](https://discord.gg/sasewaddle)