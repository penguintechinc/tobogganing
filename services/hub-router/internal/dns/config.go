// Package dns implements Squawk DNS-over-HTTPS forwarding for the hub-router.
//
// The dns package provides:
// - DNS-over-HTTPS forwarding via the Squawk DNS proxy
// - Policy-based domain blocklist enforcement
// - Prometheus metrics for DNS query tracking
// - Graceful start/stop lifecycle management
// - Concurrent UDP and TCP listener support
package dns

// Config holds configuration for the DNS forwarder.
type Config struct {
	Enabled        bool     `mapstructure:"enabled"`
	ListenAddr     string   `mapstructure:"listen_addr"`
	SquawkServer   string   `mapstructure:"squawk_server"`
	CacheTTL       int      `mapstructure:"cache_ttl"`
	BlockedDomains []string `mapstructure:"blocked_domains"`
}

// DefaultConfig returns a Config populated with safe defaults.
// DNS forwarding is disabled by default; set Enabled = true to activate.
func DefaultConfig() Config {
	return Config{
		Enabled:      false,
		ListenAddr:   ":5353",
		SquawkServer: "https://dns.penguintech.io/dns-query",
		CacheTTL:     300,
	}
}
