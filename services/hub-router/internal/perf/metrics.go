package perf

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Prometheus metrics for WaddlePerf fabric telemetry.
var (
	fabricLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "tobogganing_fabric_latency_ms",
		Help:    "Fabric latency between nodes in milliseconds",
		Buckets: []float64{1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500},
	}, []string{"source", "target", "protocol"})

	fabricJitter = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "tobogganing_fabric_jitter_ms",
		Help: "Fabric jitter between nodes in milliseconds",
	}, []string{"source", "target", "protocol"})

	fabricPacketLoss = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "tobogganing_fabric_packet_loss_pct",
		Help: "Fabric packet loss percentage between nodes",
	}, []string{"source", "target", "protocol"})

	fabricThroughput = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "tobogganing_fabric_throughput_mbps",
		Help: "Fabric throughput between nodes in Mbps",
	}, []string{"source", "target", "protocol"})

	proxyOverhead = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "tobogganing_proxy_overhead_ms",
		Help:    "Proxy processing overhead in milliseconds",
		Buckets: []float64{0.1, 0.5, 1, 2, 5, 10, 25},
	})
)

// ensure fabricThroughput and proxyOverhead are referenced to satisfy
// the compiler when they are not yet used in other files.
var _ = fabricThroughput
var _ = proxyOverhead
