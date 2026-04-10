package overlay

import (
	"context"
	"fmt"
	"net"
	"sync"

	"github.com/openziti/sdk-golang/ziti"
	"github.com/openziti/sdk-golang/ziti/edge"
)

// ZitiContext is the subset of ziti.Context used by openZitiProvider.
// Extracting it as an interface enables dependency injection and testing without
// a live OpenZiti control plane.
type ZitiContext interface {
	// Authenticate performs zero-trust authentication against the controller.
	Authenticate() error
	// Dial opens a connection to the named OpenZiti service.
	// The concrete ziti.Context returns edge.Conn which satisfies net.Conn.
	Dial(serviceName string) (net.Conn, error)
	// Close releases all resources held by the context.
	Close()
}

// ZitiContextFactory creates a ZitiContext from an identity file path.
// The default implementation calls ziti.NewContextFromFile.
type ZitiContextFactory func(identityFile string) (ZitiContext, error)

// innerZitiContext is the minimal subset of ziti.Context that zitiContextAdapter
// delegates to. Keeping it narrow allows test code to provide a simple stub
// without implementing the full ziti.Context interface.
type innerZitiContext interface {
	Authenticate() error
	Dial(serviceName string) (edge.Conn, error)
	Close()
}

// zitiContextAdapter wraps an innerZitiContext and adapts its Dial method to
// return net.Conn instead of edge.Conn (edge.Conn satisfies net.Conn).
type zitiContextAdapter struct {
	inner innerZitiContext
}

func (a *zitiContextAdapter) Authenticate() error { return a.inner.Authenticate() }
func (a *zitiContextAdapter) Dial(serviceName string) (net.Conn, error) {
	return a.inner.Dial(serviceName)
}
func (a *zitiContextAdapter) Close() { a.inner.Close() }

// defaultZitiFactory wraps ziti.NewContextFromFile and adapts the concrete
// ziti.Context to the ZitiContext interface.
func defaultZitiFactory(identityFile string) (ZitiContext, error) {
	ctx, err := ziti.NewContextFromFile(identityFile)
	if err != nil {
		return nil, err
	}
	return &zitiContextAdapter{inner: ctx}, nil
}

// OpenZitiProvider extends OverlayProvider with OpenZiti-specific operations.
type OpenZitiProvider interface {
	OverlayProvider
	// SetJWTToken supplies the authentication token used during Authenticate.
	SetJWTToken(token string)
}

type openZitiProvider struct {
	cfg     OpenZitiConfig
	factory ZitiContextFactory
	mu      sync.Mutex
	// jwtToken is stored for future use (e.g. re-authentication flows).
	jwtToken string
	zitiCtx  ZitiContext
	conn     net.Conn
}

// NewOpenZitiProvider creates an OpenZitiProvider backed by OpenZiti zero-trust
// networking using the default ziti SDK factory.
func NewOpenZitiProvider(cfg OpenZitiConfig) OpenZitiProvider {
	return NewOpenZitiProviderWithFactory(cfg, defaultZitiFactory)
}

// NewOpenZitiProviderWithFactory creates an OpenZitiProvider with an injectable
// ZitiContextFactory. Use this constructor in tests to supply mock contexts.
func NewOpenZitiProviderWithFactory(cfg OpenZitiConfig, factory ZitiContextFactory) OpenZitiProvider {
	return &openZitiProvider{cfg: cfg, factory: factory}
}

func (o *openZitiProvider) SetJWTToken(token string) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.jwtToken = token
}

func (o *openZitiProvider) Connect(_ context.Context) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	if o.zitiCtx != nil {
		return nil // already connected
	}

	zitiCtx, err := o.factory(o.cfg.IdentityFile)
	if err != nil {
		return fmt.Errorf("load openziti identity %q: %w", o.cfg.IdentityFile, err)
	}

	if err := zitiCtx.Authenticate(); err != nil {
		return fmt.Errorf("openziti authenticate: %w", err)
	}

	conn, err := zitiCtx.Dial(o.cfg.ServiceName)
	if err != nil {
		return fmt.Errorf("openziti dial service %q: %w", o.cfg.ServiceName, err)
	}

	o.zitiCtx = zitiCtx
	o.conn = conn
	return nil
}

func (o *openZitiProvider) Disconnect(_ context.Context) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	var firstErr error
	if o.conn != nil {
		if err := o.conn.Close(); err != nil {
			firstErr = fmt.Errorf("close connection: %w", err)
		}
		o.conn = nil
	}
	if o.zitiCtx != nil {
		o.zitiCtx.Close()
		o.zitiCtx = nil
	}
	return firstErr
}

func (o *openZitiProvider) Status(_ context.Context) (ProviderStatus, error) {
	o.mu.Lock()
	defer o.mu.Unlock()

	connected := o.zitiCtx != nil && o.conn != nil
	status := ProviderStatus{Connected: connected}
	if connected {
		if addr := o.conn.RemoteAddr(); addr != nil {
			status.Endpoint = addr.String()
		}
	}
	return status, nil
}
