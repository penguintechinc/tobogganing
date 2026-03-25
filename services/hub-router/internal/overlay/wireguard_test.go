package overlay

import (
	"context"
	"testing"
)

// ---------------------------------------------------------------------------
// Interface compliance
// ---------------------------------------------------------------------------

// TestWireGuardProvider_ImplementsOverlayProvider is a compile-time interface
// assertion.  If WireGuardProvider no longer satisfies OverlayProvider the
// package will fail to compile, catching the regression immediately.
var _ OverlayProvider = (*WireGuardProvider)(nil)

// ---------------------------------------------------------------------------
// Name
// ---------------------------------------------------------------------------

func TestWireGuardProvider_Name(t *testing.T) {
	cfg := WireGuardConfig{Interface: "wg0", ListenPort: 51820}
	p := NewWireGuardProvider(cfg)
	if got := p.Name(); got != "wireguard" {
		t.Errorf("Name() = %q, want %q", got, "wireguard")
	}
}

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

func TestWireGuardProvider_Metrics_InitiallyZero(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	m := p.Metrics()
	if m.BytesSent != 0 || m.BytesReceived != 0 || m.ActivePeers != 0 || m.LatencyMS != 0 {
		t.Errorf("expected zero Metrics on new provider, got %+v", m)
	}
}

func TestWireGuardProvider_Metrics_ReturnsSnapshot(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	// Seed metrics by sending a packet.
	if _, err := p.HandlePacket([]byte("hello"), "send"); err != nil {
		t.Fatalf("HandlePacket error: %v", err)
	}

	m := p.Metrics()
	if m.BytesSent != 5 {
		t.Errorf("expected BytesSent=5, got %d", m.BytesSent)
	}
	if m.BytesReceived != 0 {
		t.Errorf("expected BytesReceived=0, got %d", m.BytesReceived)
	}
}

// ---------------------------------------------------------------------------
// Initialize
// ---------------------------------------------------------------------------

func TestWireGuardProvider_Initialize_ReturnsNil(t *testing.T) {
	cfg := WireGuardConfig{Interface: "wg0", ListenPort: 51820}
	p := NewWireGuardProvider(cfg)
	if err := p.Initialize(context.Background()); err != nil {
		t.Errorf("Initialize returned unexpected error: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Connect / Disconnect lifecycle
// ---------------------------------------------------------------------------

func TestWireGuardProvider_Connect_SetsRunning(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect returned unexpected error: %v", err)
	}

	p.mu.RLock()
	running := p.running
	p.mu.RUnlock()

	if !running {
		t.Error("expected provider.running = true after Connect")
	}
}

func TestWireGuardProvider_Disconnect_ClearsRunning(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	_ = p.Connect(context.Background())

	if err := p.Disconnect(); err != nil {
		t.Fatalf("Disconnect returned unexpected error: %v", err)
	}

	p.mu.RLock()
	running := p.running
	p.mu.RUnlock()

	if running {
		t.Error("expected provider.running = false after Disconnect")
	}
}

func TestWireGuardProvider_ConnectDisconnectReconnect(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	ctx := context.Background()

	if err := p.Connect(ctx); err != nil {
		t.Fatalf("first Connect error: %v", err)
	}
	if err := p.Disconnect(); err != nil {
		t.Fatalf("Disconnect error: %v", err)
	}
	// Provider should accept a second Connect after Disconnect.
	if err := p.Connect(ctx); err != nil {
		t.Fatalf("second Connect error: %v", err)
	}

	p.mu.RLock()
	running := p.running
	p.mu.RUnlock()
	if !running {
		t.Error("expected provider.running = true after reconnect")
	}
}

// ---------------------------------------------------------------------------
// HandlePacket
// ---------------------------------------------------------------------------

func TestWireGuardProvider_HandlePacket_Send_AccumulatesBytesSent(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	data := []byte("payload")

	out, err := p.HandlePacket(data, "send")
	if err != nil {
		t.Fatalf("HandlePacket error: %v", err)
	}
	// Pass-through — returned slice must equal input.
	if string(out) != string(data) {
		t.Errorf("HandlePacket should return input data unchanged, got %q", out)
	}
	if p.metrics.BytesSent != int64(len(data)) {
		t.Errorf("expected BytesSent=%d, got %d", len(data), p.metrics.BytesSent)
	}
}

func TestWireGuardProvider_HandlePacket_Recv_AccumulatesBytesReceived(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	data := []byte("incoming")

	_, err := p.HandlePacket(data, "recv")
	if err != nil {
		t.Fatalf("HandlePacket error: %v", err)
	}
	if p.metrics.BytesReceived != int64(len(data)) {
		t.Errorf("expected BytesReceived=%d, got %d", len(data), p.metrics.BytesReceived)
	}
	if p.metrics.BytesSent != 0 {
		t.Errorf("expected BytesSent=0 after recv-only, got %d", p.metrics.BytesSent)
	}
}

func TestWireGuardProvider_HandlePacket_MultiplePackets_Accumulates(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})

	_, _ = p.HandlePacket([]byte("abc"), "send")   // 3 bytes sent
	_, _ = p.HandlePacket([]byte("de"), "recv")     // 2 bytes received
	_, _ = p.HandlePacket([]byte("fghi"), "send")   // 4 bytes sent

	m := p.Metrics()
	if m.BytesSent != 7 {
		t.Errorf("expected cumulative BytesSent=7, got %d", m.BytesSent)
	}
	if m.BytesReceived != 2 {
		t.Errorf("expected cumulative BytesReceived=2, got %d", m.BytesReceived)
	}
}

func TestWireGuardProvider_HandlePacket_EmptyData_NoError(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	out, err := p.HandlePacket([]byte{}, "send")
	if err != nil {
		t.Fatalf("HandlePacket with empty data returned error: %v", err)
	}
	if len(out) != 0 {
		t.Errorf("expected empty output, got len=%d", len(out))
	}
}

// ---------------------------------------------------------------------------
// Close
// ---------------------------------------------------------------------------

func TestWireGuardProvider_Close_SetsRunningFalse(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	_ = p.Connect(context.Background())

	if err := p.Close(); err != nil {
		t.Fatalf("Close returned unexpected error: %v", err)
	}

	p.mu.RLock()
	running := p.running
	p.mu.RUnlock()

	if running {
		t.Error("expected provider.running = false after Close")
	}
}

func TestWireGuardProvider_Close_WithoutConnectReturnsNil(t *testing.T) {
	p := NewWireGuardProvider(WireGuardConfig{})
	// Closing without a prior Connect should not panic or error.
	if err := p.Close(); err != nil {
		t.Errorf("Close on never-connected provider returned error: %v", err)
	}
}
