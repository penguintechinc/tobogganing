// Package xdp provides XDP/eBPF edge protection for the Tobogganing hub-router.
//
// When built with -tags xdp, the package provides kernel-level packet filtering
// via XDP programs attached to the NIC. Without the tag, all operations are
// safe no-ops (stubs) that compile without BPF dependencies.
package xdp

// XDPConfig holds configuration for XDP edge protection.
type XDPConfig struct {
	// Enabled controls whether XDP protection is active.
	Enabled bool `mapstructure:"enabled"`

	// Interface is the network interface to attach XDP programs to.
	Interface string `mapstructure:"interface"`

	// RateLimitPPS is the general per-source-IP packet rate limit.
	RateLimitPPS int `mapstructure:"rate_limit_pps"`

	// SYNRateLimitPPS is the per-source-IP SYN packet rate limit.
	SYNRateLimitPPS int `mapstructure:"syn_rate_limit_pps"`

	// UDPRateLimitPPS is the per-source-IP UDP packet rate limit.
	UDPRateLimitPPS int `mapstructure:"udp_rate_limit_pps"`

	// BlocklistSyncURL is the hub-api endpoint for IP blocklist sync.
	BlocklistSyncURL string `mapstructure:"blocklist_sync_url"`
}

// XDPStats holds XDP packet processing statistics.
type XDPStats struct {
	// PacketsProcessed is the total number of packets that passed all checks.
	PacketsProcessed uint64

	// PacketsDropped is the total number of packets dropped by blocklist.
	PacketsDropped uint64

	// PacketsRateLimited is the total number of packets dropped by general rate limiting.
	PacketsRateLimited uint64

	// SYNFloodDropped is the total number of SYN packets dropped by flood protection.
	SYNFloodDropped uint64

	// UDPFloodDropped is the total number of UDP packets dropped by flood protection.
	UDPFloodDropped uint64
}
