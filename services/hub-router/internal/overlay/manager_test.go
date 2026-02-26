package overlay

import (
	"context"
	"errors"
	"testing"
)

// ---------------------------------------------------------------------------
// stub provider — implements OverlayProvider for testing
// ---------------------------------------------------------------------------

type stubProvider struct {
	name           string
	initErr        error
	connectErr     error
	disconnectErr  error
	closeErr       error
	initCalled     bool
	connectCalled  bool
	closeCalled    bool
	metrics        OverlayMetrics
}

func newStub(name string) *stubProvider {
	return &stubProvider{name: name}
}

func (s *stubProvider) Name() string { return s.name }

func (s *stubProvider) Initialize(_ context.Context) error {
	s.initCalled = true
	return s.initErr
}

func (s *stubProvider) Connect(_ context.Context) error {
	s.connectCalled = true
	return s.connectErr
}

func (s *stubProvider) Disconnect() error {
	return s.disconnectErr
}

func (s *stubProvider) HandlePacket(data []byte, _ string) ([]byte, error) {
	return data, nil
}

func (s *stubProvider) Metrics() OverlayMetrics {
	return s.metrics
}

func (s *stubProvider) Close() error {
	s.closeCalled = true
	return s.closeErr
}

// ---------------------------------------------------------------------------
// NewOverlayManager
// ---------------------------------------------------------------------------

func TestNewManager_CreatesValidManager(t *testing.T) {
	m := NewOverlayManager("wireguard")
	if m == nil {
		t.Fatal("NewOverlayManager returned nil")
	}
	if m.primary != "wireguard" {
		t.Errorf("expected primary=%q, got %q", "wireguard", m.primary)
	}
	if m.providers == nil {
		t.Error("providers map should be initialised, got nil")
	}
}

// ---------------------------------------------------------------------------
// RegisterProvider
// ---------------------------------------------------------------------------

func TestRegisterProvider_AddsProvider(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	m.RegisterProvider(wg)

	m.mu.RLock()
	_, ok := m.providers["wireguard"]
	m.mu.RUnlock()

	if !ok {
		t.Error("expected provider 'wireguard' to be registered after RegisterProvider")
	}
}

func TestRegisterProvider_ReplacesExisting(t *testing.T) {
	m := NewOverlayManager("wireguard")
	first := newStub("wireguard")
	second := newStub("wireguard")
	m.RegisterProvider(first)
	m.RegisterProvider(second)

	m.mu.RLock()
	got := m.providers["wireguard"]
	m.mu.RUnlock()

	if got != second {
		t.Error("registering a second provider with the same name should replace the first")
	}
}

// ---------------------------------------------------------------------------
// GetProvider
// ---------------------------------------------------------------------------

func TestGetProvider_WireGuardScope_ReturnsWireGuard(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	m.RegisterProvider(wg)

	p, err := m.GetProvider("wireguard")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p != wg {
		t.Error("GetProvider('wireguard') should return the registered WireGuard provider")
	}
}

func TestGetProvider_K8sScope_ReturnsPrimary(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	m.RegisterProvider(wg)

	p, err := m.GetProvider("k8s")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p != wg {
		t.Errorf("GetProvider('k8s') should return primary provider, got %T", p)
	}
}

func TestGetProvider_BothScope_ReturnsPrimary(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	m.RegisterProvider(wg)

	p, err := m.GetProvider("both")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p != wg {
		t.Errorf("GetProvider('both') should return primary provider, got %T", p)
	}
}

func TestGetProvider_UnknownScope_ReturnsPrimary(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	m.RegisterProvider(wg)

	p, err := m.GetProvider("unknown-overlay")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p != wg {
		t.Errorf("GetProvider with unknown scope should return primary, got %T", p)
	}
}

func TestGetProvider_EmptyScope_ReturnsPrimary(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	m.RegisterProvider(wg)

	p, err := m.GetProvider("")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p != wg {
		t.Errorf("GetProvider('') should return primary provider, got %T", p)
	}
}

func TestGetProvider_OpenZiti_FallbackToPrimaryWhenNotRegistered(t *testing.T) {
	// "openziti" scope requested but only wireguard is registered → primary fallback.
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	m.RegisterProvider(wg)

	p, err := m.GetProvider("openziti")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p != wg {
		t.Errorf("GetProvider('openziti') without openziti registered should fall back to primary, got %T", p)
	}
}

func TestGetProvider_OpenZiti_ReturnsOpenZitiWhenRegistered(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	oz := newStub("openziti")
	m.RegisterProvider(wg)
	m.RegisterProvider(oz)

	p, err := m.GetProvider("openziti")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if p != oz {
		t.Error("GetProvider('openziti') should return openziti provider when registered")
	}
}

func TestGetProvider_NoPrimaryRegistered_ReturnsError(t *testing.T) {
	m := NewOverlayManager("wireguard")
	// No providers registered at all.

	_, err := m.GetProvider("k8s")
	if err == nil {
		t.Error("expected error when primary provider is not registered, got nil")
	}
}

