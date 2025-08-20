// Package proxy provides WireGuard-aware routing for authenticated traffic.
// 
// The WireGuard router handles two traffic patterns:
// 1. Client → Headend → Internet (external destinations)
// 2. Client → Headend → Other WireGuard Clients (peer-to-peer)
//
// All traffic is authenticated before routing decisions are made.
package main

import (
	"fmt"
	"net"
	"os/exec"
	"strings"

	log "github.com/sirupsen/logrus"
)

// WireGuardRouter handles routing decisions for authenticated traffic
type WireGuardRouter struct {
	wgNetwork     *net.IPNet  // WireGuard network CIDR (e.g., 10.200.0.0/16)
	wgInterface   string      // WireGuard interface name (e.g., wg0)
	headendIP     net.IP      // Headend's IP in WireGuard network
}

// NewWireGuardRouter creates a new WireGuard-aware router
func NewWireGuardRouter(wgInterface string, wgNetwork string, headendIP string) (*WireGuardRouter, error) {
	// Parse WireGuard network CIDR
	_, ipNet, err := net.ParseCIDR(wgNetwork)
	if err != nil {
		return nil, fmt.Errorf("invalid WireGuard network CIDR: %w", err)
	}

	// Parse headend IP
	ip := net.ParseIP(headendIP)
	if ip == nil {
		return nil, fmt.Errorf("invalid headend IP: %s", headendIP)
	}

	return &WireGuardRouter{
		wgNetwork:   ipNet,
		wgInterface: wgInterface,
		headendIP:   ip,
	}, nil
}

// RouteTraffic determines how to route authenticated traffic
func (wr *WireGuardRouter) RouteTraffic(targetHost string, sourceConn net.Conn) error {
	targetIP := net.ParseIP(targetHost)
	
	// Check if target is a WireGuard peer
	if targetIP != nil && wr.wgNetwork.Contains(targetIP) {
		return wr.routeToPeer(targetHost, sourceConn)
	}
	
	// Route to internet via normal proxy
	return wr.routeToInternet(targetHost, sourceConn)
}

// routeToPeer handles traffic destined for other WireGuard clients
func (wr *WireGuardRouter) routeToPeer(targetIP string, sourceConn net.Conn) error {
	log.Infof("Routing traffic to WireGuard peer: %s", targetIP)

	// Check if peer exists in WireGuard configuration
	if !wr.isPeerConfigured(targetIP) {
		return fmt.Errorf("peer %s not found in WireGuard configuration", targetIP)
	}

	// Create connection to WireGuard peer through the WireGuard interface
	targetConn, err := wr.dialPeer(targetIP)
	if err != nil {
		return fmt.Errorf("failed to connect to peer %s: %w", targetIP, err)
	}
	defer targetConn.Close()

	// Mark this traffic as authenticated for iptables
	if err := wr.markTrafficAuthenticated(sourceConn); err != nil {
		log.Warnf("Failed to mark traffic as authenticated: %v", err)
	}

	// Bidirectional proxy between client and peer
	go wr.proxyData(sourceConn, targetConn, fmt.Sprintf("client->%s", targetIP))
	wr.proxyData(targetConn, sourceConn, fmt.Sprintf("%s->client", targetIP))

	return nil
}

// routeToInternet handles traffic destined for external hosts
func (wr *WireGuardRouter) routeToInternet(targetHost string, sourceConn net.Conn) error {
	log.Infof("Routing traffic to internet: %s", targetHost)

	// Connect to external host
	targetConn, err := net.Dial("tcp", targetHost)
	if err != nil {
		return fmt.Errorf("failed to connect to %s: %w", targetHost, err)
	}
	defer targetConn.Close()

	// Mark this traffic as authenticated for iptables
	if err := wr.markTrafficAuthenticated(sourceConn); err != nil {
		log.Warnf("Failed to mark traffic as authenticated: %v", err)
	}

	// Bidirectional proxy between client and internet
	go wr.proxyData(sourceConn, targetConn, fmt.Sprintf("client->%s", targetHost))
	wr.proxyData(targetConn, sourceConn, fmt.Sprintf("%s->client", targetHost))

	return nil
}

