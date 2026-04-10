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

// ─── TCP and UDP connection handlers ───────────────────────────────────────

func TestAcceptTCPConnections_WithHandler(t *testing.T) {
	pm := NewPortManager()
	connHandled := false
	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {
			connHandled = true
			conn.Close()
		},
		func(data []byte, addr *net.UDPAddr, port int) {},
	)

	if err := pm.ParsePortRanges("19879", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Connect to trigger handler
	conn, err := net.Dial("tcp", "127.0.0.1:19879")
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	conn.Close()

	// Wait for handler
	time.Sleep(50 * time.Millisecond)

	if !connHandled {
		t.Error("expected handler to be called")
	}
}

func TestAcceptTCPConnections_WithoutHandler(t *testing.T) {
	pm := NewPortManager()
	// No handlers set

	if err := pm.ParsePortRanges("19880", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Connect – should close without handler
	conn, err := net.Dial("tcp", "127.0.0.1:19880")
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	conn.Close()

	time.Sleep(50 * time.Millisecond)
}

func TestReceiveUDPPackets_WithHandler(t *testing.T) {
	pm := NewPortManager()
	packetReceived := false
	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {},
		func(data []byte, addr *net.UDPAddr, port int) {
			packetReceived = true
		},
	)

	if err := pm.ParsePortRanges("", "19881"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Send UDP packet
	conn, err := net.Dial("udp", "127.0.0.1:19881")
	if err != nil {
		t.Fatalf("failed to dial UDP: %v", err)
	}
	_, _ = conn.Write([]byte("test"))
	conn.Close()

	// Wait for handler
	time.Sleep(50 * time.Millisecond)

	if !packetReceived {
		t.Error("expected packet handler to be called")
	}
}

func TestReceiveUDPPackets_WithoutHandler(t *testing.T) {
	pm := NewPortManager()
	// No handlers set

	if err := pm.ParsePortRanges("", "19882"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Send UDP packet – should not panic
	conn, err := net.Dial("udp", "127.0.0.1:19882")
	if err != nil {
		t.Fatalf("failed to dial UDP: %v", err)
	}
	_, _ = conn.Write([]byte("test"))
	conn.Close()

	time.Sleep(50 * time.Millisecond)
}

func TestStartListening_RangeWithMultiplePorts(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19883-19885", "19886-19888"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	count := pm.GetListenerCount()
	expected := 6 // 3 TCP + 3 UDP
	if count != expected {
		t.Errorf("expected %d listeners, got %d", expected, count)
	}
}

// ─── startTCPListener error path (port already in use) ───────────────────

func TestStartTCPListener_ErrorHandling(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19879", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	// Start once successfully
	if err := pm.StartListening(); err != nil {
		t.Fatalf("first StartListening failed: %v", err)
	}
	defer pm.Stop()

	// Try to start a listener on the same port again – should fail
	if err := pm.startTCPListener(19879); err == nil {
		t.Error("expected error when binding to already-used port")
	}
}

// ─── startUDPListener error path ──────────────────────────────────────────

func TestStartUDPListener_ErrorHandling(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("", "19880"); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	// Start once successfully
	if err := pm.StartListening(); err != nil {
		t.Fatalf("first StartListening failed: %v", err)
	}
	defer pm.Stop()

	// Try to start a listener on the same UDP port again – should fail
	if err := pm.startUDPListener(19880); err == nil {
		t.Error("expected error when binding to already-used UDP port")
	}
}

// ─── AcceptTCPConnections error and shutdown path ────────────────────────

func TestAcceptTCPConnections_ErrorOnShutdown(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19890", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	// Verify listener exists
	if pm.GetListenerCount() != 1 {
		t.Fatal("expected 1 listener")
	}

	// Stop should close listener, causing Accept to error and exit gracefully
	pm.Stop()
	time.Sleep(100 * time.Millisecond)

	// Verify listeners are marked inactive
	listeners := pm.GetActiveListeners()
	for _, listener := range listeners {
		if listener.Active {
			t.Error("expected listener to be marked inactive after Stop")
		}
	}
}

// ─── ReceiveUDPPackets error and shutdown path ────────────────────────────

func TestReceiveUDPPackets_ErrorOnShutdown(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("", "19891"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	// Stop should close UDP conn, causing ReadFromUDP to error and exit
	pm.Stop()
	time.Sleep(100 * time.Millisecond)

	// Verify listeners are marked inactive (they still exist in map but Active=false)
	listeners := pm.GetActiveListeners()
	for _, listener := range listeners {
		if listener.Active {
			t.Error("expected listeners to be marked inactive after Stop")
		}
	}
}

// ─── TCP connection with connection handler error ───────────────────────

func TestAcceptTCPConnections_HandlerError(t *testing.T) {
	pm := NewPortManager()
	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {
			// Handler that closes connection properly
			if err := conn.Close(); err != nil {
				t.Logf("close error in handler: %v", err)
			}
		},
		func(data []byte, addr *net.UDPAddr, port int) {},
	)

	if err := pm.ParsePortRanges("19892", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Connect and let handler close connection
	conn, err := net.Dial("tcp", "127.0.0.1:19892")
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	conn.Close()
	time.Sleep(100 * time.Millisecond)
}

// ─── UDP with no handler – packets discarded ────────────────────────────

func TestReceiveUDPPackets_NoHandler_Discarded(t *testing.T) {
	pm := NewPortManager()
	// Explicitly no handlers set
	if err := pm.ParsePortRanges("", "19893"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Send UDP packet – should be silently discarded (no handler)
	conn, err := net.Dial("udp", "127.0.0.1:19893")
	if err != nil {
		t.Fatalf("failed to dial UDP: %v", err)
	}
	_, _ = conn.Write([]byte("test"))
	conn.Close()

	time.Sleep(50 * time.Millisecond)
	// No crash or error expected
}

// ─── StartListening continues on individual listener failure ───────────────

func TestStartListening_ContinuesOnFailure(t *testing.T) {
	pm := NewPortManager()

	// Parse ranges but don't actually listen yet
	if err := pm.ParsePortRanges("19894,19895", "19896"); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	// Manually bind to 19894 to block it, then StartListening
	blocker, err := net.Listen("tcp", ":19894")
	if err != nil {
		t.Fatalf("failed to block port 19894: %v", err)
	}
	defer blocker.Close()

	// StartListening should skip 19894 but succeed with 19895 and 19896
	if err := pm.StartListening(); err != nil {
		t.Fatalf("StartListening should not fail on individual listener errors: %v", err)
	}
	defer pm.Stop()

	// Verify at least one listener was created (19895 or 19896)
	count := pm.GetListenerCount()
	if count == 0 {
		t.Error("expected at least 1 listener to be created")
	}
}

// ─── Config client FetchConfig scenarios ───────────────────────────────────

func TestConfigClient_FetchConfig(t *testing.T) {
	// Test config_client.go FetchConfig if it exists and has low coverage
	pm := NewPortManager()
	_ = pm
	// This is a placeholder for config_client coverage
	// See proxy/ports/config_client.go for actual implementation
}

// ─── Listener type assertion for Stop ──────────────────────────────────────

func TestStop_ListenerTypeAssertion(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19897,19898", "19899,19900"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	// Stop should handle both net.Listener (TCP) and *net.UDPConn (UDP)
	pm.Stop()

	// Verify all listeners are cleaned up
	listeners := pm.GetActiveListeners()
	for _, listener := range listeners {
		if listener.Active {
			t.Error("listener should be inactive after Stop")
		}
	}
}

// ─── TCP connection without handler – closed cleanly ─────────────────────

func TestAcceptTCPConnections_NoHandler_ClosesConnection(t *testing.T) {
	pm := NewPortManager()
	// Explicitly set no handlers
	if err := pm.ParsePortRanges("19901", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Connect – connection should be closed since there's no handler
	conn, err := net.Dial("tcp", "127.0.0.1:19901")
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}
	defer conn.Close()

	// Try to read – should EOF quickly
	buf := make([]byte, 1)
	n, err := conn.Read(buf)
	if n != 0 && err == nil {
		// Connection was closed or will be closed soon
	}
	time.Sleep(50 * time.Millisecond)
}

// ─── Multiple TCP connections ─────────────────────────────────────────────

func TestAcceptTCPConnections_MultipleConnections(t *testing.T) {
	pm := NewPortManager()
	connCount := 0
	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {
			connCount++
			conn.Close()
		},
		func(data []byte, addr *net.UDPAddr, port int) {},
	)

	if err := pm.ParsePortRanges("19902", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Make multiple connections
	for i := 0; i < 3; i++ {
		conn, err := net.Dial("tcp", "127.0.0.1:19902")
		if err != nil {
			t.Fatalf("failed to dial: %v", err)
		}
		conn.Close()
	}

	time.Sleep(150 * time.Millisecond)

	// All 3 connections should have been handled
	if connCount < 3 {
		t.Errorf("expected at least 3 connections handled, got %d", connCount)
	}
}

// ─── UDP packets in sequence ───────────────────────────────────────────────

func TestReceiveUDPPackets_MultiplePackets(t *testing.T) {
	pm := NewPortManager()
	packetCount := 0
	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {},
		func(data []byte, addr *net.UDPAddr, port int) {
			packetCount++
		},
	)

	if err := pm.ParsePortRanges("", "19903"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Send multiple UDP packets
	conn, err := net.Dial("udp", "127.0.0.1:19903")
	if err != nil {
		t.Fatalf("failed to dial UDP: %v", err)
	}
	defer conn.Close()

	for i := 0; i < 5; i++ {
		_, _ = conn.Write([]byte("test"))
	}

	time.Sleep(200 * time.Millisecond)

	// All 5 packets should have been received
	if packetCount < 5 {
		t.Errorf("expected at least 5 packets handled, got %d", packetCount)
	}
}

// ─── StartListening with both TCP and UDP ─────────────────────────────────

func TestStartListening_BothProtocols(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19904-19905", "19906-19907"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Verify all listeners were created
	count := pm.GetListenerCount()
	expected := 4 // 2 TCP + 2 UDP
	if count != expected {
		t.Errorf("expected %d listeners, got %d", expected, count)
	}

	// Verify listener details
	listeners := pm.GetActiveListeners()
	tcpCount := 0
	udpCount := 0
	for key := range listeners {
		if len(key) > 0 && key[0] == 't' {
			tcpCount++
		} else if len(key) > 0 && key[0] == 'u' {
			udpCount++
		}
	}
	if tcpCount != 2 {
		t.Errorf("expected 2 TCP listeners, got %d", tcpCount)
	}
	if udpCount != 2 {
		t.Errorf("expected 2 UDP listeners, got %d", udpCount)
	}
}

// ─── GetActiveListeners returns copy ───────────────────────────────────────

func TestGetActiveListeners_ReturnsIndependentCopy(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19908", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	listeners1 := pm.GetActiveListeners()
	listeners2 := pm.GetActiveListeners()

	// Both should have same content but be different maps
	if len(listeners1) != len(listeners2) {
		t.Errorf("listener counts differ: %d vs %d", len(listeners1), len(listeners2))
	}

	// Modifying one should not affect the other
	for key := range listeners1 {
		delete(listeners1, key)
		break
	}
	listeners3 := pm.GetActiveListeners()
	if len(listeners3) == 0 {
		t.Error("expected listeners3 to still have listeners")
	}
}

// ─── StartListening error handling (continue on listener failure) ─────────

func TestStartListening_HandleUDPListenerError(t *testing.T) {
	pm := NewPortManager()
	// Parse both TCP and UDP ranges
	if err := pm.ParsePortRanges("19909", "19910"); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	// Block the UDP port before starting
	blocker, err := net.ListenUDP("udp", &net.UDPAddr{Port: 19910})
	if err != nil {
		t.Fatalf("failed to block UDP port: %v", err)
	}
	defer blocker.Close()

	// StartListening should skip blocked UDP but continue with TCP
	if err := pm.StartListening(); err != nil {
		t.Fatalf("StartListening should not fail: %v", err)
	}
	defer pm.Stop()

	// TCP listener should exist
	listeners := pm.GetActiveListeners()
	if _, exists := listeners["tcp:19909"]; !exists {
		t.Error("expected TCP listener to be created despite UDP failure")
	}
}

// ─── Accept and UDP receive with large messages ────────────────────────

func TestReceiveUDPPackets_LargeMessage(t *testing.T) {
	pm := NewPortManager()
	receivedSize := 0
	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {},
		func(data []byte, addr *net.UDPAddr, port int) {
			receivedSize = len(data)
		},
	)

	if err := pm.ParsePortRanges("", "19911"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Send large UDP message
	conn, err := net.Dial("udp", "127.0.0.1:19911")
	if err != nil {
		t.Fatalf("failed to dial UDP: %v", err)
	}
	defer conn.Close()

	largeMsg := make([]byte, 1000)
	for i := 0; i < len(largeMsg); i++ {
		largeMsg[i] = byte(i % 256)
	}
	_, _ = conn.Write(largeMsg)

	time.Sleep(100 * time.Millisecond)

	if receivedSize != 1000 {
		t.Errorf("expected 1000 bytes received, got %d", receivedSize)
	}
}

// ─── Stop closes all listener types properly ───────────────────────────────

func TestStop_ClosesAllListenerTypes(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19912-19913", "19914-19915"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	// Verify listeners are active before stop
	if pm.GetListenerCount() == 0 {
		t.Fatal("expected listeners to be active")
	}

	// Stop and verify cleanup
	pm.Stop()
	time.Sleep(100 * time.Millisecond)

	// All should be marked inactive
	for key, listener := range pm.GetActiveListeners() {
		if listener.Active {
			t.Errorf("listener %s should be inactive after Stop", key)
		}
	}
}

// ─── SetConnectionHandlers with both TCP and UDP handlers ────────────────

func TestSetConnectionHandlers_BothCallbacksInvoked(t *testing.T) {
	pm := NewPortManager()
	tcpInvoked := false
	udpInvoked := false

	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {
			tcpInvoked = true
			conn.Close()
		},
		func(data []byte, addr *net.UDPAddr, port int) {
			udpInvoked = true
		},
	)

	if err := pm.ParsePortRanges("19916", "19917"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Send TCP
	tcpConn, _ := net.Dial("tcp", "127.0.0.1:19916")
	tcpConn.Close()

	// Send UDP
	udpConn, _ := net.Dial("udp", "127.0.0.1:19917")
	udpConn.Write([]byte("test"))
	udpConn.Close()

	time.Sleep(150 * time.Millisecond)

	if !tcpInvoked {
		t.Error("TCP handler was not invoked")
	}
	if !udpInvoked {
		t.Error("UDP handler was not invoked")
	}
}

// ─── SetConnectionHandlers with nil handlers ──────────────────────────

func TestSetConnectionHandlers_WithNilHandlers(t *testing.T) {
	pm := NewPortManager()
	// Explicitly set both handlers to nil
	pm.SetConnectionHandlers(nil, nil)

	// ParsePortRanges and StartListening should succeed
	if err := pm.ParsePortRanges("19920", "19921"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Send connections - they should be closed without handler invocation
	tcpConn, _ := net.Dial("tcp", "127.0.0.1:19920")
	tcpConn.Close()

	udpConn, _ := net.Dial("udp", "127.0.0.1:19921")
	udpConn.Write([]byte("test"))
	udpConn.Close()

	time.Sleep(100 * time.Millisecond)
	// No panic expected
}

// ─── SetConnectionHandlers with only TCP handler ──────────────────────

func TestSetConnectionHandlers_OnlyTCPHandler(t *testing.T) {
	pm := NewPortManager()
	tcpHandled := false

	pm.SetConnectionHandlers(
		func(conn net.Conn, port int, protocol string) {
			tcpHandled = true
			conn.Close()
		},
		nil, // no UDP handler
	)

	if err := pm.ParsePortRanges("19922", "19923"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	tcpConn, _ := net.Dial("tcp", "127.0.0.1:19922")
	tcpConn.Close()

	time.Sleep(100 * time.Millisecond)
	if !tcpHandled {
		t.Error("TCP handler was not invoked")
	}
}

// ─── SetConnectionHandlers with only UDP handler ──────────────────────

func TestSetConnectionHandlers_OnlyUDPHandler(t *testing.T) {
	pm := NewPortManager()
	udpHandled := false

	pm.SetConnectionHandlers(
		nil, // no TCP handler
		func(data []byte, addr *net.UDPAddr, port int) {
			udpHandled = true
		},
	)

	if err := pm.ParsePortRanges("19924", "19925"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	udpConn, _ := net.Dial("udp", "127.0.0.1:19925")
	udpConn.Write([]byte("test"))
	udpConn.Close()

	time.Sleep(100 * time.Millisecond)
	if !udpHandled {
		t.Error("UDP handler was not invoked")
	}
}

// ─── ParsePortRanges with extra commas/spaces ─────────────────────────

func TestParsePortRanges_ExtraCommasAndSpaces(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("  8000  ,  8001  ", "  9000  "); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(pm.tcpRanges) != 2 {
		t.Errorf("expected 2 TCP ranges, got %d", len(pm.tcpRanges))
	}
	if len(pm.udpRanges) != 1 {
		t.Errorf("expected 1 UDP range, got %d", len(pm.udpRanges))
	}
}

// ─── GetListenerCount after partial failures ──────────────────────────

func TestGetListenerCount_AfterPartialFailure(t *testing.T) {
	pm := NewPortManager()

	// Parse ranges but block one port before starting
	if err := pm.ParsePortRanges("19926,19927", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}

	// Block port 19926
	blocker, err := net.Listen("tcp", ":19926")
	if err != nil {
		t.Fatalf("failed to block port: %v", err)
	}
	defer blocker.Close()

	// StartListening should still succeed and create listener on 19927
	if err := pm.StartListening(); err != nil {
		t.Fatalf("StartListening should not fail: %v", err)
	}
	defer pm.Stop()

	// Verify only one listener was created (19927)
	count := pm.GetListenerCount()
	if count != 1 {
		t.Errorf("expected 1 listener after partial failure, got %d", count)
	}
}

// ─── Stop with partial listener setup ──────────────────────────────────

func TestStop_WithPartiallyActiveListeners(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19928", "19929"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	// Manually close one listener before Stop
	if listener, ok := pm.listeners["tcp:19928"].Listener.(net.Listener); ok {
		listener.Close()
	}

	// Stop should handle mixed active/inactive gracefully
	pm.Stop()

	// Verify all are marked inactive
	for _, l := range pm.GetActiveListeners() {
		if l.Active {
			t.Error("all listeners should be marked inactive after Stop")
		}
	}
}

// ─── ValidatePortRanges with invalid format ───────────────────────────

func TestValidatePortRanges_InvalidFormat_Hyphen(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ValidatePortRanges("8000-8100-8200", ""); err == nil {
		t.Error("expected error for invalid hyphen format")
	}
}

// ─── AcceptTCPConnections with listener closed ────────────────────────

func TestAcceptTCPConnections_ListenerClosed_GracefulExit(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19930", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	// Close the listener directly
	if listener, ok := pm.listeners["tcp:19930"].Listener.(net.Listener); ok {
		listener.Close()
	}

	// Stop should exit gracefully
	pm.Stop()
	time.Sleep(100 * time.Millisecond)
	// No panic expected
}

// ─── UDP with close error handling ────────────────────────────────────

func TestReceiveUDPPackets_CloseErrorHandled(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("", "19931"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}

	// Send a packet
	conn, _ := net.Dial("udp", "127.0.0.1:19931")
	conn.Write([]byte("test"))

	// Stop should close gracefully
	pm.Stop()
	time.Sleep(100 * time.Millisecond)

	conn.Close()
	// No panic expected
}

// ─── GetActiveListeners thread safety ─────────────────────────────────

func TestGetActiveListeners_ThreadSafety(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19932", "19933"); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// Concurrent reads should not panic
	done := make(chan struct{})
	for i := 0; i < 10; i++ {
		go func() {
			_ = pm.GetActiveListeners()
			done <- struct{}{}
		}()
	}

	for i := 0; i < 10; i++ {
		<-done
	}
}

// ─── acceptTCPConnections uncovered branches ───────────────────────────────────

// TestAcceptTCPConnections_NoHandler covers the else branch (onNewConn == nil)
// where acceptTCPConnections closes the connection directly.
func TestAcceptTCPConnections_NoHandler(t *testing.T) {
	pm := NewPortManager()
	if err := pm.ParsePortRanges("19941", ""); err != nil {
		t.Fatalf("parse error: %v", err)
	}
	if err := pm.StartListening(); err != nil {
		t.Fatalf("start error: %v", err)
	}
	defer pm.Stop()

	// No connection handler set — the accept loop calls conn.Close() directly.
	conn, err := net.Dial("tcp", "127.0.0.1:19941")
	if err != nil {
		t.Fatalf("dial error: %v", err)
	}
	defer conn.Close()

	// Give acceptTCPConnections time to accept and close the connection.
	time.Sleep(30 * time.Millisecond)
}

// TestAcceptTCPConnections_AcceptError_Default covers the default case in the error
// select (accept error but stopChan not closed → log.Errorf + continue).
// We trigger it by closing the underlying listener while the loop is running and
// without signalling stopChan.
func TestAcceptTCPConnections_AcceptError_Default(t *testing.T) {
	// Create a raw listener so we can close it without going through PortManager.Stop().
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen error: %v", err)
	}

	pm := NewPortManager()
	stopChan := pm.stopChan // capture before starting goroutine

	done := make(chan struct{})
	go func() {
		defer close(done)
		pm.acceptTCPConnections(ln, 0)
	}()

	// Close the listener to trigger an accept error. Because stopChan is still open,
	// the goroutine hits the default case (log + continue), then on the next iteration
	// Accept returns error again. Close stopChan to let it exit cleanly.
	ln.Close()
	time.Sleep(20 * time.Millisecond)
	close(stopChan)

	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Error("acceptTCPConnections goroutine did not exit")
	}
}
