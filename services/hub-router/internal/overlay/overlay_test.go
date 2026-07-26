package overlay

import (
	"context"
	"net"
	"testing"
)

// mockProvider is a test implementation of the Provider interface
type mockProvider struct {
	name             string
	initializeErr    error
	connectErr       error
	disconnectErr    error
	listener         net.Listener
	initializeCalled bool
	connectCalled    bool
	disconnectCalled bool
}

func (m *mockProvider) Name() string { return m.name }

func (m *mockProvider) Initialize(ctx context.Context) error {
	m.initializeCalled = true
	return m.initializeErr
}

func (m *mockProvider) Connect(ctx context.Context) error {
	m.connectCalled = true
	return m.connectErr
}

func (m *mockProvider) Disconnect(ctx context.Context) error {
	m.disconnectCalled = true
	return m.disconnectErr
}

func (m *mockProvider) Listener() net.Listener {
	return m.listener
}

func TestNewManager(t *testing.T) {
	m := NewManager()
	if m == nil {
		t.Fatal("NewManager() returned nil")
	}
	if m.providers == nil {
		t.Fatal("NewManager() did not initialize providers map")
	}
	if len(m.providers) != 0 {
		t.Errorf("NewManager() should have empty providers: got %d, want 0", len(m.providers))
	}
	if m.primary != "" {
		t.Errorf("NewManager() should have empty primary: got %s, want empty", m.primary)
	}
}

func TestRegisterProvider(t *testing.T) {
	m := NewManager()
	provider := &mockProvider{name: "test"}

	m.RegisterProvider(provider)
	if len(m.providers) != 1 {
		t.Errorf("RegisterProvider() should have 1 provider: got %d", len(m.providers))
	}
	if _, ok := m.providers["test"]; !ok {
		t.Error("RegisterProvider() did not register provider by name")
	}
}

func TestRegisterMultipleProviders(t *testing.T) {
	m := NewManager()
	provider1 := &mockProvider{name: "wireguard"}
	provider2 := &mockProvider{name: "openziti"}
	provider3 := &mockProvider{name: "vxlan"}

	m.RegisterProvider(provider1)
	m.RegisterProvider(provider2)
	m.RegisterProvider(provider3)

	if len(m.providers) != 3 {
		t.Errorf("RegisterProvider() should have 3 providers: got %d", len(m.providers))
	}

	if m.providers["wireguard"] != provider1 {
		t.Error("wireguard provider not registered correctly")
	}
	if m.providers["openziti"] != provider2 {
		t.Error("openziti provider not registered correctly")
	}
	if m.providers["vxlan"] != provider3 {
		t.Error("vxlan provider not registered correctly")
	}
}

func TestRegisterProviderOverride(t *testing.T) {
	m := NewManager()
	provider1 := &mockProvider{name: "test"}
	provider2 := &mockProvider{name: "test"}

	m.RegisterProvider(provider1)
	m.RegisterProvider(provider2)

	if len(m.providers) != 1 {
		t.Errorf("RegisterProvider() override should still have 1 provider: got %d", len(m.providers))
	}
	if m.providers["test"] != provider2 {
		t.Error("RegisterProvider() override did not replace provider")
	}
}

func TestSetPrimary(t *testing.T) {
	m := NewManager()
	provider := &mockProvider{name: "wireguard"}

	m.RegisterProvider(provider)
	err := m.SetPrimary("wireguard")

	if err != nil {
		t.Fatalf("SetPrimary() returned error: %v", err)
	}
	if m.primary != "wireguard" {
		t.Errorf("SetPrimary() did not set primary: got %s, want wireguard", m.primary)
	}
}

