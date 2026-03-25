package dns

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// dnsQueriesTotal counts all DNS queries processed, partitioned by record
	// type (e.g. A, AAAA, CNAME) and outcome (success, error, blocked).
	dnsQueriesTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "tobogganing_dns_queries_total",
		Help: "Total number of DNS queries processed",
	}, []string{"type", "status"})

	// dnsQueryDuration records the latency of DNS queries in seconds,
	// partitioned by record type.
	dnsQueryDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "tobogganing_dns_query_duration_seconds",
		Help:    "DNS query duration in seconds",
		Buckets: prometheus.DefBuckets,
	}, []string{"type"})

	// dnsBlockedTotal counts queries refused by the domain blocklist policy.
	dnsBlockedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "tobogganing_dns_blocked_total",
		Help: "Total number of DNS queries blocked by policy",
	})
)
