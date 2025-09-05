// Package ebpf statistics collection and performance monitoring
// 
// This file implements comprehensive statistics collection from eBPF programs,
// providing real-time insights into network performance, policy enforcement,
// and traffic patterns for the Tobogganing Kubernetes CNI.

package ebpf

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/cilium/ebpf"
	"github.com/sirupsen/logrus"
)

// Statistics indices for different eBPF programs
const (
	// Routing statistics
	StatPacketsProcessed = 0
	StatPacketsForwarded = 1
	StatPacketsDropped   = 2
	StatLocalForwards    = 3
	StatRemoteForwards   = 4
	StatPolicyDrops      = 5
	StatFlowCreates      = 6
	StatProcessingTime   = 7

	// Firewall statistics  
	StatFWPacketsProcessed = 0
	StatFWPacketsAllowed   = 1
	StatFWPacketsdenied    = 2
	StatFWPolicyViolations = 3
	StatFWRulesMatched     = 4
	StatFWDefaultAllows    = 5
	StatFWDefaultDenies    = 6
	StatFWProcessingTime   = 7

	// Monitor statistics
	StatMonitorFlows       = 0
	StatMonitorConnections = 1
	StatMonitorEvents      = 2
	StatMonitorAnomalies   = 3
)

// StatsCollector manages statistics collection from eBPF programs
type StatsCollector struct {
	logger   *logrus.Entry
	maps     map[string]*ebpf.Map
	interval time.Duration

	// Current statistics
	mu           sync.RWMutex
	currentStats map[string]uint64
	deltaStats   map[string]uint64
	lastStats    map[string]uint64

	// Performance tracking
	collectionTimes []time.Duration
	errorCount      uint64
	lastCollection  time.Time
}

// NewStatsCollector creates a new statistics collector
func NewStatsCollector(maps map[string]*ebpf.Map, interval time.Duration) (*StatsCollector, error) {
	collector := &StatsCollector{
		logger:          logrus.WithField("component", "stats-collector"),
		maps:            maps,
		interval:        interval,
		currentStats:    make(map[string]uint64),
		deltaStats:      make(map[string]uint64),
		lastStats:       make(map[string]uint64),
		collectionTimes: make([]time.Duration, 0, 100), // Keep last 100 collection times
	}

	return collector, nil
}

// Start begins statistics collection in a background goroutine
func (sc *StatsCollector) Start(ctx context.Context) {
	sc.logger.Info("starting eBPF statistics collection")

	ticker := time.NewTicker(sc.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			sc.logger.Info("stopping statistics collection")
			return

		case <-ticker.C:
			start := time.Now()
			if err := sc.collectStats(); err != nil {
				sc.errorCount++
				sc.logger.WithError(err).Error("failed to collect statistics")
			} else {
				collectionTime := time.Since(start)
				sc.recordCollectionTime(collectionTime)
				sc.lastCollection = time.Now()
			}
		}
	}
}

// collectStats collects statistics from all eBPF maps
func (sc *StatsCollector) collectStats() error {
	sc.mu.Lock()
	defer sc.mu.Unlock()

	newStats := make(map[string]uint64)
	deltas := make(map[string]uint64)

	// Collect routing statistics
	if err := sc.collectRoutingStats(newStats); err != nil {
		return fmt.Errorf("failed to collect routing stats: %w", err)
	}

	// Collect firewall statistics
	if err := sc.collectFirewallStats(newStats); err != nil {
		return fmt.Errorf("failed to collect firewall stats: %w", err)
	}

	// Collect monitor statistics
	if err := sc.collectMonitorStats(newStats); err != nil {
		return fmt.Errorf("failed to collect monitor stats: %w", err)
	}

	// Calculate deltas
	for key, current := range newStats {
		if last, exists := sc.lastStats[key]; exists {
			if current >= last {
				deltas[key] = current - last
			} else {
				// Counter overflow or reset
				deltas[key] = current
			}
		} else {
			deltas[key] = current
		}
	}

	// Update statistics
	sc.currentStats = newStats
	sc.deltaStats = deltas
	sc.lastStats = make(map[string]uint64)
	for k, v := range newStats {
		sc.lastStats[k] = v
	}

	sc.logger.WithFields(logrus.Fields{
		"stats_count": len(newStats),
		"deltas":      len(deltas),
	}).Debug("collected eBPF statistics")

	return nil
}

