package overlay

import (
	"context"
	"fmt"
	"net"
	"sync"

	"github.com/openziti/sdk-golang/ziti"
)

// OpenZitiProvider extends OverlayProvider with OpenZiti-specific operations.
type OpenZitiProvider interface {
	OverlayProvider
	// SetJWTToken supplies the authentication token used during Authenticate.
	SetJWTToken(token string)
}

type openZitiProvider struct {
	cfg      OpenZitiConfig
	mu       sync.Mutex
	jwtToken string
	ctx      ziti.Context
	conn     net.Conn
}

// NewOpenZitiProvider creates an OpenZitiProvider backed by OpenZiti zero-trust networking.
func NewOpenZitiProvider(cfg OpenZitiConfig) OpenZitiProvider {
	return &openZitiProvider{cfg: cfg}
}

func (o *openZitiProvider) SetJWTToken(token string) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.jwtToken = token
}

func (o *openZitiProvider) Connect(_ context.Context) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	if o.ctx != nil {
		return nil // already connected
	}

	zitiCtx, err := ziti.NewContextFromFile(o.cfg.IdentityFile)
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

	o.ctx = zitiCtx
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
	if o.ctx != nil {
		o.ctx.Close()
		o.ctx = nil
	}
	return firstErr
}

func (o *openZitiProvider) Status(_ context.Context) (ProviderStatus, error) {
	o.mu.Lock()
	defer o.mu.Unlock()

	connected := o.ctx != nil && o.conn != nil
	status := ProviderStatus{Connected: connected}
	if connected {
		if addr := o.conn.RemoteAddr(); addr != nil {
			status.Endpoint = addr.String()
		}
	}
	return status, nil
}
