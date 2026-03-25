// Package dns provides Squawk DNS integration for the Tobogganing native client.
//
// When enabled, the module configures the system's DNS resolver to point to a
// local listener that forwards queries to the hub-router's Squawk DNS-over-HTTPS
// endpoint.  On disconnect the original system DNS configuration is restored.
package dns

// Config holds DNS module settings for the native client.
type Config struct {
	// Enabled controls whether the DNS module is active.
	Enabled bool `mapstructure:"enabled"`

	// ListenAddr is the local address the DNS stub listener binds to.
	// Typical value: "127.0.0.1:53".
	ListenAddr string `mapstructure:"listen_addr"`

	// UpstreamAddr is the address of the hub-router DNS forwarder inside the
	// WireGuard tunnel.  Queries received by the stub listener are forwarded
	// here.  Typical value: "10.200.0.1:5353".
	UpstreamAddr string `mapstructure:"upstream_addr"`
}

// DefaultConfig returns a Config with safe defaults.
// DNS forwarding is disabled by default.
func DefaultConfig() Config {
	return Config{
		Enabled:      false,
		ListenAddr:   "127.0.0.1:53",
		UpstreamAddr: "10.200.0.1:5353",
	}
}
