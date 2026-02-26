package overlay

import "context"

// OverlayProvider defines the interface for network overlay implementations.
// Both WireGuard and OpenZiti implement this interface, allowing the proxy
// server to use either overlay transparently.
//
// Implementations must be safe for concurrent use by multiple goroutines.
type OverlayProvider interface {
	// Name returns the canonical provider identifier (e.g. "wireguard", "openziti").
	Name() string

	// Initialize sets up the overlay provider using its configuration.  It must
	// be called exactly once before Connect.
	Initialize(ctx context.Context) error

	// Connect establishes (or re-establishes) the overlay connection.
	Connect(ctx context.Context) error

	// Disconnect tears down the overlay connection without releasing underlying
	// resources.  The provider may be re-connected via Connect after a
	// Disconnect call.
	Disconnect() error

	// HandlePacket processes a single packet through the overlay.
	// direction must be "send" or "recv".  The returned byte slice may be the
	// same backing array as data when no transformation is required.
	HandlePacket(data []byte, direction string) ([]byte, error)

	// Metrics returns a snapshot of current overlay performance metrics.
	Metrics() OverlayMetrics

	// Close disconnects and releases all resources held by the provider.
	// After Close the provider must not be used.
	Close() error
}

// OverlayMetrics contains a point-in-time snapshot of overlay performance data.
// Values are cumulative since the provider was initialised.
type OverlayMetrics struct {
	BytesSent     int64   `json:"bytes_sent"`
	BytesReceived int64   `json:"bytes_received"`
	ActivePeers   int     `json:"active_peers"`
	LatencyMS     float64 `json:"latency_ms"`
}
