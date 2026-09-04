// Package main implements the SASEWaddle headend proxy server.
package main

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	log "github.com/sirupsen/logrus"
	"github.com/spf13/viper"

	"github.com/tobogganing/headend/proxy/ports"
)

func (s *ProxyServer) Run() error {
	httpPort := viper.GetString("server.http_port")
	certFile := viper.GetString("server.cert_file")
	keyFile := viper.GetString("server.key_file")

	s.httpServer = &http.Server{
		Addr:         ":" + httpPort,
		Handler:      s.router,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// Graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan

		log.Info("Shutting down server...")

		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		if s.mirrorManager != nil {
			s.mirrorManager.Stop()
		}

		if s.firewallManager != nil {
			s.firewallManager.Stop()
		}

		if s.syslogLogger != nil {
			s.syslogLogger.Stop()
		}

		if s.portManager != nil {
			s.portManager.Stop()
		}

		// Close TCP and UDP proxies
		if s.tcpProxy != nil && s.tcpProxy.listener != nil {
			if err := s.tcpProxy.listener.Close(); err != nil {
				log.Errorf("Failed to close TCP listener: %v", err)
			}
		}
		if s.udpProxy != nil && s.udpProxy.conn != nil {
			if err := s.udpProxy.conn.Close(); err != nil {
				log.Errorf("Failed to close UDP connection: %v", err)
			}
		}

		if err := s.httpServer.Shutdown(ctx); err != nil {
			log.Errorf("Server shutdown error: %v", err)
		}
	}()

	log.Infof("Starting headend HTTP proxy on port %s", httpPort)

	if certFile != "" && keyFile != "" {
		return s.httpServer.ListenAndServeTLS(certFile, keyFile)
	}

	return s.httpServer.ListenAndServe()
}

func (s *ProxyServer) initializeTCPProxy() error {
	tcpPort := viper.GetString("server.tcp_port")

	listener, err := net.Listen("tcp", ":"+tcpPort)
	if err != nil {
		return fmt.Errorf("failed to create TCP listener: %w", err)
	}

	s.tcpProxy = &TCPProxy{
		listener:        listener,
		authProvider:    s.authProvider,
		mirrorManager:   s.mirrorManager,
		firewallManager: s.firewallManager,
		syslogLogger:    s.syslogLogger,
		wgRouter:        s.wgRouter,
	}

	// Start TCP proxy in goroutine
	go s.tcpProxy.Start()

	log.Infof("TCP proxy listening on port %s", tcpPort)
	return nil
}

func (s *ProxyServer) initializeUDPProxy() error {
	udpPort := viper.GetString("server.udp_port")

	addr, err := net.ResolveUDPAddr("udp", ":"+udpPort)
	if err != nil {
		return fmt.Errorf("failed to resolve UDP address: %w", err)
	}

	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		return fmt.Errorf("failed to create UDP listener: %w", err)
	}

	s.udpProxy = &UDPProxy{
		conn:            conn,
		authProvider:    s.authProvider,
		mirrorManager:   s.mirrorManager,
		firewallManager: s.firewallManager,
		syslogLogger:    s.syslogLogger,
		wgRouter:        s.wgRouter,
	}

	// Start UDP proxy in goroutine
	go s.udpProxy.Start()

	log.Infof("UDP proxy listening on port %s", udpPort)
	return nil
}

// refreshPortConfig periodically fetches updated port configuration from the Manager
func (s *ProxyServer) refreshPortConfig(configClient *ports.ConfigClient) {
	refreshInterval, err := time.ParseDuration(viper.GetString("ports.refresh_interval"))
	if err != nil {
		refreshInterval = 60 * time.Second
	}

	ticker := time.NewTicker(refreshInterval)
	defer ticker.Stop()

	for range ticker.C {
		config, err := configClient.FetchConfig()
		if err != nil {
			log.Errorf("Failed to refresh port config: %v", err)
			continue
		}

		// Validate the configuration
		if err := configClient.ValidateConfig(config); err != nil {
			log.Errorf("Invalid port config received: %v", err)
			continue
		}

		// Update port manager configuration
		if err := s.updatePortConfiguration(config); err != nil {
			log.Errorf("Failed to update port configuration: %v", err)
		} else {
			log.Infof("Updated port configuration: TCP=%s, UDP=%s", config.TCPRanges, config.UDPRanges)
		}
	}
}

// updatePortConfiguration applies new port configuration to the port manager
func (s *ProxyServer) updatePortConfiguration(config *ports.PortConfig) error {
	// Stop current listeners
	s.portManager.Stop()

	// Create new port manager with updated config
	s.portManager = ports.NewPortManager()
	s.portManager.SetConnectionHandlers(
		s.handleDynamicTCPConnection,
		s.handleDynamicUDPPacket,
	)

	// Parse and apply new configuration
	if err := s.portManager.ParsePortRanges(config.TCPRanges, config.UDPRanges); err != nil {
		return fmt.Errorf("failed to parse port ranges: %w", err)
	}

	if err := s.portManager.StartListening(); err != nil {
		return fmt.Errorf("failed to start listeners: %w", err)
	}

	return nil
}

