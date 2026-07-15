// Package main implements the SASEWaddle headend proxy server.
package main

import (
	"net"

	log "github.com/sirupsen/logrus"
)

// TCP Proxy Implementation
func (t *TCPProxy) Start() {
	log.Info("Starting TCP proxy server")

	for {
		conn, err := t.listener.Accept()
		if err != nil {
			log.Errorf("TCP accept error: %v", err)
			continue
		}

		// Handle connection in goroutine with authentication
		go t.handleConnection(conn)
	}
}

func (t *TCPProxy) handleConnection(clientConn net.Conn) {
	defer func() {
		if err := clientConn.Close(); err != nil {
			log.Debugf("Error closing client connection: %v", err)
		}
	}()

	// Read first packet to extract JWT token from headers
	buffer := make([]byte, 4096)
	n, err := clientConn.Read(buffer)
	if err != nil {
		log.Errorf("TCP read error: %v", err)
		return
	}

	// Parse JWT token from connection metadata
	// This would typically be in a custom protocol header
	token := extractJWTFromPacket(buffer[:n])

	// Authenticate using JWT
	user, err := t.authProvider.ValidateToken(token)
	if err != nil {
		log.Errorf("TCP authentication failed: %v", err)
		return
	}

	log.Infof("TCP connection authenticated for user: %s", user.ID)

	// Extract target host from the packet
	targetHost := extractTargetFromPacket(buffer[:n])
	if targetHost == "" {
		log.Error("No target host found in TCP packet")
		return
	}

	// Check firewall rules if firewall manager is enabled
	var allowed bool
	if t.firewallManager != nil {
		allowed = t.firewallManager.CheckAccess(user.ID, targetHost)
	} else {
		allowed = true
	}

	if !allowed {
		log.Warnf("Firewall blocked TCP connection for user %s to %s", user.ID, targetHost)

		// Log denied access to syslog
		if t.syslogLogger != nil {
			t.syslogLogger.LogTCPAccess(user.ID, user.Name, clientConn.RemoteAddr().String(), targetHost, false)
		}

		return
	}

	log.Debugf("Firewall allowed TCP connection for user %s to %s", user.ID, targetHost)

	// Log allowed access to syslog
	if t.syslogLogger != nil {
		t.syslogLogger.LogTCPAccess(user.ID, user.Name, clientConn.RemoteAddr().String(), targetHost, true)
	}

	// Use WireGuard router if available for intelligent routing
	if t.wgRouter != nil {
		log.Infof("Using WireGuard router for TCP traffic to %s", targetHost)
		if err := t.wgRouter.RouteTraffic(targetHost, clientConn); err != nil {
			log.Errorf("WireGuard routing failed for %s: %v", targetHost, err)
		}
		return
	}

	// Fallback to direct connection
	targetConn, err := net.Dial("tcp", targetHost)
	if err != nil {
		log.Errorf("Failed to connect to target %s: %v", targetHost, err)
		return
	}
	defer func() {
		if err := targetConn.Close(); err != nil {
			log.Debugf("Error closing target connection: %v", err)
		}
	}()

	// Send original packet to target
	if _, err := targetConn.Write(buffer[:n]); err != nil {
		log.Errorf("Failed to write to target: %v", err)
		return
	}

	// Mirror traffic if enabled
	if t.mirrorManager != nil {
		go t.mirrorManager.MirrorTCP(clientConn.RemoteAddr().String(), targetHost, buffer[:n])
	}

	// Bidirectional proxy
	go t.proxyData(clientConn, targetConn, "client->target")
	t.proxyData(targetConn, clientConn, "target->client")
}

func (t *TCPProxy) proxyData(src, dst net.Conn, direction string) {
	buffer := make([]byte, 32768)

	for {
		n, err := src.Read(buffer)
		if err != nil {
			break
		}

		if _, err := dst.Write(buffer[:n]); err != nil {
			break
		}

		// Mirror additional data if enabled
		if t.mirrorManager != nil {
			go t.mirrorManager.MirrorTCP(src.RemoteAddr().String(), dst.RemoteAddr().String(), buffer[:n])
		}
	}
}
