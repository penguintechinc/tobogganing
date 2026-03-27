package ports

import (
	"net"
	"testing"
	"time"
)

// ─── NewPortManager ───────────────────────────────────────────────────────────

func TestNewPortManager(t *testing.T) {
	pm := NewPortManager()
	if pm == nil {
		t.Fatal("expected non-nil port manager")
	}
	if pm.listeners == nil {
		t.Error("listeners map should be initialised")
	}
}

// ─── SetConnectionHandlers ────────────────────────────────────────────────────

func TestSetConnectionHandlers(t *testing.T) {
	pm := NewPortManager()
	called := false
	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) { called = true },
		func(data []byte, addr *net.UDPAddr, port int) {},
	)
	// Just check no panic; handlers are stored
	_ = called
}

// ─── parseRangeString ─────────────────────────────────────────────────────────

func TestParseRangeString_Empty(t *testing.T) {
	pm := NewPortManager()
	ranges, err := pm.parseRangeString("", "tcp")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ranges) != 0 {
		t.Errorf("expected empty ranges, got %d", len(ranges))
	}
}

func TestParseRangeString_WhitespaceOnly(t *testing.T) {
	pm := NewPortManager()
	ranges, err := pm.parseRangeString("   ", "tcp")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ranges) != 0 {
		t.Errorf("expected empty ranges, got %d", len(ranges))
	}
}

func TestParseRangeString_SinglePort(t *testing.T) {
	pm := NewPortManager()
	ranges, err := pm.parseRangeString("8080", "tcp")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ranges) != 1 {
		t.Fatalf("expected 1 range, got %d", len(ranges))
	}
	if ranges[0].StartPort != 8080 || ranges[0].EndPort != 8080 {
		t.Errorf("unexpected range: %+v", ranges[0])
	}
	if ranges[0].Protocol != "tcp" {
		t.Errorf("unexpected protocol: %s", ranges[0].Protocol)
	}
}

func TestParseRangeString_PortRange(t *testing.T) {
	pm := NewPortManager()
	ranges, err := pm.parseRangeString("8000-8100", "tcp")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ranges) != 1 {
		t.Fatalf("expected 1 range, got %d", len(ranges))
	}
	if ranges[0].StartPort != 8000 || ranges[0].EndPort != 8100 {
		t.Errorf("unexpected range: %+v", ranges[0])
	}
}

func TestParseRangeString_MixedSingleAndRange(t *testing.T) {
	pm := NewPortManager()
	ranges, err := pm.parseRangeString("8000-8100,9000,9500-9600", "udp")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ranges) != 3 {
		t.Fatalf("expected 3 ranges, got %d", len(ranges))
	}
	if ranges[1].StartPort != 9000 || ranges[1].EndPort != 9000 {
		t.Errorf("unexpected single port range: %+v", ranges[1])
	}
}

func TestParseRangeString_InvalidPort(t *testing.T) {
	pm := NewPortManager()
	_, err := pm.parseRangeString("notaport", "tcp")
	if err == nil {
		t.Error("expected error for non-numeric port")
	}
}

func TestParseRangeString_InvalidRangeStart(t *testing.T) {
	pm := NewPortManager()
	_, err := pm.parseRangeString("abc-8100", "tcp")
	if err == nil {
		t.Error("expected error for invalid range start")
	}
}

func TestParseRangeString_InvalidRangeEnd(t *testing.T) {
	pm := NewPortManager()
	_, err := pm.parseRangeString("8000-xyz", "tcp")
	if err == nil {
		t.Error("expected error for invalid range end")
	}
}

func TestParseRangeString_StartGreaterThanEnd(t *testing.T) {
	pm := NewPortManager()
	_, err := pm.parseRangeString("9000-8000", "tcp")
	if err == nil {
		t.Error("expected error when start > end")
	}
}

func TestParseRangeString_PortOutOfRange_Low(t *testing.T) {
	pm := NewPortManager()
	_, err := pm.parseRangeString("0", "tcp")
	if err == nil {
		t.Error("expected error for port 0")
	}
}

func TestParseRangeString_PortOutOfRange_High(t *testing.T) {
	pm := NewPortManager()
	_, err := pm.parseRangeString("65536", "tcp")
	if err == nil {
		t.Error("expected error for port > 65535")
	}
}