// handleDynamicTCPConnection handles new TCP connections on dynamically configured ports
func (s *ProxyServer) handleDynamicTCPConnection(conn net.Conn, port int, protocol string) {
	defer func() {
		if err := conn.Close(); err != nil {
			log.Debugf("Error closing connection: %v", err)
		}
	}()

	log.Debugf("New TCP connection on dynamic port %d from %s", port, conn.RemoteAddr())

	// Read first packet to extract authentication and target information
	buffer := make([]byte, 4096)
	n, err := conn.Read(buffer)
	if err != nil {
		log.Errorf("Failed to read from TCP connection on port %d: %v", port, err)
		return
	}

	// Extract JWT token and target from the packet
	token := extractJWTFromPacket(buffer[:n])
	targetHost := extractTargetFromPacket(buffer[:n])

	if token == "" || targetHost == "" {
		log.Errorf("Missing authentication or target in TCP packet on port %d", port)
		return
	}

	// Authenticate using JWT
	user, err := s.authProvider.ValidateToken(token)
	if err != nil {
		log.Errorf("Authentication failed for TCP connection on port %d: %v", port, err)
		return
	}

	log.Infof("Authenticated TCP connection on port %d for user: %s to %s", port, user.ID, targetHost)

	// Check firewall rules
	if s.firewallManager != nil {
		allowed := s.firewallManager.CheckAccess(user.ID, targetHost)
		if !allowed {
			log.Warnf("Firewall blocked TCP connection on port %d for user %s to %s", port, user.ID, targetHost)

			// Log denied access to syslog
			if s.syslogLogger != nil {
				s.syslogLogger.LogTCPAccess(user.ID, user.Name, conn.RemoteAddr().String(), targetHost, false)
			}
			return
		}
	}

	// Log allowed access to syslog
	if s.syslogLogger != nil {
		s.syslogLogger.LogTCPAccess(user.ID, user.Name, conn.RemoteAddr().String(), targetHost, true)
	}

	// Use WireGuard router if available for intelligent routing
	if s.wgRouter != nil {
		log.Infof("Using WireGuard router for dynamic TCP traffic to %s on port %d", targetHost, port)
		if err := s.wgRouter.RouteTraffic(targetHost, conn); err != nil {
			log.Errorf("WireGuard routing failed for %s on port %d: %v", targetHost, port, err)
		}
		return
	}

	// Fallback to direct connection
	targetConn, err := net.Dial("tcp", targetHost)
	if err != nil {
		log.Errorf("Failed to connect to target %s from port %d: %v", targetHost, port, err)
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
	if s.mirrorManager != nil {
		go s.mirrorManager.MirrorTCP(conn.RemoteAddr().String(), targetHost, buffer[:n])
	}

	// Bidirectional proxy
	go s.proxyTCPData(conn, targetConn, fmt.Sprintf("client->target (port %d)", port))
	s.proxyTCPData(targetConn, conn, fmt.Sprintf("target->client (port %d)", port))
}

// handleDynamicUDPPacket handles new UDP packets on dynamically configured ports
func (s *ProxyServer) handleDynamicUDPPacket(data []byte, addr *net.UDPAddr, port int) {
	log.Debugf("New UDP packet on dynamic port %d from %s", port, addr)

	// Extract JWT token and target from the packet
	token := extractJWTFromPacket(data)
	targetHost := extractTargetFromPacket(data)

	if token == "" || targetHost == "" {
		log.Errorf("Missing authentication or target in UDP packet on port %d", port)
		return
	}

	// Authenticate using JWT
	user, err := s.authProvider.ValidateToken(token)
	if err != nil {
		log.Errorf("Authentication failed for UDP packet on port %d: %v", port, err)
		return
	}

	log.Infof("Authenticated UDP packet on port %d for user: %s to %s", port, user.ID, targetHost)

	// Check firewall rules
	if s.firewallManager != nil {
		allowed := s.firewallManager.CheckAccess(user.ID, targetHost)
		if !allowed {
			log.Warnf("Firewall blocked UDP packet on port %d for user %s to %s", port, user.ID, targetHost)

			// Log denied access to syslog
			if s.syslogLogger != nil {
				s.syslogLogger.LogUDPAccess(user.ID, user.Name, addr.String(), targetHost, false)
			}
			return
		}
	}

	// Log allowed access to syslog
	if s.syslogLogger != nil {
		s.syslogLogger.LogUDPAccess(user.ID, user.Name, addr.String(), targetHost, true)
	}

	// Connect to target
	targetAddr, err := net.ResolveUDPAddr("udp", targetHost)
	if err != nil {
		log.Errorf("Failed to resolve target %s from port %d: %v", targetHost, port, err)
		return
	}

	targetConn, err := net.DialUDP("udp", nil, targetAddr)
	if err != nil {
		log.Errorf("Failed to connect to target %s from port %d: %v", targetHost, port, err)
		return
	}
	defer func() {
		if err := targetConn.Close(); err != nil {
			log.Debugf("Error closing target connection: %v", err)
		}
	}()

	// Forward packet to target
	if _, err := targetConn.Write(data); err != nil {
		log.Errorf("Failed to write to target: %v", err)
		return
	}

	// Mirror traffic if enabled
	if s.mirrorManager != nil {
		go s.mirrorManager.MirrorUDP(addr.String(), targetHost, data)
	}

	// Read response and send back (UDP response handling would need port manager support)
	response := make([]byte, 65536)
	if err := targetConn.SetReadDeadline(time.Now().Add(30 * time.Second)); err != nil {
		log.Errorf("Failed to set read deadline: %v", err)
		return
	}
	n, err := targetConn.Read(response)
	if err != nil {
		log.Debugf("No response from target %s (normal for UDP)", targetHost)
		return
	}

	log.Debugf("Received %d bytes response from target %s", n, targetHost)
}

// proxyTCPData proxies data between two TCP connections
func (s *ProxyServer) proxyTCPData(src, dst net.Conn, direction string) {
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
		if s.mirrorManager != nil {
			go s.mirrorManager.MirrorTCP(src.RemoteAddr().String(), dst.RemoteAddr().String(), buffer[:n])
		}
	}
}
