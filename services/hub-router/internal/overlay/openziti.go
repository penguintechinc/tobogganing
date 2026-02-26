//go:build openziti

package overlay

import (
	"context"
	"fmt"
	"sync"

	log "github.com/sirupsen/logrus"
)

// OpenZitiProvider implements OverlayProvider using the OpenZiti SDK.
// This file is only compiled when the "openziti" build tag is set, keeping the
// default hub-router binary free of the OpenZiti SDK dependency.
//
// Production wiring (marked with TODO comments below) requires:
//   - github.com/openziti/sdk-golang as a module dependency
//   - An enrolled identity file produced by the OpenZiti enroller
//   - A running OpenZiti controller reachable at config.ControllerURL
type OpenZitiProvider struct {
	config  OpenZitiConfig
	running bool
	mu      sync.RWMutex
	metrics OverlayMetrics

	// TODO(openziti): store *ziti.Context here once the SDK is wired in.
	// zitiCtx *ziti.Context
}

// NewOpenZitiProvider constructs an OpenZitiProvider from the given config.
func NewOpenZitiProvider(cfg OpenZitiConfig) *OpenZitiProvider {
	return &OpenZitiProvider{
		config: cfg,
	}
}

// Name implements OverlayProvider.
func (z *OpenZitiProvider) Name() string {
	return "openziti"
}

// Initialize implements OverlayProvider.  It validates required configuration
// fields and loads the OpenZiti identity.
//
// Production steps (not yet wired):
//  1. Load identity from z.config.IdentityFile via ziti.LoadIdentityFromFile
//  2. Authenticate against z.config.ControllerURL
//  3. Store the resulting *ziti.Context for use in Connect / HandlePacket
func (z *OpenZitiProvider) Initialize(ctx context.Context) error {
	log.WithFields(log.Fields{
		"controller": z.config.ControllerURL,
		"identity":   z.config.IdentityFile,
		"service":    z.config.ServiceName,
	}).Info("overlay: initializing OpenZiti provider")

	if z.config.ControllerURL == "" {
		return fmt.Errorf("overlay: openziti controller_url is required")
	}
	if z.config.IdentityFile == "" {
		return fmt.Errorf("overlay: openziti identity_file is required")
	}

	// TODO(openziti): wire SDK initialisation.
	// zitiCtx, err := ziti.NewContext(z.config.IdentityFile)
	// if err != nil {
	//     return fmt.Errorf("overlay: failed to create OpenZiti context: %w", err)
	// }
	// z.zitiCtx = zitiCtx

	log.Info("overlay: OpenZiti provider initialized")
	return nil
}

// Connect implements OverlayProvider.  It establishes the OpenZiti tunnel and
// registers the configured service.
//
// Production steps (not yet wired):
//  1. Authenticate the stored *ziti.Context against the controller
//  2. Bind or dial z.config.ServiceName to expose / access the service
func (z *OpenZitiProvider) Connect(ctx context.Context) error {
	z.mu.Lock()
	defer z.mu.Unlock()

	// TODO(openziti): authenticate and bind/dial the service.
	z.running = true
	log.Info("overlay: OpenZiti provider connected")
	return nil
}

// Disconnect implements OverlayProvider.
func (z *OpenZitiProvider) Disconnect() error {
	z.mu.Lock()
	defer z.mu.Unlock()

	// TODO(openziti): close any open listeners / dialers.
	z.running = false
	log.Info("overlay: OpenZiti provider disconnected")
	return nil
}

// HandlePacket implements OverlayProvider.  In production this routes the
// packet through the OpenZiti fabric; currently it only accounts bytes.
func (z *OpenZitiProvider) HandlePacket(data []byte, direction string) ([]byte, error) {
	z.mu.Lock()
	if direction == "send" {
		z.metrics.BytesSent += int64(len(data))
	} else {
		z.metrics.BytesReceived += int64(len(data))
	}
	z.mu.Unlock()

	// TODO(openziti): route through the OpenZiti fabric.
	return data, nil
}

// Metrics implements OverlayProvider.
func (z *OpenZitiProvider) Metrics() OverlayMetrics {
	z.mu.RLock()
	defer z.mu.RUnlock()
	return z.metrics
}

// Close implements OverlayProvider.
func (z *OpenZitiProvider) Close() error {
	return z.Disconnect()
}
