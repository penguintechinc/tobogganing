// Package ebpf provides eBPF program loading, management and interaction
// for high-performance networking in the Tobogganing Kubernetes CNI.
//
// This package implements:
// - eBPF program compilation and loading
// - BPF map management and data synchronization
// - TC (Traffic Control) hook attachment
// - Performance monitoring and statistics collection
// - Policy rule management and updates
// - Real-time event processing from eBPF programs
//
// The eBPF programs provide fast-path routing, firewall enforcement,
// and comprehensive traffic monitoring with minimal performance overhead.
package ebpf

import (
	"context"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"sync"
	"time"
	"unsafe"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/link"
	"github.com/cilium/ebpf/rlimit"
	"github.com/sirupsen/logrus"
	"github.com/vishvananda/netlink"
)

const (
	// eBPF program paths
	RoutingProgram  = "routing.o"
	FirewallProgram = "firewall.o"
	MonitorProgram  = "monitor.o"

	// Map names
	MapPods          = "pod_map"
	MapFlows         = "flow_map"
	MapPolicyRules   = "policy_rules"
	MapPodNamespaces = "pod_namespaces"
	MapStats         = "stats_map"
	MapFirewallStats = "firewall_stats"
	MapMonitorStats  = "monitor_stats"

	// Default values
	DefaultMaxPods   = 4096
	DefaultMaxFlows  = 65536
	DefaultMaxRules  = 8192
	
	// Statistics update interval
	StatsUpdateInterval = 30 * time.Second
)

// ProgramType represents the type of eBPF program
type ProgramType int

const (
	ProgramTypeRouting ProgramType = iota
	ProgramTypeFirewall
	ProgramTypeMonitor
)