// ---------------------------------------------------------------------------
// Initialize
// ---------------------------------------------------------------------------

func TestInitialize_CallsAllProviders(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	oz := newStub("openziti")
	m.RegisterProvider(wg)
	m.RegisterProvider(oz)

	if err := m.Initialize(context.Background()); err != nil {
		t.Fatalf("Initialize returned unexpected error: %v", err)
	}
	if !wg.initCalled {
		t.Error("expected Initialize to be called on wireguard provider")
	}
	if !oz.initCalled {
		t.Error("expected Initialize to be called on openziti provider")
	}
}

func TestInitialize_StopsOnFirstError(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	wg.initErr = errors.New("init failed")
	m.RegisterProvider(wg)

	err := m.Initialize(context.Background())
	if err == nil {
		t.Error("expected Initialize to propagate provider error, got nil")
	}
}

func TestInitialize_NoProviders_ReturnsNil(t *testing.T) {
	m := NewOverlayManager("wireguard")
	if err := m.Initialize(context.Background()); err != nil {
		t.Errorf("Initialize with no providers should return nil, got %v", err)
	}
}

// ---------------------------------------------------------------------------
// Close
// ---------------------------------------------------------------------------

func TestClose_CallsAllProviders(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	oz := newStub("openziti")
	m.RegisterProvider(wg)
	m.RegisterProvider(oz)

	if err := m.Close(); err != nil {
		t.Fatalf("Close returned unexpected error: %v", err)
	}
	if !wg.closeCalled {
		t.Error("expected Close to be called on wireguard provider")
	}
	if !oz.closeCalled {
		t.Error("expected Close to be called on openziti provider")
	}
}

func TestClose_ReturnsFirstError(t *testing.T) {
	m := NewOverlayManager("wireguard")
	bad := newStub("wireguard")
	bad.closeErr = errors.New("close failed")
	m.RegisterProvider(bad)

	err := m.Close()
	if err == nil {
		t.Error("expected Close to return provider error, got nil")
	}
}

func TestClose_ContinuesAfterError(t *testing.T) {
	// Even when one provider fails to close, the others should still be closed.
	m := NewOverlayManager("bad")
	bad := newStub("bad")
	bad.closeErr = errors.New("close failed")
	good := newStub("good")
	m.RegisterProvider(bad)
	m.RegisterProvider(good)

	// We expect an error (from bad) but good should still be closed.
	_ = m.Close()
	if !good.closeCalled {
		t.Error("Close should attempt all providers even if one fails")
	}
}

func TestClose_NoProviders_ReturnsNil(t *testing.T) {
	m := NewOverlayManager("wireguard")
	if err := m.Close(); err != nil {
		t.Errorf("Close with no providers should return nil, got %v", err)
	}
}

// ---------------------------------------------------------------------------
// AllMetrics
// ---------------------------------------------------------------------------

func TestAllMetrics_AggregatesMetrics(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	wg.metrics = OverlayMetrics{BytesSent: 100, BytesReceived: 200, ActivePeers: 3, LatencyMS: 1.5}
	oz := newStub("openziti")
	oz.metrics = OverlayMetrics{BytesSent: 50, BytesReceived: 75, ActivePeers: 1, LatencyMS: 2.0}
	m.RegisterProvider(wg)
	m.RegisterProvider(oz)

	metrics := m.AllMetrics()
	if len(metrics) != 2 {
		t.Fatalf("expected 2 metric entries, got %d", len(metrics))
	}

	wgM, ok := metrics["wireguard"]
	if !ok {
		t.Fatal("expected 'wireguard' key in AllMetrics result")
	}
	if wgM.BytesSent != 100 || wgM.BytesReceived != 200 {
		t.Errorf("wireguard metrics mismatch: got %+v", wgM)
	}

	ozM, ok := metrics["openziti"]
	if !ok {
		t.Fatal("expected 'openziti' key in AllMetrics result")
	}
	if ozM.BytesSent != 50 || ozM.BytesReceived != 75 {
		t.Errorf("openziti metrics mismatch: got %+v", ozM)
	}
}

func TestAllMetrics_EmptyManager_ReturnsEmptyMap(t *testing.T) {
	m := NewOverlayManager("wireguard")
	metrics := m.AllMetrics()
	if len(metrics) != 0 {
		t.Errorf("expected empty metrics map, got %d entries", len(metrics))
	}
}

func TestAllMetrics_SingleProvider_ReturnsOneEntry(t *testing.T) {
	m := NewOverlayManager("wireguard")
	wg := newStub("wireguard")
	wg.metrics = OverlayMetrics{ActivePeers: 7}
	m.RegisterProvider(wg)

	metrics := m.AllMetrics()
	if len(metrics) != 1 {
		t.Fatalf("expected 1 metric entry, got %d", len(metrics))
	}
	if metrics["wireguard"].ActivePeers != 7 {
		t.Errorf("expected ActivePeers=7, got %d", metrics["wireguard"].ActivePeers)
	}
}
