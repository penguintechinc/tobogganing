// Package network provides high-performance IP address management (IPAM) for CNI pods.
//
// This package implements:
// - Dynamic IP allocation and management for Kubernetes pods
// - Integration with Tobogganing Manager for centralized IP tracking
// - Support for multiple IP pools and subnets
// - Performance-optimized allocation with caching
// - IPv4 and IPv6 dual-stack support
// - Conflict detection and resolution
// - Garbage collection of unused IPs
//
// The network manager coordinates with the Tobogganing Manager service
// to maintain consistent IP allocation across the cluster while providing
// fast local allocation for optimal CNI performance.
package network

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
	"github.com/tobogganing/k8s-cni/pkg/config"
)

// Config represents the network manager configuration
type Config struct {
	IPAM       config.IPAMConfig
	ManagerURL string
	APIKey     string
	ClusterID  string
}

// Manager handles IP address allocation and management
type Manager struct {
	config       *Config
	httpClient   *http.Client
	allocatedIPs map[string]net.IP // containerID -> IP
	ipPool       *IPPool
	mu           sync.RWMutex
	logger       *logrus.Entry
}

// IPPool represents a pool of available IP addresses
type IPPool struct {
	Subnet    *net.IPNet
	Gateway   net.IP
	Available []net.IP
	Used      map[string]net.IP // IP string -> containerID
	mutex     sync.RWMutex
}

// AllocationRequest represents an IP allocation request to the Manager
type AllocationRequest struct {
	ContainerID string `json:"container_id"`
	PodID       string `json:"pod_id"`
	NodeID      string `json:"node_id"`
	ClusterID   string `json:"cluster_id"`
	RequestedIP string `json:"requested_ip,omitempty"`
}

// AllocationResponse represents the Manager's response to IP allocation
type AllocationResponse struct {
	AllocatedIP string `json:"allocated_ip"`
	Gateway     string `json:"gateway"`
	Subnet      string `json:"subnet"`
	Success     bool   `json:"success"`
	Error       string `json:"error,omitempty"`
}

// ReleaseRequest represents an IP release request to the Manager
type ReleaseRequest struct {
	ContainerID string `json:"container_id"`
	AllocatedIP string `json:"allocated_ip"`
	ClusterID   string `json:"cluster_id"`
}

// NewManager creates a new network manager
func NewManager(config *Config) (*Manager, error) {
	logger := logrus.WithFields(logrus.Fields{
		"component": "network-manager",
		"cluster":   config.ClusterID,
	})

	manager := &Manager{
		config:       config,
		httpClient:   &http.Client{Timeout: 30 * time.Second},
		allocatedIPs: make(map[string]net.IP),
		logger:       logger,
	}

	// Initialize IP pool if subnet is configured locally
	if config.IPAM.Subnet != "" {
		pool, err := manager.initializeIPPool()
		if err != nil {
			return nil, fmt.Errorf("failed to initialize IP pool: %w", err)
		}
		manager.ipPool = pool
	}

	return manager, nil
}

// AllocateIP allocates an IP address for a container
func (m *Manager) AllocateIP(ctx context.Context, containerID string) (net.IP, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.logger.WithField("containerID", containerID).Info("allocating IP address")

	// Check if IP is already allocated for this container
	if ip, exists := m.allocatedIPs[containerID]; exists {
		m.logger.WithFields(logrus.Fields{
			"containerID": containerID,
			"ip":          ip.String(),
		}).Info("IP already allocated for container")
		return ip, nil
	}

	var allocatedIP net.IP
	var err error

	// Try local allocation first if we have a pool
	if m.ipPool != nil {
		allocatedIP, err = m.allocateFromLocalPool(containerID)
		if err != nil {
			m.logger.WithError(err).Warn("local allocation failed, trying manager")
		}
	}

	// Fall back to manager allocation if local fails or no local pool
	if allocatedIP == nil {
		allocatedIP, err = m.allocateFromManager(ctx, containerID)
		if err != nil {
			return nil, fmt.Errorf("failed to allocate IP from manager: %w", err)
		}
	}

	// Track allocation
	m.allocatedIPs[containerID] = allocatedIP

	m.logger.WithFields(logrus.Fields{
		"containerID": containerID,
		"ip":          allocatedIP.String(),
	}).Info("successfully allocated IP address")

	return allocatedIP, nil
}