// Manager manages eBPF programs and their lifecycle
type Manager struct {
	logger *logrus.Entry
	config *Config

	// eBPF collections and links
	routingColl  *ebpf.Collection
	firewallColl *ebpf.Collection
	monitorColl  *ebpf.Collection

	// TC links for traffic control
	ingressLinks map[string]link.Link
	egressLinks  map[string]link.Link

	// BPF maps for data exchange
	maps map[string]*ebpf.Map

	// Statistics and monitoring
	statsCollector *StatsCollector
	eventProcessor *EventProcessor

	// Synchronization
	mu     sync.RWMutex
	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

// Config holds eBPF manager configuration
type Config struct {
	ProgramDir    string        // Directory containing compiled eBPF programs
	MaxPods       int           // Maximum number of pods to track
	MaxFlows      int           // Maximum number of flows to track
	MaxRules      int           // Maximum number of firewall rules
	StatsInterval time.Duration // Statistics collection interval
	Debug         bool          // Enable debug logging
}

// PodInfo represents pod information for eBPF maps
type PodInfo struct {
	PodIP       net.IP
	NodeLocal   bool
	NamespaceID uint32
	LastSeen    uint64
	PodName     string
	Namespace   string
}

// FirewallRule represents a firewall rule for eBPF enforcement
type FirewallRule struct {
	RuleID        uint32
	Priority      uint32
	SrcNamespace  uint32
	DstNamespace  uint32
	SrcIP         net.IP
	SrcMask       net.IPMask
	DstIP         net.IP
	DstMask       net.IPMask
	SrcPortStart  uint16
	SrcPortEnd    uint16
	DstPortStart  uint16
	DstPortEnd    uint16
	Protocol      uint8
	Direction     uint8 // 0=ingress, 1=egress, 2=both
	Action        uint8 // 0=deny, 1=allow, 2=log
	Enabled       bool
	CreatedTime   uint64
}

// FlowStats represents traffic flow statistics
type FlowStats struct {
	PacketsTotal uint64
	BytesTotal   uint64
	PacketsIn    uint64
	BytesIn      uint64
	PacketsOut   uint64
	BytesOut     uint64
	FirstSeen    uint64
	LastSeen     uint64
	Duration     uint64
}

// NewManager creates a new eBPF manager instance
func NewManager(config *Config) (*Manager, error) {
	if config == nil {
		config = &Config{
			ProgramDir:    "/opt/tobogganing/ebpf",
			MaxPods:       DefaultMaxPods,
			MaxFlows:      DefaultMaxFlows,
			MaxRules:      DefaultMaxRules,
			StatsInterval: StatsUpdateInterval,
			Debug:         false,
		}
	}

	// Set defaults
	if config.ProgramDir == "" {
		config.ProgramDir = "/opt/tobogganing/ebpf"
	}
	if config.MaxPods == 0 {
		config.MaxPods = DefaultMaxPods
	}
	if config.MaxFlows == 0 {
		config.MaxFlows = DefaultMaxFlows
	}
	if config.MaxRules == 0 {
		config.MaxRules = DefaultMaxRules
	}
	if config.StatsInterval == 0 {
		config.StatsInterval = StatsUpdateInterval
	}

	logger := logrus.WithField("component", "ebpf-manager")
	if config.Debug {
		logger.Logger.SetLevel(logrus.DebugLevel)
	}

	ctx, cancel := context.WithCancel(context.Background())

	manager := &Manager{
		logger:       logger,
		config:       config,
		ctx:          ctx,
		cancel:       cancel,
		ingressLinks: make(map[string]link.Link),
		egressLinks:  make(map[string]link.Link),
		maps:         make(map[string]*ebpf.Map),
	}

	return manager, nil
}

// Initialize sets up the eBPF environment and loads programs
func (m *Manager) Initialize() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.logger.Info("initializing eBPF manager")

	// Remove memory limit for eBPF
	if err := rlimit.RemoveMemlock(); err != nil {
		return fmt.Errorf("failed to remove memlock limit: %w", err)
	}

	// Load eBPF programs
	if err := m.loadPrograms(); err != nil {
		return fmt.Errorf("failed to load eBPF programs: %w", err)
	}

	// Initialize statistics collector
	statsCollector, err := NewStatsCollector(m.maps, m.config.StatsInterval)
	if err != nil {
		return fmt.Errorf("failed to create stats collector: %w", err)
	}
	m.statsCollector = statsCollector

	// Initialize event processor
	eventProcessor, err := NewEventProcessor(m.maps)
	if err != nil {
		return fmt.Errorf("failed to create event processor: %w", err)
	}
	m.eventProcessor = eventProcessor

	// Start background tasks
	m.startBackgroundTasks()

	m.logger.Info("eBPF manager initialized successfully")
	return nil
}

// loadPrograms loads all eBPF programs from disk
func (m *Manager) loadPrograms() error {
	// Load routing program
	routingPath := filepath.Join(m.config.ProgramDir, RoutingProgram)
	if _, err := os.Stat(routingPath); err == nil {
		routingColl, err := ebpf.LoadCollection(routingPath)
		if err != nil {
			return fmt.Errorf("failed to load routing program: %w", err)
		}
		m.routingColl = routingColl
		m.logger.Debug("loaded routing eBPF program")

		// Register maps from routing collection
		for name, bpfMap := range routingColl.Maps {
			m.maps[name] = bpfMap
		}
	}

	// Load firewall program
	firewallPath := filepath.Join(m.config.ProgramDir, FirewallProgram)
	if _, err := os.Stat(firewallPath); err == nil {
		firewallColl, err := ebpf.LoadCollection(firewallPath)
		if err != nil {
			return fmt.Errorf("failed to load firewall program: %w", err)
		}
		m.firewallColl = firewallColl
		m.logger.Debug("loaded firewall eBPF program")

		// Register maps from firewall collection
		for name, bpfMap := range firewallColl.Maps {
			m.maps[name] = bpfMap
		}
	}

	// Load monitor program
	monitorPath := filepath.Join(m.config.ProgramDir, MonitorProgram)
	if _, err := os.Stat(monitorPath); err == nil {
		monitorColl, err := ebpf.LoadCollection(monitorPath)
		if err != nil {
			return fmt.Errorf("failed to load monitor program: %w", err)
		}
		m.monitorColl = monitorColl
		m.logger.Debug("loaded monitor eBPF program")

		// Register maps from monitor collection
		for name, bpfMap := range monitorColl.Maps {
			m.maps[name] = bpfMap
		}
	}

	return nil
}