func TestSetPrimaryUnknownProvider(t *testing.T) {
	m := NewManager()

	err := m.SetPrimary("nonexistent")

	if err == nil {
		t.Fatal("SetPrimary() should return error for unknown provider")
	}
	if m.primary != "" {
		t.Errorf("SetPrimary() should not change primary on error: got %s", m.primary)
	}
	expectedMsg := "overlay provider \"nonexistent\" not registered"
	if err.Error() != expectedMsg {
		t.Errorf("SetPrimary() error message: got %q, want %q", err.Error(), expectedMsg)
	}
}

func TestSetPrimarySwitch(t *testing.T) {
	m := NewManager()
	provider1 := &mockProvider{name: "wireguard"}
	provider2 := &mockProvider{name: "openziti"}

	m.RegisterProvider(provider1)
	m.RegisterProvider(provider2)

	if err := m.SetPrimary("wireguard"); err != nil {
		t.Fatalf("SetPrimary(wireguard) returned error: %v", err)
	}

	if m.primary != "wireguard" {
		t.Errorf("first SetPrimary: got %s, want wireguard", m.primary)
	}

	if err := m.SetPrimary("openziti"); err != nil {
		t.Fatalf("SetPrimary(openziti) returned error: %v", err)
	}

	if m.primary != "openziti" {
		t.Errorf("second SetPrimary: got %s, want openziti", m.primary)
	}
}

func TestCloseAll(t *testing.T) {
	m := NewManager()
	provider1 := &mockProvider{name: "provider1"}
	provider2 := &mockProvider{name: "provider2"}

	m.RegisterProvider(provider1)
	m.RegisterProvider(provider2)

	m.CloseAll()

	if !provider1.disconnectCalled {
		t.Error("CloseAll() did not call Disconnect on provider1")
	}
	if !provider2.disconnectCalled {
		t.Error("CloseAll() did not call Disconnect on provider2")
	}
}

func TestCloseAllWithErrors(t *testing.T) {
	m := NewManager()
	provider1 := &mockProvider{name: "provider1", disconnectErr: nil}
	provider2 := &mockProvider{name: "provider2", disconnectErr: nil}

	m.RegisterProvider(provider1)
	m.RegisterProvider(provider2)

	// Should not panic even if Disconnect returns errors
	m.CloseAll()

	if !provider1.disconnectCalled || !provider2.disconnectCalled {
		t.Error("CloseAll() should call Disconnect on all providers even with errors")
	}
}

func TestCloseAllEmpty(t *testing.T) {
	m := NewManager()
	// Should not panic with no providers
	m.CloseAll()
}

func TestPrimary(t *testing.T) {
	m := NewManager()

	// nil case - no primary set
	if m.Primary() != nil {
		t.Error("Primary() should return nil when no primary set")
	}

	provider := &mockProvider{name: "wireguard"}
	m.RegisterProvider(provider)

	if err := m.SetPrimary("wireguard"); err != nil {
		t.Fatalf("SetPrimary() returned error: %v", err)
	}

	primary := m.Primary()
	if primary == nil {
		t.Fatal("Primary() returned nil after SetPrimary")
	}
	if primary != provider {
		t.Error("Primary() did not return the correct provider")
	}
}

func TestPrimaryMultipleProviders(t *testing.T) {
	m := NewManager()
	provider1 := &mockProvider{name: "provider1"}
	provider2 := &mockProvider{name: "provider2"}
	provider3 := &mockProvider{name: "provider3"}

	m.RegisterProvider(provider1)
	m.RegisterProvider(provider2)
	m.RegisterProvider(provider3)

	if err := m.SetPrimary("provider2"); err != nil {
		t.Fatalf("SetPrimary() returned error: %v", err)
	}

	primary := m.Primary()
	if primary != provider2 {
		t.Error("Primary() did not return provider2")
	}
}

func TestNewWireGuardProvider(t *testing.T) {
	cfg := WireGuardConfig{
		Interface: "wg0",
		Network:   "10.0.0.0/24",
	}

	p := NewWireGuardProvider(cfg)
	if p == nil {
		t.Fatal("NewWireGuardProvider() returned nil")
	}

	provider := p.(*wireGuardProvider)
	if provider.cfg != cfg {
		t.Errorf("NewWireGuardProvider() did not store config correctly")
	}
}

