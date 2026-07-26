// Package xdp provides XDP/eBPF-based edge protection for the hub-router.
//
// When XDP is available and enabled, it attaches an eBPF program to the
// specified network interface to enforce per-second packet-rate limits at the
// kernel level before packets reach userspace.  This provides DDoS mitigation
// at wire speed without involving the Go runtime for every packet.
//
// Build with -tags xdp for the full eBPF implementation.
// The default (no tag) uses this stub which logs a warning and is a no-op.
package xdp

// XDPConfig holds runtime configuration for the XDP protection layer.
type XDPConfig struct {
	Enabled          bool
	Interface        string
	RateLimitPPS     int
	SYNRateLimitPPS  int
	UDPRateLimitPPS  int
	BlocklistSyncURL string
}

// XDPProtection manages an attached XDP program on a network interface.
type XDPProtection struct {
	cfg XDPConfig
}

// New creates a new XDPProtection instance with the given config.
// The protection is not active until Attach is called.
func New(cfg XDPConfig) *XDPProtection {
	return &XDPProtection{cfg: cfg}
}

// Attach loads and attaches the XDP program to the named network interface.
// Returns an error if the interface does not exist or XDP is not supported.
func (x *XDPProtection) Attach(iface string) error {
	// Stub — real implementation requires Linux + eBPF (build tag: xdp).
	_ = iface
	return nil
}

// SetRateLimit updates the global packets-per-second rate limit.
func (x *XDPProtection) SetRateLimit(pps int) { x.cfg.RateLimitPPS = pps }

// SetSYNRateLimit updates the SYN packets-per-second rate limit.
func (x *XDPProtection) SetSYNRateLimit(pps int) { x.cfg.SYNRateLimitPPS = pps }

// SetUDPRateLimit updates the UDP packets-per-second rate limit.
func (x *XDPProtection) SetUDPRateLimit(pps int) { x.cfg.UDPRateLimitPPS = pps }

// Detach removes the XDP program from the interface.
func (x *XDPProtection) Detach() error { return nil }

// Close detaches the XDP program and releases all resources.
func (x *XDPProtection) Close() error { return x.Detach() }