// collectRoutingStats collects statistics from routing eBPF program
func (sc *StatsCollector) collectRoutingStats(stats map[string]uint64) error {
	statsMap := sc.maps[MapStats]
	if statsMap == nil {
		return nil // Map not available
	}

	// Collect per-CPU statistics and sum them
	statNames := []string{
		"routing.packets_processed",
		"routing.packets_forwarded", 
		"routing.packets_dropped",
		"routing.local_forwards",
		"routing.remote_forwards",
		"routing.policy_drops",
		"routing.flow_creates",
		"routing.processing_time",
	}

	for i, name := range statNames {
		key := uint32(i)
		var values []uint64

		if err := statsMap.Lookup(key, &values); err != nil {
			if !isMapKeyNotExist(err) {
				return fmt.Errorf("failed to lookup stat %s: %w", name, err)
			}
			continue
		}

		// Sum per-CPU values
		var total uint64
		for _, value := range values {
			total += value
		}
		stats[name] = total
	}

	return nil
}

// collectFirewallStats collects statistics from firewall eBPF program
func (sc *StatsCollector) collectFirewallStats(stats map[string]uint64) error {
	firewallStatsMap := sc.maps[MapFirewallStats]
	if firewallStatsMap == nil {
		return nil // Map not available
	}

	statNames := []string{
		"firewall.packets_processed",
		"firewall.packets_allowed",
		"firewall.packets_denied",
		"firewall.policy_violations",
		"firewall.rules_matched",
		"firewall.default_allows",
		"firewall.default_denies",
		"firewall.processing_time",
	}

	for i, name := range statNames {
		key := uint32(i)
		var values []uint64

		if err := firewallStatsMap.Lookup(key, &values); err != nil {
			if !isMapKeyNotExist(err) {
				return fmt.Errorf("failed to lookup firewall stat %s: %w", name, err)
			}
			continue
		}

		// Sum per-CPU values
		var total uint64
		for _, value := range values {
			total += value
		}
		stats[name] = total
	}

	return nil
}

// collectMonitorStats collects statistics from monitor eBPF program
func (sc *StatsCollector) collectMonitorStats(stats map[string]uint64) error {
	monitorStatsMap := sc.maps[MapMonitorStats]
	if monitorStatsMap == nil {
		return nil // Map not available
	}

	// Count active flows
	flowMap := sc.maps[MapFlows]
	if flowMap != nil {
		flowCount := uint64(0)
		iter := flowMap.Iterate()
		var key, value []byte
		for iter.Next(&key, &value) {
			flowCount++
		}
		stats["monitor.active_flows"] = flowCount
	}

	// Count pods
	podMap := sc.maps[MapPods]
	if podMap != nil {
		podCount := uint64(0)
		iter := podMap.Iterate()
		var key, value []byte
		for iter.Next(&key, &value) {
			podCount++
		}
		stats["monitor.tracked_pods"] = podCount
	}

	// Count firewall rules
	policyMap := sc.maps[MapPolicyRules]
	if policyMap != nil {
		ruleCount := uint64(0)
		iter := policyMap.Iterate()
		var key, value []byte
		for iter.Next(&key, &value) {
			ruleCount++
		}
		stats["monitor.firewall_rules"] = ruleCount
	}

	return nil
}

// recordCollectionTime records the time taken to collect statistics
func (sc *StatsCollector) recordCollectionTime(duration time.Duration) {
	// Keep only the last 100 collection times
	if len(sc.collectionTimes) >= 100 {
		sc.collectionTimes = sc.collectionTimes[1:]
	}
	sc.collectionTimes = append(sc.collectionTimes, duration)
}

// GetCurrentStats returns the current statistics snapshot
func (sc *StatsCollector) GetCurrentStats() (map[string]uint64, error) {
	sc.mu.RLock()
	defer sc.mu.RUnlock()

	// Create a copy to avoid concurrent modifications
	stats := make(map[string]uint64)
	for k, v := range sc.currentStats {
		stats[k] = v
	}

	return stats, nil
}

// GetDeltaStats returns the statistics deltas since last collection
func (sc *StatsCollector) GetDeltaStats() (map[string]uint64, error) {
	sc.mu.RLock()
	defer sc.mu.RUnlock()

	// Create a copy to avoid concurrent modifications
	deltas := make(map[string]uint64)
	for k, v := range sc.deltaStats {
		deltas[k] = v
	}

	return deltas, nil
}