// AttachToInterface attaches eBPF programs to a network interface
func (m *Manager) AttachToInterface(ifaceName string, programTypes ...ProgramType) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	iface, err := netlink.LinkByName(ifaceName)
	if err != nil {
		return fmt.Errorf("failed to find interface %s: %w", ifaceName, err)
	}

	m.logger.WithField("interface", ifaceName).Info("attaching eBPF programs to interface")

	for _, progType := range programTypes {
		if err := m.attachProgram(iface, progType); err != nil {
			return fmt.Errorf("failed to attach program type %d to interface %s: %w", progType, ifaceName, err)
		}
	}

	return nil
}

// attachProgram attaches a specific eBPF program to an interface
func (m *Manager) attachProgram(iface netlink.Link, progType ProgramType) error {
	var ingressProg, egressProg *ebpf.Program
	var progName string

	switch progType {
	case ProgramTypeRouting:
		if m.routingColl == nil {
			return fmt.Errorf("routing program not loaded")
		}
		ingressProg = m.routingColl.Programs["tc_ingress_handler"]
		egressProg = m.routingColl.Programs["tc_egress_handler"]
		progName = "routing"

	case ProgramTypeFirewall:
		if m.firewallColl == nil {
			return fmt.Errorf("firewall program not loaded")
		}
		ingressProg = m.firewallColl.Programs["firewall_ingress"]
		egressProg = m.firewallColl.Programs["firewall_egress"]
		progName = "firewall"

	case ProgramTypeMonitor:
		if m.monitorColl == nil {
			return fmt.Errorf("monitor program not loaded")
		}
		ingressProg = m.monitorColl.Programs["monitor_ingress"]
		egressProg = m.monitorColl.Programs["monitor_egress"]
		progName = "monitor"

	default:
		return fmt.Errorf("unknown program type: %d", progType)
	}

	ifaceName := iface.Attrs().Name

	// Attach ingress program
	if ingressProg != nil {
		ingressLink, err := link.AttachTCX(link.TCXOptions{
			Interface: iface.Attrs().Index,
			Program:   ingressProg,
			Attach:    ebpf.AttachTCXIngress,
		})
		if err != nil {
			return fmt.Errorf("failed to attach %s ingress program: %w", progName, err)
		}

		linkKey := fmt.Sprintf("%s-%s-ingress", ifaceName, progName)
		m.ingressLinks[linkKey] = ingressLink
		m.logger.WithFields(logrus.Fields{
			"interface": ifaceName,
			"program":   progName,
			"direction": "ingress",
		}).Debug("attached eBPF program")
	}

	// Attach egress program
	if egressProg != nil {
		egressLink, err := link.AttachTCX(link.TCXOptions{
			Interface: iface.Attrs().Index,
			Program:   egressProg,
			Attach:    ebpf.AttachTCXEgress,
		})
		if err != nil {
			return fmt.Errorf("failed to attach %s egress program: %w", progName, err)
		}

		linkKey := fmt.Sprintf("%s-%s-egress", ifaceName, progName)
		m.egressLinks[linkKey] = egressLink
		m.logger.WithFields(logrus.Fields{
			"interface": ifaceName,
			"program":   progName,
			"direction": "egress",
		}).Debug("attached eBPF program")
	}

	return nil
}

