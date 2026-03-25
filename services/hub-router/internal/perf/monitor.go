package perf

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	log "github.com/sirupsen/logrus"

	"github.com/tobogganing/headend/internal/perf/protocols"
)

// FabricMonitor periodically probes peer hub-router nodes and ships
// latency/jitter/packet-loss metrics to Prometheus and hub-api.
type FabricMonitor struct {
	config     Config
	httpClient *http.Client
	cancelFunc context.CancelFunc
}

// NewFabricMonitor creates a FabricMonitor from the given Config.
func NewFabricMonitor(cfg Config) *FabricMonitor {
	return &FabricMonitor{
		config:     cfg,
		httpClient: &http.Client{Timeout: 30 * time.Second},
	}
}

// Start launches the background probe loop. It is a no-op when disabled.
func (m *FabricMonitor) Start(ctx context.Context) error {
	if !m.config.Enabled {
		log.Info("Fabric performance monitor disabled")
		return nil
	}

	ctx, cancel := context.WithCancel(ctx)
	m.cancelFunc = cancel

	interval := time.Duration(m.config.Interval) * time.Second

	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		// Run an immediate probe round on startup.
		m.runProbes()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				m.runProbes()
			}
		}
	}()

	log.WithFields(log.Fields{
		"interval": interval,
		"targets":  len(m.config.Targets),
	}).Info("Fabric performance monitor started")

	return nil
}

// Stop cancels the background probe loop.
func (m *FabricMonitor) Stop() {
	if m.cancelFunc != nil {
		m.cancelFunc()
	}
	log.Info("Fabric performance monitor stopped")
}

// IsRunning reports whether the monitor's probe loop is active.
func (m *FabricMonitor) IsRunning() bool {
	return m.cancelFunc != nil
}

// runProbes fans out a probe goroutine per configured target.
func (m *FabricMonitor) runProbes() {
	for _, target := range m.config.Targets {
		go m.probeTarget(target)
	}
}

// probeTarget runs HTTP, TCP, and ICMP probes against a single peer node.
func (m *FabricMonitor) probeTarget(target string) {
	timeout := 10 * time.Second

	// HTTP probe against the peer's health endpoint.
	httpResult := protocols.RunHTTPTest(fmt.Sprintf("https://%s/healthz", target), timeout)
	if httpResult.Success {
		fabricLatency.WithLabelValues(m.config.SourceID, target, "http").Observe(httpResult.LatencyMs)
	}

	// TCP dial probe against the peer's main listener port.
	tcpResult := protocols.RunTCPTest(fmt.Sprintf("%s:8443", target), timeout)
	if tcpResult.Success {
		fabricLatency.WithLabelValues(m.config.SourceID, target, "tcp").Observe(tcpResult.LatencyMs)
	}

	// ICMP ping sequence — requires CAP_NET_RAW in the container.
	icmpResult := protocols.RunICMPTest(target, 5, timeout)
	if icmpResult.Success {
		fabricLatency.WithLabelValues(m.config.SourceID, target, "icmp").Observe(icmpResult.LatencyMs)
		fabricJitter.WithLabelValues(m.config.SourceID, target, "icmp").Set(icmpResult.JitterMs)
		fabricPacketLoss.WithLabelValues(m.config.SourceID, target, "icmp").Set(icmpResult.PacketLoss)
	}

	m.submitMetrics(target, httpResult, tcpResult, icmpResult)
}

// submitMetrics ships a batch of successful probe results to hub-api.
func (m *FabricMonitor) submitMetrics(
	target string,
	httpRes protocols.HTTPTestResult,
	tcpRes protocols.TCPTestResult,
	icmpRes protocols.ICMPTestResult,
) {
	if m.config.HubAPIURL == "" {
		return
	}

	var metrics []map[string]interface{}

	if httpRes.Success {
		metrics = append(metrics, map[string]interface{}{
			"source_id":   m.config.SourceID,
			"source_type": "hub-router",
			"target_id":   target,
			"protocol":    "http",
			"latency_ms":  httpRes.LatencyMs,
		})
	}

	if tcpRes.Success {
		metrics = append(metrics, map[string]interface{}{
			"source_id":   m.config.SourceID,
			"source_type": "hub-router",
			"target_id":   target,
			"protocol":    "tcp",
			"latency_ms":  tcpRes.LatencyMs,
		})
	}

	if icmpRes.Success {
		metrics = append(metrics, map[string]interface{}{
			"source_id":       m.config.SourceID,
			"source_type":     "hub-router",
			"target_id":       target,
			"protocol":        "icmp",
			"latency_ms":      icmpRes.LatencyMs,
			"jitter_ms":       icmpRes.JitterMs,
			"packet_loss_pct": icmpRes.PacketLoss,
		})
	}

	if len(metrics) == 0 {
		return
	}

	body, err := json.Marshal(map[string]interface{}{"metrics": metrics})
	if err != nil {
		log.WithError(err).Warn("Failed to marshal perf metrics")
		return
	}

	url := m.config.HubAPIURL + "/api/v1/perf/metrics"
	resp, err := m.httpClient.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		log.WithError(err).Warn("Failed to submit perf metrics to hub-api")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.WithField("status", resp.StatusCode).Warn("Perf metrics submission returned non-200")
	}
}