func TestWireGuardProviderName(t *testing.T) {
	cfg := WireGuardConfig{}
	p := NewWireGuardProvider(cfg)

	if p.Name() != "wireguard" {
		t.Errorf("WireGuard Name(): got %s, want wireguard", p.Name())
	}
}

func TestWireGuardProviderInitialize(t *testing.T) {
	cfg := WireGuardConfig{}
	p := NewWireGuardProvider(cfg)

	err := p.Initialize(context.Background())
	if err != nil {
		t.Fatalf("WireGuard Initialize() returned error: %v", err)
	}
}

func TestWireGuardProviderConnect(t *testing.T) {
	cfg := WireGuardConfig{}
	p := NewWireGuardProvider(cfg)

	err := p.Connect(context.Background())
	if err != nil {
		t.Fatalf("WireGuard Connect() returned error: %v", err)
	}
}

func TestWireGuardProviderDisconnect(t *testing.T) {
	cfg := WireGuardConfig{}
	p := NewWireGuardProvider(cfg)

	err := p.Disconnect(context.Background())
	if err != nil {
		t.Fatalf("WireGuard Disconnect() returned error: %v", err)
	}
}

func TestWireGuardProviderListener(t *testing.T) {
	cfg := WireGuardConfig{}
	p := NewWireGuardProvider(cfg)

	listener := p.Listener()
	if listener != nil {
		t.Errorf("WireGuard Listener(): got %v, want nil", listener)
	}
}

func TestWireGuardProviderWithConfig(t *testing.T) {
	cfg := WireGuardConfig{
		Interface: "wg0",
		Network:   "192.168.1.0/24",
	}
	p := NewWireGuardProvider(cfg)

	provider := p.(*wireGuardProvider)
	if provider.cfg.Interface != "wg0" {
		t.Errorf("WireGuard config Interface: got %s, want wg0", provider.cfg.Interface)
	}
	if provider.cfg.Network != "192.168.1.0/24" {
		t.Errorf("WireGuard config Network: got %s, want 192.168.1.0/24", provider.cfg.Network)
	}
}

func TestNewOpenZitiProvider(t *testing.T) {
	cfg := OpenZitiConfig{
		IdentityFile: "/etc/ziti/identity.json",
		ServiceName:  "myservice",
	}

	p := NewOpenZitiProvider(cfg)
	if p == nil {
		t.Fatal("NewOpenZitiProvider() returned nil")
	}

	if p.cfg != cfg {
		t.Errorf("NewOpenZitiProvider() did not store config correctly")
	}
}

func TestOpenZitiProviderName(t *testing.T) {
	cfg := OpenZitiConfig{}
	p := NewOpenZitiProvider(cfg)

	if p.Name() != "openziti" {
		t.Errorf("OpenZiti Name(): got %s, want openziti", p.Name())
	}
}

func TestOpenZitiProviderInitialize(t *testing.T) {
	cfg := OpenZitiConfig{}
	p := NewOpenZitiProvider(cfg)

	err := p.Initialize(context.Background())
	if err != nil {
		t.Fatalf("OpenZiti Initialize() returned error: %v", err)
	}
}

func TestOpenZitiProviderConnect(t *testing.T) {
	cfg := OpenZitiConfig{}
	p := NewOpenZitiProvider(cfg)

	err := p.Connect(context.Background())
	if err != nil {
		t.Fatalf("OpenZiti Connect() returned error: %v", err)
	}
}

func TestOpenZitiProviderDisconnect(t *testing.T) {
	cfg := OpenZitiConfig{}
	p := NewOpenZitiProvider(cfg)

	err := p.Disconnect(context.Background())
	if err != nil {
		t.Fatalf("OpenZiti Disconnect() returned error: %v", err)
	}
}