// DetachFromInterface detaches eBPF programs from a network interface
func (m *Manager) DetachFromInterface(ifaceName string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.logger.WithField("interface", ifaceName).Info("detaching eBPF programs from interface")

	// Detach ingress links
	for linkKey, link := range m.ingressLinks {
		if contains(linkKey, ifaceName) {
			if err := link.Close(); err != nil {
				m.logger.WithError(err).Warn("failed to close ingress link")
			}
			delete(m.ingressLinks, linkKey)
		}
	}

	// Detach egress links
	for linkKey, link := range m.egressLinks {
		if contains(linkKey, ifaceName) {
			if err := link.Close(); err != nil {
				m.logger.WithError(err).Warn("failed to close egress link")
			}
			delete(m.egressLinks, linkKey)
		}
	}

	return nil
}

// UpdatePodInfo updates pod information in eBPF maps
func (m *Manager) UpdatePodInfo(podIP net.IP, info *PodInfo) error {
	m.mu.RLock()
	podMap := m.maps[MapPods]
	m.mu.RUnlock()

	if podMap == nil {
		return fmt.Errorf("pod map not found")
	}

	// Convert to eBPF map format
	key := ipToUint32(podIP)
	value := podInfoToBytes(info)

	if err := podMap.Update(key, value, ebpf.UpdateAny); err != nil {
		return fmt.Errorf("failed to update pod info: %w", err)
	}

	m.logger.WithFields(logrus.Fields{
		"pod_ip":    podIP.String(),
		"pod_name":  info.PodName,
		"namespace": info.Namespace,
	}).Debug("updated pod info in eBPF map")

	return nil
}

// RemovePodInfo removes pod information from eBPF maps
func (m *Manager) RemovePodInfo(podIP net.IP) error {
	m.mu.RLock()
	podMap := m.maps[MapPods]
	m.mu.RUnlock()

	if podMap == nil {
		return fmt.Errorf("pod map not found")
	}

	key := ipToUint32(podIP)
	if err := podMap.Delete(key); err != nil {
		return fmt.Errorf("failed to remove pod info: %w", err)
	}

	m.logger.WithField("pod_ip", podIP.String()).Debug("removed pod info from eBPF map")
	return nil
}

// UpdateFirewallRule updates a firewall rule in eBPF maps
func (m *Manager) UpdateFirewallRule(rule *FirewallRule) error {
	m.mu.RLock()
	policyMap := m.maps[MapPolicyRules]
	m.mu.RUnlock()

	if policyMap == nil {
		return fmt.Errorf("policy rules map not found")
	}

	key := rule.RuleID
	value := firewallRuleToBytes(rule)

	if err := policyMap.Update(key, value, ebpf.UpdateAny); err != nil {
		return fmt.Errorf("failed to update firewall rule: %w", err)
	}

	m.logger.WithFields(logrus.Fields{
		"rule_id":  rule.RuleID,
		"priority": rule.Priority,
		"action":   rule.Action,
	}).Debug("updated firewall rule in eBPF map")

	return nil
}

// RemoveFirewallRule removes a firewall rule from eBPF maps
func (m *Manager) RemoveFirewallRule(ruleID uint32) error {
	m.mu.RLock()
	policyMap := m.maps[MapPolicyRules]
	m.mu.RUnlock()

	if policyMap == nil {
		return fmt.Errorf("policy rules map not found")
	}

	if err := policyMap.Delete(ruleID); err != nil {
		return fmt.Errorf("failed to remove firewall rule: %w", err)
	}

	m.logger.WithField("rule_id", ruleID).Debug("removed firewall rule from eBPF map")
	return nil
}

// GetFlowStats retrieves flow statistics from eBPF maps
func (m *Manager) GetFlowStats() (map[string]*FlowStats, error) {
	m.mu.RLock()
	flowMap := m.maps[MapFlows]
	m.mu.RUnlock()

	if flowMap == nil {
		return nil, fmt.Errorf("flow map not found")
	}

	flows := make(map[string]*FlowStats)
	var key, value []byte

	iter := flowMap.Iterate()
	for iter.Next(&key, &value) {
		flowKey := bytesToFlowKey(key)
		flowStats := bytesToFlowStats(value)
		
		keyStr := fmt.Sprintf("%s:%d->%s:%d/%d", 
			uint32ToIP(flowKey.SrcIP).String(), flowKey.SrcPort,
			uint32ToIP(flowKey.DstIP).String(), flowKey.DstPort,
			flowKey.Protocol)
		
		flows[keyStr] = flowStats
	}

	if err := iter.Err(); err != nil {
		return nil, fmt.Errorf("failed to iterate flow map: %w", err)
	}

	return flows, nil
}

