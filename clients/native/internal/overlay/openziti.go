package overlay

import (
	"context"
	"fmt"
	"net"
	"sync"
	"sync/atomic"

	"github.com/openziti/sdk-golang/ziti"
	log "github.com/sirupsen/logrus"
)

// OpenZitiConfig holds client-side OpenZiti configuration.
type OpenZitiConfig struct {
	// IdentityFile is the path to the Ziti identity JSON file.
	IdentityFile string `mapstructure:"identity_file"`

	// ServiceName is the Ziti service to dial on the hub-router.
	ServiceName string `mapstructure:"service_name"`
}

// OpenZitiProvider is the client-side OpenZiti overlay provider.
// It dials the hub-router's dark service and performs the JWT+HOST handshake.
type OpenZitiProvider struct {
	cfg       OpenZitiConfig
	zitiCtx   ziti.Context
	mu        sync.Mutex
	connected atomic.Bool

	// jwtToken is the current JWT token for authentication handshake.
	jwtToken string
}

// NewOpenZitiProvider creates a new client-side OpenZiti overlay provider.
func NewOpenZitiProvider(cfg OpenZitiConfig) *OpenZitiProvider {
	return &OpenZitiProvider{cfg: cfg}
}

// SetJWTToken sets the JWT token used in the handshake when dialing.
func (o *OpenZitiProvider) SetJWTToken(token string) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.jwtToken = token
}

// Name returns "openziti".
func (o *OpenZitiProvider) Name() string {
	return "openziti"
}

// Connect loads the Ziti identity and creates the context.
func (o *OpenZitiProvider) Connect(_ context.Context) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	if o.cfg.IdentityFile == "" {
		return fmt.Errorf("openziti client: identity_file is required")
	}

	cfg, err := ziti.NewConfigFromFile(o.cfg.IdentityFile)
	if err != nil {
		return fmt.Errorf("openziti client: failed to load identity from %s: %w", o.cfg.IdentityFile, err)
	}

	zitiCtx, err := ziti.NewContext(cfg)
	if err != nil {
		return fmt.Errorf("openziti client: failed to create context: %w", err)
	}

	o.zitiCtx = zitiCtx
	o.connected.Store(true)

	log.WithField("identity_file", o.cfg.IdentityFile).Info("OpenZiti client overlay connected")
	return nil
}

// Disconnect closes the Ziti context.
func (o *OpenZitiProvider) Disconnect() error {
	o.mu.Lock()
	defer o.mu.Unlock()

	if o.zitiCtx != nil {
		o.zitiCtx.Close()
		o.zitiCtx = nil
	}

	o.connected.Store(false)
	log.Info("OpenZiti client overlay disconnected")
	return nil
}

// IsConnected returns whether the Ziti context is active.
func (o *OpenZitiProvider) IsConnected() bool {
	return o.connected.Load()
}

// Dial connects to the hub-router's dark service through the Ziti overlay.
// It performs the JWT+HOST handshake after establishing the connection:
//
//	JWT:<token>\n
//	HOST:<target>\n
//
// This matches the protocol expected by the hub-router's handleZitiConnection.
func (o *OpenZitiProvider) Dial(_ context.Context, service string) (net.Conn, error) {
	o.mu.Lock()
	zitiCtx := o.zitiCtx
	token := o.jwtToken
	o.mu.Unlock()

	if zitiCtx == nil {
		return nil, fmt.Errorf("openziti client: not connected")
	}

	conn, err := zitiCtx.Dial(o.cfg.ServiceName)
	if err != nil {
		return nil, fmt.Errorf("openziti client: failed to dial service %s: %w", o.cfg.ServiceName, err)
	}

	// Send JWT+HOST handshake
	handshake := fmt.Sprintf("JWT:%s\nHOST:%s\n", token, service)
	if _, err := conn.Write([]byte(handshake)); err != nil {
		conn.Close()
		return nil, fmt.Errorf("openziti client: handshake failed: %w", err)
	}

	log.WithFields(log.Fields{
		"service": o.cfg.ServiceName,
		"target":  service,
	}).Debug("OpenZiti connection established with handshake")

	return conn, nil
}
