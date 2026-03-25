//go:build !xdp

package xdp

import (
	"net"
)

// XDPProtection is a no-op stub when built without the xdp tag.
// All methods are safe to call and do nothing.
type XDPProtection struct{}

// New creates a no-op XDP protection instance.
func New(_ XDPConfig) *XDPProtection {
	return &XDPProtection{}
}

// Attach is a no-op without XDP build tag.
func (x *XDPProtection) Attach(_ string) error { return nil }

// SetRateLimit is a no-op without XDP build tag.
func (x *XDPProtection) SetRateLimit(_ int) {}

// SetSYNRateLimit is a no-op without XDP build tag.
func (x *XDPProtection) SetSYNRateLimit(_ int) {}

// SetUDPRateLimit is a no-op without XDP build tag.
func (x *XDPProtection) SetUDPRateLimit(_ int) {}

// BlockIP is a no-op without XDP build tag.
func (x *XDPProtection) BlockIP(_ net.IP) {}

// UnblockIP is a no-op without XDP build tag.
func (x *XDPProtection) UnblockIP(_ net.IP) {}

// Stats returns zero stats without XDP build tag.
func (x *XDPProtection) Stats() XDPStats { return XDPStats{} }

// BlocklistSize returns 0 without XDP build tag.
func (x *XDPProtection) BlocklistSize() int { return 0 }

// Close is a no-op without XDP build tag.
func (x *XDPProtection) Close() {}