func TestParseRangeString_RangeOutOfBounds(t *testing.T) {
	pm := NewPortManager()
	_, err := pm.parseRangeString("0-8080", "tcp")
	if err == nil {
		t.Error("expected error for range starting at 0")
	}
}

func TestParseRangeString_EmptySegments(t *testing.T) {
	pm := NewPortManager()
	// Extra commas produce empty segments which are skipped
	ranges, err := pm.parseRangeString("8080,,9090", "tcp")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ranges) != 2 {
		t.Errorf("expected 2 ranges, got %d", len(ranges))
	}
}

func TestParseRangeString_InvalidRangeFormat(t *testing.T) {
	pm := NewPortManager()
	// Three dashes produces an "invalid range format" error
	_, err := pm.parseRangeString("8000-8100-9000", "tcp")
	if err == nil {
		t.Error("expected error for invalid range format with three parts")
	}
}

// ─── ParsePortRanges ─────────────────────────────────────────────────────────

func TestParsePortRanges_ValidBoth(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("8000-8010", "9000-9010"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(pm.tcpRanges) != 1 {
		t.Errorf("expected 1 TCP range, got %d", len(pm.tcpRanges))
	}
	if len(pm.udpRanges) != 1 {
		t.Errorf("expected 1 UDP range, got %d", len(pm.udpRanges))
	}
}

func TestParsePortRanges_InvalidTCP(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("bad", "9000"); err == nil {
		t.Error("expected error for invalid TCP ranges")
	}
}

func TestParsePortRanges_InvalidUDP(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("8000", "bad"); err == nil {
		t.Error("expected error for invalid UDP ranges")
	}
}

// ─── ValidatePortRanges ───────────────────────────────────────────────────────

func TestValidatePortRanges_NoDuplicates(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ValidatePortRanges("8000-8010", "9000-9010"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestValidatePortRanges_DuplicateTCP(t *testing.T) {
	pm := NewPortManager()
	// Overlapping ranges on TCP
	if err := pm.ValidatePortRanges("8000-8010,8005", ""); err == nil {
		t.Error("expected error for duplicate TCP port")
	}
}

func TestValidatePortRanges_DuplicateUDP(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ValidatePortRanges("", "9000-9010,9005"); err == nil {
		t.Error("expected error for duplicate UDP port")
	}
}

func TestValidatePortRanges_InvalidTCPFormat(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ValidatePortRanges("bad", "9000"); err == nil {
		t.Error("expected error for invalid TCP format")
	}
}

func TestValidatePortRanges_InvalidUDPFormat(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ValidatePortRanges("8000", "bad"); err == nil {
		t.Error("expected error for invalid UDP format")
	}
}

// ─── GetListenerCount / GetActiveListeners ────────────────────────────────────

func TestGetListenerCount_Zero(t *testing.T) {
	pm := NewPortManager()
	if pm.GetListenerCount() != 0 {
		t.Errorf("expected 0 listeners, got %d", pm.GetListenerCount())
	}
}

func TestGetActiveListeners_Empty(t *testing.T) {
	pm := NewPortManager()
	listeners := pm.GetActiveListeners()
	if len(listeners) != 0 {
		t.Errorf("expected empty listeners, got %d", len(listeners))
	}
}

// ─── StartListening and Stop ──────────────────────────────────────────────────

func TestStartListening_EmptyRanges(t *testing.T) {
	pm := NewPortManager()
	if err := pm.StartListening(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pm.GetListenerCount() != 0 {
		t.Errorf("expected 0 listeners with empty ranges, got %d", pm.GetListenerCount())
	}
	pm.Stop()
}

func TestStartListening_SingleTCPPort(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19876", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	if pm.GetListenerCount() != 1 {
		t.Errorf("expected 1 listener, got %d", pm.GetListenerCount())
	}

	listeners := pm.GetActiveListeners()
	if _, exists := listeners["tcp:19876"]; !exists {
		t.Error("expected tcp:19876 listener")
	}
}

func TestStartListening_SingleUDPPort(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("", "19877"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	if pm.GetListenerCount() != 1 {
		t.Errorf("expected 1 listener, got %d", pm.GetListenerCount())
	}
}

func TestStop_NoListeners(t *testing.T) {
	pm := NewPortManager()
	// Should not panic
	pm.Stop()
}

func TestStop_WithListeners(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19878", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	done := make(chan struct{})
	go func() {
		pm.Stop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Error("Stop timed out")
	}
}