// GetStatistics retrieves current eBPF program statistics
func (m *Manager) GetStatistics() (map[string]uint64, error) {
	if m.statsCollector == nil {
		return nil, fmt.Errorf("stats collector not initialized")
	}

	return m.statsCollector.GetCurrentStats()
}

// startBackgroundTasks starts background goroutines for statistics collection and event processing
func (m *Manager) startBackgroundTasks() {
	// Start statistics collector
	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		m.statsCollector.Start(m.ctx)
	}()

	// Start event processor
	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		m.eventProcessor.Start(m.ctx)
	}()
}

// Close shuts down the eBPF manager and cleans up resources
func (m *Manager) Close() error {
	m.logger.Info("shutting down eBPF manager")

	// Cancel context to stop background tasks
	m.cancel()

	// Wait for background tasks to complete
	m.wg.Wait()

	m.mu.Lock()
	defer m.mu.Unlock()

	// Close all TC links
	for linkKey, link := range m.ingressLinks {
		if err := link.Close(); err != nil {
			m.logger.WithError(err).WithField("link", linkKey).Warn("failed to close ingress link")
		}
	}

	for linkKey, link := range m.egressLinks {
		if err := link.Close(); err != nil {
			m.logger.WithError(err).WithField("link", linkKey).Warn("failed to close egress link")
		}
	}

	// Close eBPF collections
	if m.routingColl != nil {
		if err := m.routingColl.Close(); err != nil {
			m.logger.WithError(err).Warn("failed to close routing collection")
		}
	}

	if m.firewallColl != nil {
		if err := m.firewallColl.Close(); err != nil {
			m.logger.WithError(err).Warn("failed to close firewall collection")
		}
	}

	if m.monitorColl != nil {
		if err := m.monitorColl.Close(); err != nil {
			m.logger.WithError(err).Warn("failed to close monitor collection")
		}
	}

	m.logger.Info("eBPF manager shut down complete")
	return nil
}

// Helper functions for data conversion

func ipToUint32(ip net.IP) uint32 {
	ip = ip.To4()
	if ip == nil {
		return 0
	}
	return uint32(ip[0])<<24 | uint32(ip[1])<<16 | uint32(ip[2])<<8 | uint32(ip[3])
}

func uint32ToIP(ip uint32) net.IP {
	return net.IPv4(byte(ip>>24), byte(ip>>16), byte(ip>>8), byte(ip))
}

func podInfoToBytes(info *PodInfo) []byte {
	// In a real implementation, this would properly serialize the PodInfo struct
	// For now, return a placeholder
	return make([]byte, 256)
}

func firewallRuleToBytes(rule *FirewallRule) []byte {
	// In a real implementation, this would properly serialize the FirewallRule struct
	// For now, return a placeholder
	return make([]byte, 512)
}

func bytesToFlowKey(data []byte) *FlowKey {
	// In a real implementation, this would deserialize bytes to FlowKey
	return &FlowKey{}
}

func bytesToFlowStats(data []byte) *FlowStats {
	// In a real implementation, this would deserialize bytes to FlowStats
	return &FlowStats{}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && s[:len(substr)] == substr
}

// FlowKey represents a flow key for statistics
type FlowKey struct {
	SrcIP     uint32
	DstIP     uint32
	SrcPort   uint16
	DstPort   uint16
	Protocol  uint8
	Direction uint8
	SrcPodID  uint32
	DstPodID  uint32
}