// isPeerConfigured checks if the target IP is a configured WireGuard peer
func (wr *WireGuardRouter) isPeerConfigured(targetIP string) bool {
	// Check WireGuard peer list to see if this IP is configured
	cmd := exec.Command("wg", "show", wr.wgInterface, "allowed-ips")
	output, err := cmd.Output()
	if err != nil {
		log.Errorf("Failed to check WireGuard peers: %v", err)
		return false
	}

	// Parse output to find if targetIP is in allowed IPs
	lines := strings.Split(string(output), "\n")
	for _, line := range lines {
		if strings.Contains(line, targetIP) {
			return true
		}
	}

	return false
}

// dialPeer creates a connection to a WireGuard peer
func (wr *WireGuardRouter) dialPeer(targetIP string) (net.Conn, error) {
	// For peer-to-peer connections, we dial directly to the peer's IP
	// The traffic will be routed through the WireGuard interface
	return net.Dial("tcp", targetIP+":0") // Port will be determined by the actual service
}

// markTrafficAuthenticated marks packets as authenticated for iptables processing
func (wr *WireGuardRouter) markTrafficAuthenticated(conn net.Conn) error {
	// This would use SO_MARK socket option to mark packets with mark 100
	// which corresponds to our iptables rule for authenticated traffic
	
	// For TCP connections, we can use the file descriptor
	if tcpConn, ok := conn.(*net.TCPConn); ok {
		// Get the file descriptor
		file, err := tcpConn.File()
		if err != nil {
			return fmt.Errorf("failed to get connection file descriptor: %w", err)
		}
		defer file.Close()

		// Use iptables to mark packets from this connection
		// This is a simplified approach - in production, would use netlink sockets
		sourceAddr := conn.RemoteAddr().String()
		cmd := exec.Command("iptables", "-t", "mangle", "-A", "OUTPUT", 
			"-s", sourceAddr, "-j", "MARK", "--set-mark", "100")
		
		if err := cmd.Run(); err != nil {
			return fmt.Errorf("failed to mark traffic: %w", err)
		}
	}

	return nil
}

// proxyData copies data bidirectionally between connections
func (wr *WireGuardRouter) proxyData(src, dst net.Conn, direction string) {
	buffer := make([]byte, 32768)
	
	for {
		n, err := src.Read(buffer)
		if err != nil {
			log.Debugf("Connection closed in direction %s: %v", direction, err)
			break
		}

		if _, err := dst.Write(buffer[:n]); err != nil {
			log.Errorf("Failed to write in direction %s: %v", direction, err)
			break
		}

		log.Debugf("Proxied %d bytes in direction %s", n, direction)
	}
}

// IsWireGuardDestination checks if a destination is within the WireGuard network
func (wr *WireGuardRouter) IsWireGuardDestination(host string) bool {
	ip := net.ParseIP(host)
	if ip == nil {
		// Try to resolve hostname
		ips, err := net.LookupIP(host)
		if err != nil || len(ips) == 0 {
			return false
		}
		ip = ips[0]
	}

	return wr.wgNetwork.Contains(ip)
}

// GetWireGuardPeers returns list of configured WireGuard peers
func (wr *WireGuardRouter) GetWireGuardPeers() ([]string, error) {
	cmd := exec.Command("wg", "show", wr.wgInterface, "allowed-ips")
	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("failed to get WireGuard peers: %w", err)
	}

	var peers []string
	lines := strings.Split(string(output), "\n")
	
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		
		// Parse peer line format: "publickey	allowed-ips"
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			// Extract IP from allowed-ips (format: "10.200.1.2/32")
			allowedIP := parts[1]
			if ip := strings.Split(allowedIP, "/")[0]; ip != "" {
				peers = append(peers, ip)
			}
		}
	}

	return peers, nil
}