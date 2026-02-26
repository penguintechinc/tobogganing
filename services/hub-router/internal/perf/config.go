// Package perf implements WaddlePerf fabric performance monitoring for the hub-router.
//
// The perf package probes peer hub-router nodes via HTTP, TCP, and ICMP,
// records latency/jitter/packet-loss metrics into Prometheus, and ships
// batched metric records to the hub-api for persistent storage and dashboarding.
package perf

// Config holds configuration for the fabric performance monitor.
type Config struct {
	Enabled   bool     `mapstructure:"enabled"`
	Interval  int      `mapstructure:"interval"`    // seconds between probe rounds
	HubAPIURL string   `mapstructure:"hub_api_url"` // base URL of hub-api service
	SourceID  string   `mapstructure:"source_id"`   // identifier of this hub-router node
	Targets   []string `mapstructure:"targets"`     // peer hub-router addresses to probe
}

// DefaultConfig returns a Config with safe, disabled defaults.
func DefaultConfig() Config {
	return Config{
		Enabled:   false,
		Interval:  300,
		HubAPIURL: "http://hub-api:8080",
	}
}
