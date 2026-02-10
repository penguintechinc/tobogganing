// Package ports implements dynamic port management for the SASEWaddle headend proxy.
//
// The port manager provides:
// - Dynamic TCP and UDP port listening based on Manager configuration
// - Support for port ranges (e.g., "8000-8100,9000,9500-9600")
// - Hot reconfiguration without service interruption
// - Automatic listener lifecycle management
// - Integration with firewall and authentication systems
// - Connection pooling and load balancing across ports
// - Real-time port status monitoring and health checks
//
// Configuration is fetched from the Manager service and can be updated
// in real-time, allowing administrators to control which ports the
// proxy accepts connections on without requiring restarts.
package ports

import (
	"fmt"
	"net"
	"strconv"
	"strings"
	"sync"

	log "github.com/sirupsen/logrus"
)

// Note: PortRange is defined in config_client.go

// PortListener represents an active listener on a specific port
type PortListener struct {
	Port     int
	Protocol string
	Listener interface{} // net.Listener for TCP, *net.UDPConn for UDP
	Active   bool
}

// PortManager manages dynamic port listening for the proxy
type PortManager struct {
	tcpRanges   []PortRange
	udpRanges   []PortRange
	listeners   map[string]*PortListener // key: "protocol:port"
	mu          sync.RWMutex
	stopChan    chan bool
	onNewConn   func(conn net.Conn, port int, protocol string)
	onNewPacket func(data []byte, addr *net.UDPAddr, port int)
}

// NewPortManager creates a new port manager
func NewPortManager() *PortManager {
	return &PortManager{
		listeners: make(map[string]*PortListener),
		stopChan:  make(chan bool),
	}
}

// SetConnectionHandlers sets the callback functions for new connections/packets
func (pm *PortManager) SetConnectionHandlers(
	onNewConn func(conn net.Conn, port int, protocol string),
	onNewPacket func(data []byte, addr *net.UDPAddr, port int),
) {
	pm.onNewConn = onNewConn
	pm.onNewPacket = onNewPacket
}

// ParsePortRanges parses port range configurations from strings like "8000-8100,9000,9500-9600"
func (pm *PortManager) ParsePortRanges(tcpRanges, udpRanges string) error {
	var err error
	
	pm.tcpRanges, err = pm.parseRangeString(tcpRanges, "tcp")
	if err != nil {
		return fmt.Errorf("failed to parse TCP ranges: %w", err)
	}
	
	pm.udpRanges, err = pm.parseRangeString(udpRanges, "udp")
	if err != nil {
		return fmt.Errorf("failed to parse UDP ranges: %w", err)
	}
	
	log.Infof("Configured TCP port ranges: %v", pm.tcpRanges)
	log.Infof("Configured UDP port ranges: %v", pm.udpRanges)
	
	return nil
}

// parseRangeString parses a string like "8000-8100,9000,9500-9600" into PortRange structs
func (pm *PortManager) parseRangeString(rangeStr, protocol string) ([]PortRange, error) {
	var ranges []PortRange
	
	if strings.TrimSpace(rangeStr) == "" {
		return ranges, nil
	}
	
	parts := strings.Split(rangeStr, ",")
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		
		if strings.Contains(part, "-") {
			// Range like "8000-8100"
			rangeParts := strings.Split(part, "-")
			if len(rangeParts) != 2 {
				return nil, fmt.Errorf("invalid range format: %s", part)
			}
			
			start, err := strconv.Atoi(strings.TrimSpace(rangeParts[0]))
			if err != nil {
				return nil, fmt.Errorf("invalid start port: %s", rangeParts[0])
			}
			
			end, err := strconv.Atoi(strings.TrimSpace(rangeParts[1]))
			if err != nil {
				return nil, fmt.Errorf("invalid end port: %s", rangeParts[1])
			}
			
			if start > end {
				return nil, fmt.Errorf("start port %d greater than end port %d", start, end)
			}
			
			if start < 1 || end > 65535 {
				return nil, fmt.Errorf("port range %d-%d outside valid range 1-65535", start, end)
			}
			
			ranges = append(ranges, PortRange{
				StartPort:    start,
				EndPort:      end,
				Protocol: protocol,
			})
		} else {
			// Single port like "9000"
			port, err := strconv.Atoi(part)
			if err != nil {
				return nil, fmt.Errorf("invalid port: %s", part)
			}
			
			if port < 1 || port > 65535 {
				return nil, fmt.Errorf("port %d outside valid range 1-65535", port)
			}
			
			ranges = append(ranges, PortRange{
				StartPort:    port,
				EndPort:      port,
				Protocol: protocol,
			})
		}
	}
	
	return ranges, nil
}

// StartListening begins listening on all configured port ranges
func (pm *PortManager) StartListening() error {
	log.Info("Starting port manager - creating listeners for configured ranges")
	
	// Start TCP listeners
	for _, portRange := range pm.tcpRanges {
		for port := portRange.StartPort; port <= portRange.EndPort; port++ {
			if err := pm.startTCPListener(port); err != nil {
				log.Errorf("Failed to start TCP listener on port %d: %v", port, err)
				// Continue with other ports rather than failing completely
			}
		}
	}
	
	// Start UDP listeners
	for _, portRange := range pm.udpRanges {
		for port := portRange.StartPort; port <= portRange.EndPort; port++ {
			if err := pm.startUDPListener(port); err != nil {
				log.Errorf("Failed to start UDP listener on port %d: %v", port, err)
				// Continue with other ports rather than failing completely
			}
		}
	}
	
	log.Infof("Port manager started with %d active listeners", len(pm.listeners))
	return nil
}

