// Package overlay provides pluggable overlay network abstractions for the
// Tobogganing native client. It supports WireGuard (L3), OpenZiti (L7),
// and dual-mode (both simultaneously) selected at runtime via configuration.
package overlay

import (
	"context"
	"net"
)

// OverlayProvider defines the interface for client-side overlay implementations.
//
// The key method is Dial: for WireGuard it returns (nil, nil) because traffic
// routes through the kernel tunnel transparently. For OpenZiti it returns a
// net.Conn from ziti.Context.Dial() with the JWT+HOST handshake already sent.
type OverlayProvider interface {
	// Name returns the overlay type name (e.g., "wireguard", "openziti", "dual").
	Name() string

	// Connect establishes the overlay connection.
	Connect(ctx context.Context) error

	// Disconnect tears down the overlay connection.
	Disconnect() error

	// IsConnected returns whether the overlay is currently connected.
	IsConnected() bool

	// Dial creates a connection to the specified service through the overlay.
	// For WireGuard: returns (nil, nil) — traffic uses the kernel tunnel.
	// For OpenZiti: returns a net.Conn via ziti.Context.Dial() with handshake.
	Dial(ctx context.Context, service string) (net.Conn, error)
}
