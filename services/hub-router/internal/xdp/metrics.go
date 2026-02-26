package xdp

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	xdpPacketsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "tobogganing_xdp_packets_total",
			Help: "Total packets processed by XDP program",
		},
		[]string{"action"},
	)

	xdpSYNFloodDropsTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "tobogganing_xdp_syn_flood_drops_total",
			Help: "Total SYN flood packets dropped by XDP",
		},
	)

	xdpUDPFloodDropsTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "tobogganing_xdp_udp_flood_drops_total",
			Help: "Total UDP flood packets dropped by XDP",
		},
	)

	xdpBlocklistSize = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "tobogganing_xdp_blocklist_size",
			Help: "Current number of IPs in the XDP blocklist",
		},
	)
)

// UpdateMetrics updates Prometheus metrics from XDP stats.
func UpdateMetrics(stats XDPStats) {
	xdpPacketsTotal.WithLabelValues("pass").Add(float64(stats.PacketsProcessed))
	xdpPacketsTotal.WithLabelValues("drop").Add(float64(stats.PacketsDropped))
	xdpPacketsTotal.WithLabelValues("ratelimit").Add(float64(stats.PacketsRateLimited))
	xdpSYNFloodDropsTotal.Add(float64(stats.SYNFloodDropped))
	xdpUDPFloodDropsTotal.Add(float64(stats.UDPFloodDropped))
}

// SetBlocklistSize updates the blocklist size gauge.
func SetBlocklistSize(size int) {
	xdpBlocklistSize.Set(float64(size))
}