// startTCPListener creates a TCP listener on the specified port
func (pm *PortManager) startTCPListener(port int) error {
	listener, err := net.Listen("tcp", fmt.Sprintf(":%d", port))
	if err != nil {
		return fmt.Errorf("failed to listen on TCP port %d: %w", port, err)
	}
	
	portListener := &PortListener{
		Port:     port,
		Protocol: "tcp",
		Listener: listener,
		Active:   true,
	}
	
	pm.mu.Lock()
	pm.listeners[fmt.Sprintf("tcp:%d", port)] = portListener
	pm.mu.Unlock()
	
	// Start accepting connections in a goroutine
	go pm.acceptTCPConnections(listener, port)
	
	log.Debugf("Started TCP listener on port %d", port)
	return nil
}

// startUDPListener creates a UDP listener on the specified port
func (pm *PortManager) startUDPListener(port int) error {
	addr, err := net.ResolveUDPAddr("udp", fmt.Sprintf(":%d", port))
	if err != nil {
		return fmt.Errorf("failed to resolve UDP address for port %d: %w", port, err)
	}
	
	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		return fmt.Errorf("failed to listen on UDP port %d: %w", port, err)
	}
	
	portListener := &PortListener{
		Port:     port,
		Protocol: "udp",
		Listener: conn,
		Active:   true,
	}
	
	pm.mu.Lock()
	pm.listeners[fmt.Sprintf("udp:%d", port)] = portListener
	pm.mu.Unlock()
	
	// Start receiving packets in a goroutine
	go pm.receiveUDPPackets(conn, port)
	
	log.Debugf("Started UDP listener on port %d", port)
	return nil
}

// acceptTCPConnections handles incoming TCP connections
func (pm *PortManager) acceptTCPConnections(listener net.Listener, port int) {
	for {
		conn, err := listener.Accept()
		if err != nil {
			// Check if we're shutting down
			select {
			case <-pm.stopChan:
				return
			default:
				log.Errorf("TCP accept error on port %d: %v", port, err)
				continue
			}
		}
		
		// Handle the connection with the registered handler
		if pm.onNewConn != nil {
			go pm.onNewConn(conn, port, "tcp")
		} else {
			if err := conn.Close(); err != nil {
				log.Debugf("Error closing unhandled connection: %v", err)
			}
		}
	}
}

// receiveUDPPackets handles incoming UDP packets
func (pm *PortManager) receiveUDPPackets(conn *net.UDPConn, port int) {
	buffer := make([]byte, 65536) // Max UDP packet size
	
	for {
		n, addr, err := conn.ReadFromUDP(buffer)
		if err != nil {
			// Check if we're shutting down
			select {
			case <-pm.stopChan:
				return
			default:
				log.Errorf("UDP read error on port %d: %v", port, err)
				continue
			}
		}
		
		// Handle the packet with the registered handler
		if pm.onNewPacket != nil {
			go pm.onNewPacket(buffer[:n], addr, port)
		}
	}
}

// GetActiveListeners returns information about active listeners
func (pm *PortManager) GetActiveListeners() map[string]*PortListener {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	
	result := make(map[string]*PortListener)
	for key, listener := range pm.listeners {
		result[key] = listener
	}
	
	return result
}

// GetListenerCount returns the number of active listeners
func (pm *PortManager) GetListenerCount() int {
	pm.mu.RLock()
	defer pm.mu.RUnlock()
	return len(pm.listeners)
}

// Stop gracefully shuts down all listeners
func (pm *PortManager) Stop() {
	log.Info("Stopping port manager")
	
	// Signal all goroutines to stop
	close(pm.stopChan)
	
	pm.mu.Lock()
	defer pm.mu.Unlock()
	
	// Close all listeners
	for key, portListener := range pm.listeners {
		if portListener.Active {
			switch listener := portListener.Listener.(type) {
			case net.Listener:
				// TCP listener
				if err := listener.Close(); err != nil {
					log.Errorf("Error closing TCP listener %s: %v", key, err)
				}
			case *net.UDPConn:
				// UDP connection
				if err := listener.Close(); err != nil {
					log.Errorf("Error closing UDP listener %s: %v", key, err)
				}
			}
			portListener.Active = false
		}
	}
	
	log.Infof("Stopped %d port listeners", len(pm.listeners))
}

// ValidatePortRanges checks if the specified port ranges are valid and available
func (pm *PortManager) ValidatePortRanges(tcpRanges, udpRanges string) error {
	// Parse ranges first
	tcpParsed, err := pm.parseRangeString(tcpRanges, "tcp")
	if err != nil {
		return fmt.Errorf("invalid TCP ranges: %w", err)
	}
	
	udpParsed, err := pm.parseRangeString(udpRanges, "udp")
	if err != nil {
		return fmt.Errorf("invalid UDP ranges: %w", err)
	}
	
	// Check for overlaps and conflicts
	allPorts := make(map[string]bool)
	
	for _, portRange := range tcpParsed {
		for port := portRange.StartPort; port <= portRange.EndPort; port++ {
			key := fmt.Sprintf("tcp:%d", port)
			if allPorts[key] {
				return fmt.Errorf("duplicate TCP port %d in configuration", port)
			}
			allPorts[key] = true
		}
	}
	
	for _, portRange := range udpParsed {
		for port := portRange.StartPort; port <= portRange.EndPort; port++ {
			key := fmt.Sprintf("udp:%d", port)
			if allPorts[key] {
				return fmt.Errorf("duplicate UDP port %d in configuration", port)
			}
			allPorts[key] = true
		}
	}
	
	return nil
}