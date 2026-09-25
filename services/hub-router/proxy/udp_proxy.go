// Package main implements the SASEWaddle headend proxy server.
package main

import (
	"net"
	"time"

	log "github.com/sirupsen/logrus"
)

// UDP Proxy Implementation
func (u *UDPProxy) Start() {
	log.Info("Starting UDP proxy server")

	buffer := make([]byte, 65536)

	for {
		n, clientAddr, err := u.conn.ReadFromUDP(buffer)
		if err != nil {
			log.Errorf("UDP read error: %v", err)
			continue
		}

		// Copy the packet before handing it to a goroutine — buffer is reused
		// by the next ReadFromUDP iteration.
		packet := make([]byte, n)
		copy(packet, buffer[:n])

		// Bound the number of concurrently handled packets with a counting
		// semaphore (u.connSem) so a packet flood cannot fan out into an
		// unbounded number of goroutines/upstream sockets. When the cap is
		// hit, drop the packet and log rather than blocking the read loop
		// or crashing.
		select {
		case u.connSem <- struct{}{}:
			go func() {
				defer func() { <-u.connSem }()
				u.handlePacket(packet, clientAddr)
			}()
		default:
			log.Warnf("UDP packet-handler limit (%d) reached, dropping packet from %s", cap(u.connSem), clientAddr)
		}
	}
}

func (u *UDPProxy) handlePacket(data []byte, clientAddr *net.UDPAddr) {
	// Parse JWT token from UDP packet
	token := extractJWTFromPacket(data)

	// Authenticate using JWT
	user, err := u.authProvider.ValidateToken(token)
	if err != nil {
		log.Errorf("UDP authentication failed: %v", err)
		return
	}

	log.Infof("UDP packet authenticated for user: %s", user.ID)

	// Extract target from packet
	targetHost := extractTargetFromPacket(data)
	if targetHost == "" {
		log.Error("No target host found in UDP packet")
		return
	}

	// Check firewall rules if firewall manager is enabled
	var allowed bool
	if u.firewallManager != nil {
		allowed = u.firewallManager.CheckAccess(user.ID, targetHost)
	} else {
		allowed = true
	}

	if !allowed {
		log.Warnf("Firewall blocked UDP packet for user %s to %s", user.ID, targetHost)

		// Log denied access to syslog
		if u.syslogLogger != nil {
			u.syslogLogger.LogUDPAccess(user.ID, user.Name, clientAddr.String(), targetHost, false)
		}

		return
	}

	log.Debugf("Firewall allowed UDP packet for user %s to %s", user.ID, targetHost)

	// Log allowed access to syslog
	if u.syslogLogger != nil {
		u.syslogLogger.LogUDPAccess(user.ID, user.Name, clientAddr.String(), targetHost, true)
	}

	// Connect to target
	targetAddr, err := net.ResolveUDPAddr("udp", targetHost)
	if err != nil {
		log.Errorf("Failed to resolve target %s: %v", targetHost, err)
		return
	}

	targetConn, err := net.DialUDP("udp", nil, targetAddr)
	if err != nil {
		log.Errorf("Failed to connect to target %s: %v", targetHost, err)
		return
	}
	defer func() {
		if err := targetConn.Close(); err != nil {
			log.Debugf("Error closing target connection: %v", err)
		}
	}()

	idleTimeout := u.idleTimeout
	if idleTimeout <= 0 {
		idleTimeout = 30 * time.Second
	}

	if err := targetConn.SetWriteDeadline(time.Now().Add(idleTimeout)); err != nil {
		log.Errorf("Failed to set write deadline: %v", err)
		return
	}

	// Forward packet to target
	if _, err := targetConn.Write(data); err != nil {
		log.Errorf("Failed to write to target: %v", err)
		return
	}

	// Mirror traffic if enabled
	if u.mirrorManager != nil {
		go u.mirrorManager.MirrorUDP(clientAddr.String(), targetHost, data)
	}

	// Read response and send back
	response := make([]byte, 65536)
	if err := targetConn.SetReadDeadline(time.Now().Add(idleTimeout)); err != nil {
		log.Errorf("Failed to set read deadline: %v", err)
		return
	}
	n, err := targetConn.Read(response)
	if err != nil {
		log.Errorf("Failed to read response from target: %v", err)
		return
	}

	// Send response back to client
	if _, err := u.conn.WriteToUDP(response[:n], clientAddr); err != nil {
		log.Errorf("Failed to write response to client: %v", err)
		return
	}

	// Mirror response if enabled
	if u.mirrorManager != nil {
		go u.mirrorManager.MirrorUDP(targetHost, clientAddr.String(), response[:n])
	}
}
