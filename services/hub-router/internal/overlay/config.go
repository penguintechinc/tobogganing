// Package overlay defines configuration and provider abstractions for network
// overlay implementations used by the hub-router.  Two providers are supported:
// WireGuard (default, always compiled in) and OpenZiti (build-tag gated via
// the "openziti" tag to avoid bloating the default binary).
package overlay

// Config is the top-level overlay configuration block, loaded via viper with
// the "overlay" prefix.
type Config struct {
	// Type selects the active overlay provider: "wireguard" (default) or "openziti".
	Type      string          `mapstructure:"type"`
	WireGuard WireGuardConfig `mapstructure:"wireguard"`
	OpenZiti  OpenZitiConfig  `mapstructure:"openziti"`
}

// WireGuardConfig holds parameters for the WireGuard overlay provider.
type WireGuardConfig struct {
	// Interface is the kernel network interface name (e.g. "wg0").
	Interface string `mapstructure:"interface"`
	// ListenPort is the UDP port WireGuard listens on.
	ListenPort int `mapstructure:"listen_port"`
	// PrivateKey is the base64-encoded WireGuard private key.  When empty the
	// existing WireGuard manager generates or loads a key from disk.
	PrivateKey string `mapstructure:"private_key"`
	// Address is the CIDR address assigned to the WireGuard interface.
	Address string `mapstructure:"address"`
}

// OpenZitiConfig holds parameters for the OpenZiti overlay provider.
// These fields are only meaningful when the "openziti" build tag is set.
type OpenZitiConfig struct {
	// ControllerURL is the URL of the OpenZiti controller (e.g. "https://ctrl.example.com:8441").
	ControllerURL string `mapstructure:"controller_url"`
	// IdentityFile is the path to the OpenZiti identity JSON file.
	IdentityFile string `mapstructure:"identity_file"`
	// ServiceName is the OpenZiti service the headend should bind or dial.
	ServiceName string `mapstructure:"service_name"`
}

// DefaultConfig returns a Config pre-populated with production-ready defaults.
// WireGuard is the default overlay type; OpenZiti fields are intentionally
// left empty so that misconfiguration is caught at initialisation time.
func DefaultConfig() Config {
	return Config{
		Type: "wireguard",
		WireGuard: WireGuardConfig{
			Interface:  "wg0",
			ListenPort: 51820,
		},
	}
}