func TestOpenZitiProviderListener(t *testing.T) {
	cfg := OpenZitiConfig{}
	p := NewOpenZitiProvider(cfg)

	listener := p.Listener()
	if listener != nil {
		t.Errorf("OpenZiti Listener(): got %v, want nil (listener not set)", listener)
	}
}

func TestOpenZitiProviderListenerAfterSet(t *testing.T) {
	cfg := OpenZitiConfig{}
	p := NewOpenZitiProvider(cfg)

	// Mock listener for testing
	mockListener := &mockListener{}
	p.listener = mockListener

	listener := p.Listener()
	if listener != mockListener {
		t.Error("OpenZiti Listener() did not return set listener")
	}
}

func TestOpenZitiProviderWithConfig(t *testing.T) {
	cfg := OpenZitiConfig{
		IdentityFile: "/path/to/identity.json",
		ServiceName:  "test-service",
	}
	p := NewOpenZitiProvider(cfg)

	if p.cfg.IdentityFile != "/path/to/identity.json" {
		t.Errorf("OpenZiti config IdentityFile: got %s", p.cfg.IdentityFile)
	}
	if p.cfg.ServiceName != "test-service" {
		t.Errorf("OpenZiti config ServiceName: got %s", p.cfg.ServiceName)
	}
}

func TestManagerWithWireGuard(t *testing.T) {
	m := NewManager()
	cfg := WireGuardConfig{
		Interface: "wg0",
		Network:   "10.0.0.0/24",
	}
	provider := NewWireGuardProvider(cfg)

	m.RegisterProvider(provider)
	if err := m.SetPrimary("wireguard"); err != nil {
		t.Fatalf("SetPrimary() returned error: %v", err)
	}

	primary := m.Primary()
	if primary.Name() != "wireguard" {
		t.Errorf("Primary provider name: got %s, want wireguard", primary.Name())
	}
}

func TestManagerWithOpenZiti(t *testing.T) {
	m := NewManager()
	cfg := OpenZitiConfig{
		IdentityFile: "/etc/ziti/identity.json",
		ServiceName:  "myservice",
	}
	provider := NewOpenZitiProvider(cfg)

	m.RegisterProvider(provider)
	if err := m.SetPrimary("openziti"); err != nil {
		t.Fatalf("SetPrimary() returned error: %v", err)
	}

	primary := m.Primary()
	if primary.Name() != "openziti" {
		t.Errorf("Primary provider name: got %s, want openziti", primary.Name())
	}
}

func TestManagerWithMixedProviders(t *testing.T) {
	m := NewManager()
	wg := NewWireGuardProvider(WireGuardConfig{})
	oz := NewOpenZitiProvider(OpenZitiConfig{})

	m.RegisterProvider(wg)
	m.RegisterProvider(oz)

	if len(m.providers) != 2 {
		t.Errorf("Manager should have 2 providers: got %d", len(m.providers))
	}

	if err := m.SetPrimary("wireguard"); err != nil {
		t.Fatalf("SetPrimary(wireguard) returned error: %v", err)
	}

	if m.Primary().Name() != "wireguard" {
		t.Error("Primary should be wireguard")
	}

	if err := m.SetPrimary("openziti"); err != nil {
		t.Fatalf("SetPrimary(openziti) returned error: %v", err)
	}

	if m.Primary().Name() != "openziti" {
		t.Error("Primary should be openziti")
	}
}

func TestProviderInterface(t *testing.T) {
	// Ensure WireGuard and OpenZiti implement Provider interface
	var _ Provider = NewWireGuardProvider(WireGuardConfig{})
	var _ Provider = NewOpenZitiProvider(OpenZitiConfig{})
}

// mockListener is a minimal mock of net.Listener for testing
type mockListener struct{}

func (m *mockListener) Accept() (net.Conn, error) {
	return nil, nil
}

func (m *mockListener) Close() error {
	return nil
}

func (m *mockListener) Addr() net.Addr {
	return nil
}