// ReleaseIP releases an IP address for a container
func (m *Manager) ReleaseIP(ctx context.Context, containerID string, ip net.IP) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.logger.WithFields(logrus.Fields{
		"containerID": containerID,
		"ip":          ip.String(),
	}).Info("releasing IP address")

	// Release from local pool if applicable
	if m.ipPool != nil {
		if err := m.releaseToLocalPool(containerID, ip); err != nil {
			m.logger.WithError(err).Warn("failed to release to local pool")
		}
	}

	// Release from manager
	if err := m.releaseToManager(ctx, containerID, ip); err != nil {
		m.logger.WithError(err).Warn("failed to release IP to manager")
	}

	// Remove from tracking
	delete(m.allocatedIPs, containerID)

	m.logger.WithFields(logrus.Fields{
		"containerID": containerID,
		"ip":          ip.String(),
	}).Info("successfully released IP address")

	return nil
}

// GetAllocatedIP returns the allocated IP for a container
func (m *Manager) GetAllocatedIP(containerID string) net.IP {
	m.mu.RLock()
	defer m.mu.RUnlock()
	
	return m.allocatedIPs[containerID]
}

// Close cleans up the network manager
func (m *Manager) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Release all tracked IPs
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	for containerID, ip := range m.allocatedIPs {
		if err := m.releaseToManager(ctx, containerID, ip); err != nil {
			m.logger.WithError(err).WithFields(logrus.Fields{
				"containerID": containerID,
				"ip":          ip.String(),
			}).Warn("failed to release IP during cleanup")
		}
	}

	return nil
}

// initializeIPPool sets up a local IP pool from configuration
func (m *Manager) initializeIPPool() (*IPPool, error) {
	_, subnet, err := net.ParseCIDR(m.config.IPAM.Subnet)
	if err != nil {
		return nil, fmt.Errorf("invalid subnet: %w", err)
	}

	var gateway net.IP
	if m.config.IPAM.Gateway != "" {
		gateway = net.ParseIP(m.config.IPAM.Gateway)
		if gateway == nil {
			return nil, fmt.Errorf("invalid gateway IP: %s", m.config.IPAM.Gateway)
		}
	}

	pool := &IPPool{
		Subnet:  subnet,
		Gateway: gateway,
		Used:    make(map[string]net.IP),
	}

	// Generate available IPs
	if err := m.generateAvailableIPs(pool); err != nil {
		return nil, fmt.Errorf("failed to generate available IPs: %w", err)
	}

	m.logger.WithFields(logrus.Fields{
		"subnet":      subnet.String(),
		"gateway":     gateway.String(),
		"availableIPs": len(pool.Available),
	}).Info("initialized local IP pool")

	return pool, nil
}

// generateAvailableIPs populates the available IP list for a pool
func (m *Manager) generateAvailableIPs(pool *IPPool) error {
	// Get all IPs in the subnet
	ip := pool.Subnet.IP.Mask(pool.Subnet.Mask)
	
	for {
		// Skip network and broadcast addresses
		if !pool.Subnet.Contains(ip) {
			break
		}
		
		// Skip network address (first IP)
		if ip.Equal(pool.Subnet.IP) {
			ip = nextIP(ip)
			continue
		}
		
		// Skip gateway if specified
		if pool.Gateway != nil && ip.Equal(pool.Gateway) {
			ip = nextIP(ip)
			continue
		}
		
		// Skip broadcast address (last IP for IPv4)
		if isLastIP(ip, pool.Subnet) {
			break
		}
		
		// Add to available IPs
		pool.Available = append(pool.Available, copyIP(ip))
		ip = nextIP(ip)
	}
	
	return nil
}

// allocateFromLocalPool allocates an IP from the local pool
func (m *Manager) allocateFromLocalPool(containerID string) (net.IP, error) {
	m.ipPool.mutex.Lock()
	defer m.ipPool.mutex.Unlock()

	if len(m.ipPool.Available) == 0 {
		return nil, fmt.Errorf("no available IPs in local pool")
	}

	// Get first available IP
	ip := m.ipPool.Available[0]
	m.ipPool.Available = m.ipPool.Available[1:]
	
	// Mark as used
	m.ipPool.Used[ip.String()] = ip

	return ip, nil
}