// GetPerformanceMetrics returns performance metrics for the stats collector
func (sc *StatsCollector) GetPerformanceMetrics() *StatsCollectorMetrics {
	sc.mu.RLock()
	defer sc.mu.RUnlock()

	metrics := &StatsCollectorMetrics{
		ErrorCount:       sc.errorCount,
		LastCollection:   sc.lastCollection,
		CollectionTimes:  make([]time.Duration, len(sc.collectionTimes)),
		TotalCollections: uint64(len(sc.collectionTimes)),
	}

	copy(metrics.CollectionTimes, sc.collectionTimes)

	// Calculate average collection time
	if len(sc.collectionTimes) > 0 {
		var total time.Duration
		for _, t := range sc.collectionTimes {
			total += t
		}
		metrics.AvgCollectionTime = total / time.Duration(len(sc.collectionTimes))

		// Find min/max collection times
		metrics.MinCollectionTime = sc.collectionTimes[0]
		metrics.MaxCollectionTime = sc.collectionTimes[0]
		for _, t := range sc.collectionTimes {
			if t < metrics.MinCollectionTime {
				metrics.MinCollectionTime = t
			}
			if t > metrics.MaxCollectionTime {
				metrics.MaxCollectionTime = t
			}
		}
	}

	return metrics
}

// GetStatsSummary returns a human-readable summary of key statistics
func (sc *StatsCollector) GetStatsSummary() (*StatsSummary, error) {
	stats, err := sc.GetCurrentStats()
	if err != nil {
		return nil, err
	}

	deltas, err := sc.GetDeltaStats()
	if err != nil {
		return nil, err
	}

	summary := &StatsSummary{
		Timestamp:  time.Now(),
		TotalStats: len(stats),
	}

	// Routing statistics
	summary.Routing.PacketsProcessed = stats["routing.packets_processed"]
	summary.Routing.PacketsForwarded = stats["routing.packets_forwarded"]
	summary.Routing.PacketsDropped = stats["routing.packets_dropped"]
	summary.Routing.LocalForwards = stats["routing.local_forwards"]
	summary.Routing.RemoteForwards = stats["routing.remote_forwards"]
	summary.Routing.ProcessingTimeNs = stats["routing.processing_time"]

	// Calculate rates (per second)
	if sc.interval > 0 {
		intervalSec := float64(sc.interval) / float64(time.Second)
		summary.Routing.PacketRatePS = float64(deltas["routing.packets_processed"]) / intervalSec
		summary.Routing.ForwardRatePS = float64(deltas["routing.packets_forwarded"]) / intervalSec
		summary.Routing.DropRatePS = float64(deltas["routing.packets_dropped"]) / intervalSec
	}

	// Firewall statistics
	summary.Firewall.PacketsProcessed = stats["firewall.packets_processed"]
	summary.Firewall.PacketsAllowed = stats["firewall.packets_allowed"]
	summary.Firewall.PacketsDenied = stats["firewall.packets_denied"]
	summary.Firewall.PolicyViolations = stats["firewall.policy_violations"]
	summary.Firewall.RulesMatched = stats["firewall.rules_matched"]

	// Calculate firewall rates
	if sc.interval > 0 {
		intervalSec := float64(sc.interval) / float64(time.Second)
		summary.Firewall.ProcessRatePS = float64(deltas["firewall.packets_processed"]) / intervalSec
		summary.Firewall.ViolationRatePS = float64(deltas["firewall.policy_violations"]) / intervalSec
	}

	// Monitor statistics
	summary.Monitor.ActiveFlows = stats["monitor.active_flows"]
	summary.Monitor.TrackedPods = stats["monitor.tracked_pods"]
	summary.Monitor.FirewallRules = stats["monitor.firewall_rules"]

	return summary, nil
}

// StatsCollectorMetrics holds performance metrics for the stats collector
type StatsCollectorMetrics struct {
	ErrorCount         uint64
	LastCollection     time.Time
	CollectionTimes    []time.Duration
	TotalCollections   uint64
	AvgCollectionTime  time.Duration
	MinCollectionTime  time.Duration
	MaxCollectionTime  time.Duration
}

// StatsSummary provides a high-level summary of eBPF statistics
type StatsSummary struct {
	Timestamp  time.Time
	TotalStats int

	Routing struct {
		PacketsProcessed  uint64
		PacketsForwarded  uint64
		PacketsDropped    uint64
		LocalForwards     uint64
		RemoteForwards    uint64
		ProcessingTimeNs  uint64
		PacketRatePS      float64
		ForwardRatePS     float64
		DropRatePS        float64
	}

	Firewall struct {
		PacketsProcessed  uint64
		PacketsAllowed    uint64
		PacketsDenied     uint64
		PolicyViolations  uint64
		RulesMatched      uint64
		ProcessRatePS     float64
		ViolationRatePS   float64
	}

	Monitor struct {
		ActiveFlows    uint64
		TrackedPods    uint64
		FirewallRules  uint64
	}
}

// Helper function to check if error is "key not found"
func isMapKeyNotExist(err error) bool {
	return err != nil && err.Error() == "key does not exist"
}