// releaseToLocalPool releases an IP back to the local pool
func (m *Manager) releaseToLocalPool(containerID string, ip net.IP) error {
	m.ipPool.mutex.Lock()
	defer m.ipPool.mutex.Unlock()

	ipStr := ip.String()
	if _, exists := m.ipPool.Used[ipStr]; !exists {
		return fmt.Errorf("IP %s not found in used pool", ipStr)
	}

	// Remove from used
	delete(m.ipPool.Used, ipStr)
	
	// Add back to available
	m.ipPool.Available = append(m.ipPool.Available, ip)

	return nil
}

// allocateFromManager allocates an IP from the Tobogganing Manager
func (m *Manager) allocateFromManager(ctx context.Context, containerID string) (net.IP, error) {
	url := fmt.Sprintf("%s/api/v1/ipam/allocate", m.config.ManagerURL)

	req := &AllocationRequest{
		ContainerID: containerID,
		PodID:       containerID, // Use containerID as podID for simplicity
		NodeID:      m.getNodeID(),
		ClusterID:   m.config.ClusterID,
	}

	reqData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, strings.NewReader(string(reqData)))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+m.config.APIKey)

	resp, err := m.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("manager returned status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	var response AllocationResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w", err)
	}

	if !response.Success {
		return nil, fmt.Errorf("allocation failed: %s", response.Error)
	}

	ip := net.ParseIP(response.AllocatedIP)
	if ip == nil {
		return nil, fmt.Errorf("invalid IP received from manager: %s", response.AllocatedIP)
	}

	return ip, nil
}

// releaseToManager releases an IP to the Tobogganing Manager
func (m *Manager) releaseToManager(ctx context.Context, containerID string, ip net.IP) error {
	url := fmt.Sprintf("%s/api/v1/ipam/release", m.config.ManagerURL)

	req := &ReleaseRequest{
		ContainerID: containerID,
		AllocatedIP: ip.String(),
		ClusterID:   m.config.ClusterID,
	}

	reqData, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, strings.NewReader(string(reqData)))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+m.config.APIKey)

	resp, err := m.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNotFound {
		return fmt.Errorf("manager returned status %d", resp.StatusCode)
	}

	return nil
}

// getNodeID returns the current node identifier
func (m *Manager) getNodeID() string {
	// Try to get from environment first
	if nodeID := os.Getenv("NODE_NAME"); nodeID != "" {
		return nodeID
	}
	
	// Fall back to hostname
	if hostname, err := os.Hostname(); err == nil {
		return hostname
	}
	
	return "unknown"
}

// nextIP returns the next IP address
func nextIP(ip net.IP) net.IP {
	next := make(net.IP, len(ip))
	copy(next, ip)
	
	for j := len(next) - 1; j >= 0; j-- {
		next[j]++
		if next[j] > 0 {
			break
		}
	}
	
	return next
}

// copyIP creates a copy of an IP address
func copyIP(ip net.IP) net.IP {
	dup := make(net.IP, len(ip))
	copy(dup, ip)
	return dup
}

// isLastIP checks if an IP is the last (broadcast) address in a subnet
func isLastIP(ip net.IP, subnet *net.IPNet) bool {
	// For IPv4, check if it's the broadcast address
	if len(ip) == 4 {
		broadcast := make(net.IP, 4)
		for i := 0; i < 4; i++ {
			broadcast[i] = subnet.IP[i] | ^subnet.Mask[i]
		}
		return ip.Equal(broadcast)
	}
	
	// For IPv6, we don't have a broadcast concept, so just check if it's all 1s in host portion
	ones, bits := subnet.Mask.Size()
	if ones == bits {
		return false // No host portion
	}
	
	// Check if all host bits are 1
	hostBytes := (bits - ones + 7) / 8
	for i := len(ip) - hostBytes; i < len(ip); i++ {
		if ip[i] != 0xFF {
			return false
		}
	}
	
	return true
}

// GetPoolStats returns statistics about the IP pool
func (m *Manager) GetPoolStats() map[string]interface{} {
	if m.ipPool == nil {
		return map[string]interface{}{
			"type": "manager-only",
			"allocatedCount": len(m.allocatedIPs),
		}
	}
	
	m.ipPool.mutex.RLock()
	defer m.ipPool.mutex.RUnlock()
	
	return map[string]interface{}{
		"type":           "local-pool",
		"subnet":         m.ipPool.Subnet.String(),
		"gateway":        m.ipPool.Gateway.String(),
		"availableCount": len(m.ipPool.Available),
		"usedCount":      len(m.ipPool.Used),
		"allocatedCount": len(m.allocatedIPs),
	}
}