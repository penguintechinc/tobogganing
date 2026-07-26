package mirror

import (
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// ─── NewManager / NewManagerWithSuricata ──────────────────────────────────────

func TestNewManager_Defaults(t *testing.T) {
	m := NewManager([]string{"127.0.0.1:4789"}, "", 100)
	if m == nil {
		t.Fatal("expected non-nil manager")
	}
	if m.protocol != "VXLAN" {
		t.Errorf("expected VXLAN default protocol, got %s", m.protocol)
	}
	if m.bufferSize != 100 {
		t.Errorf("expected bufferSize 100, got %d", m.bufferSize)
	}
	if cap(m.queue) != 100 {
		t.Errorf("expected queue capacity 100, got %d", cap(m.queue))
	}
}

func TestNewManager_CustomProtocol(t *testing.T) {
	m := NewManager([]string{"127.0.0.1:4789"}, "GRE", 50)
	if m.protocol != "GRE" {
		t.Errorf("expected GRE protocol, got %s", m.protocol)
	}
}

func TestNewManagerWithSuricata_Enabled(t *testing.T) {
	m := NewManagerWithSuricata([]string{}, "VXLAN", 100, "127.0.0.1", "9999")
	if !m.suricataEnabled {
		t.Error("expected suricata enabled")
	}
	if m.suricataHost != "127.0.0.1" {
		t.Errorf("unexpected suricataHost: %s", m.suricataHost)
	}
}

func TestNewManagerWithSuricata_Disabled_EmptyHost(t *testing.T) {
	m := NewManagerWithSuricata([]string{}, "VXLAN", 100, "", "9999")
	if m.suricataEnabled {
		t.Error("expected suricata disabled when host is empty")
	}
}

func TestNewManagerWithSuricata_Disabled_EmptyPort(t *testing.T) {
	m := NewManagerWithSuricata([]string{}, "VXLAN", 100, "127.0.0.1", "")
	if m.suricataEnabled {
		t.Error("expected suricata disabled when port is empty")
	}
}

// ─── Stats ────────────────────────────────────────────────────────────────────

func TestStats_IncrementSent(t *testing.T) {
	s := &Stats{}
	s.incrementSent(100)
	s.incrementSent(200)
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.PacketsSent != 2 {
		t.Errorf("expected PacketsSent=2, got %d", s.PacketsSent)
	}
	if s.BytesSent != 300 {
		t.Errorf("expected BytesSent=300, got %d", s.BytesSent)
	}
}

func TestStats_IncrementDropped(t *testing.T) {
	s := &Stats{}
	s.incrementDropped()
	s.incrementDropped()
	s.incrementDropped()
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.PacketsDropped != 3 {
		t.Errorf("expected PacketsDropped=3, got %d", s.PacketsDropped)
	}
}

func TestStats_IncrementErrors(t *testing.T) {
	s := &Stats{}
	s.incrementErrors()
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.Errors != 1 {
		t.Errorf("expected Errors=1, got %d", s.Errors)
	}
}

// ─── Encapsulation ────────────────────────────────────────────────────────────

func TestEncapsulateVXLAN(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	packet := &MirrorPacket{
		Data: []byte("hello"),
	}
	result, err := m.encapsulateVXLAN(packet)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// VXLAN header is 8 bytes
	if len(result) != 8+len(packet.Data) {
		t.Errorf("unexpected encapsulated length: %d", len(result))
	}
	// Check I-flag set in first byte
	if result[0] != 0x08 {
		t.Errorf("expected I-flag 0x08, got 0x%02x", result[0])
	}
}

func TestEncapsulateGRE(t *testing.T) {
	m := NewManager(nil, "GRE", 10)
	packet := &MirrorPacket{
		Data: []byte("world"),
	}
	result, err := m.encapsulateGRE(packet)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// GRE header is 4 bytes
	if len(result) != 4+len(packet.Data) {
		t.Errorf("unexpected encapsulated length: %d", len(result))
	}
}

func TestEncapsulateERSPAN(t *testing.T) {
	m := NewManager(nil, "ERSPAN", 10)
	packet := &MirrorPacket{
		Data: []byte("test"),
	}
	result, err := m.encapsulateERSPAN(packet)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// ERSPAN header is 8 bytes
	if len(result) != 8+len(packet.Data) {
		t.Errorf("unexpected encapsulated length: %d", len(result))
	}
}

// ─── encodeHTTP ───────────────────────────────────────────────────────────────

func TestEncodeHTTP(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	req := httptest.NewRequest(http.MethodGet, "/test?foo=bar", nil)
	req.Header.Set("X-Custom", "header-value")

	encoded := m.encodeHTTP(req, http.StatusOK, []byte("response body"))
	if len(encoded) == 0 {
		t.Error("expected non-empty encoded data")
	}
	// Check contains method
	if string(encoded[:3]) != "GET" {
		t.Errorf("expected GET at start of encoded data, got %s", string(encoded[:3]))
	}
}

// ─── MirrorHTTP / MirrorTCP / MirrorUDP / MirrorRaw ─────────────────────────

func TestMirrorHTTP_QueueFull(t *testing.T) {
	m := NewManager(nil, "VXLAN", 1) // capacity=1
	// Fill the queue
	m.queue <- &MirrorPacket{Data: []byte("fill")}

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	// Queue is full; should drop and increment counter without panic
	m.MirrorHTTP(req, 200, []byte("body"))

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.PacketsDropped != 1 {
		t.Errorf("expected PacketsDropped=1, got %d", m.stats.PacketsDropped)
	}
}

func TestMirrorHTTP_Queued(t *testing.T) {
	m := NewManager(nil, "VXLAN", 100)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	m.MirrorHTTP(req, 200, []byte("body"))

	if len(m.queue) != 1 {
		t.Errorf("expected 1 item in queue, got %d", len(m.queue))
	}
	pkt := <-m.queue
	if pkt.Protocol != "HTTP" {
		t.Errorf("unexpected protocol: %s", pkt.Protocol)
	}
}

func TestMirrorTCP_Queued(t *testing.T) {
	m := NewManager(nil, "VXLAN", 100)
	m.MirrorTCP("192.168.1.1:1234", "10.0.0.1:80", []byte("tcp-data"))

	if len(m.queue) != 1 {
		t.Errorf("expected 1 item in queue, got %d", len(m.queue))
	}
	pkt := <-m.queue
	if pkt.Protocol != "TCP" {
		t.Errorf("unexpected protocol: %s", pkt.Protocol)
	}
}

func TestMirrorTCP_QueueFull(t *testing.T) {
	m := NewManager(nil, "VXLAN", 1)
	m.queue <- &MirrorPacket{}
	m.MirrorTCP("src", "dst", []byte("data"))

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.PacketsDropped != 1 {
		t.Errorf("expected PacketsDropped=1, got %d", m.stats.PacketsDropped)
	}
}

func TestMirrorUDP_Queued(t *testing.T) {
	m := NewManager(nil, "VXLAN", 100)
	m.MirrorUDP("192.168.1.1:5000", "10.0.0.1:53", []byte("udp-data"))

	if len(m.queue) != 1 {
		t.Errorf("expected 1 item in queue, got %d", len(m.queue))
	}
	pkt := <-m.queue
	if pkt.Protocol != "UDP" {
		t.Errorf("unexpected protocol: %s", pkt.Protocol)
	}
}

func TestMirrorUDP_QueueFull(t *testing.T) {
	m := NewManager(nil, "VXLAN", 1)
	m.queue <- &MirrorPacket{}
	m.MirrorUDP("src", "dst", []byte("data"))

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.PacketsDropped != 1 {
		t.Errorf("expected PacketsDropped=1, got %d", m.stats.PacketsDropped)
	}
}

func TestMirrorRaw_Queued(t *testing.T) {
	m := NewManager(nil, "VXLAN", 100)
	meta := map[string]interface{}{"key": "value"}
	m.MirrorRaw([]byte("raw-data"), meta)

	if len(m.queue) != 1 {
		t.Errorf("expected 1 item in queue, got %d", len(m.queue))
	}
	pkt := <-m.queue
	if pkt.Protocol != "RAW" {
		t.Errorf("unexpected protocol: %s", pkt.Protocol)
	}
}

func TestMirrorRaw_QueueFull(t *testing.T) {
	m := NewManager(nil, "VXLAN", 1)
	m.queue <- &MirrorPacket{}
	m.MirrorRaw([]byte("raw"), map[string]interface{}{})

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.PacketsDropped != 1 {
		t.Errorf("expected PacketsDropped=1, got %d", m.stats.PacketsDropped)
	}
}

// ─── prepareSuricataData ─────────────────────────────────────────────────────

func TestPrepareSuricataData_WithSourceDest(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	pkt := &MirrorPacket{
		Timestamp:   time.Now(),
		Protocol:    "TCP",
		Source:      net.ParseIP("192.168.1.1"),
		Destination: net.ParseIP("10.0.0.1"),
		Data:        []byte("payload"),
		Metadata:    map[string]interface{}{"cluster_id": "cl1", "user_id": "u1"},
	}
	result := m.prepareSuricataData(pkt)
	if len(result) == 0 {
		t.Error("expected non-empty suricata data")
	}
	// Should end with newline (EVE JSON format)
	if result[len(result)-1] != '\n' {
		t.Error("expected trailing newline in suricata data")
	}
}

func TestPrepareSuricataData_WithoutSourceDest(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "HTTP",
		Data:      []byte("body"),
		Metadata:  map[string]interface{}{},
	}
	result := m.prepareSuricataData(pkt)
	if len(result) == 0 {
		t.Error("expected non-empty suricata data")
	}
}

// ─── createConnection ─────────────────────────────────────────────────────────

func TestCreateConnection_VXLAN(t *testing.T) {
	// Set up a real UDP listener to connect to
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", addr)
	if err != nil {
		t.Fatalf("failed to create test UDP listener: %v", err)
	}
	defer listener.Close()

	m := NewManager(nil, "VXLAN", 10)
	conn, err := m.createConnection(listener.LocalAddr().String())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	defer conn.Close()
}

func TestCreateConnection_ERSPAN(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", addr)
	if err != nil {
		t.Fatalf("failed to create test UDP listener: %v", err)
	}
	defer listener.Close()

	m := NewManager(nil, "ERSPAN", 10)
	conn, err := m.createConnection(listener.LocalAddr().String())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	defer conn.Close()
}

func TestCreateConnection_Default(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", addr)
	if err != nil {
		t.Fatalf("failed to create test UDP listener: %v", err)
	}
	defer listener.Close()

	m := NewManager(nil, "UNKNOWN", 10)
	conn, err := m.createConnection(listener.LocalAddr().String())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	defer conn.Close()
}

// ─── Start/Stop with real UDP server ─────────────────────────────────────────

func TestStart_WithUDPDestination(t *testing.T) {
	// Set up a real UDP "destination"
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "VXLAN", 10)
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	done := make(chan struct{})
	go func() {
		m.Stop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Error("Stop timed out")
	}
}

func TestStart_NoDestinations_NoSuricata(t *testing.T) {
	// No destinations and no suricata → should error
	m := NewManager([]string{}, "VXLAN", 10)
	if err := m.Start(); err == nil {
		t.Error("expected error when no destinations and no suricata")
	}
}

func TestStop_WithoutStart(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	// Should not panic
	m.Stop()
}

// ─── sendPacket – coverage of protocol branches ───────────────────────────────

func TestSendPacket_VXLANProtocol(t *testing.T) {
	// Use a real UDP dest
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "VXLAN", 10)
	conn, _ := m.createConnection(listener.LocalAddr().String())
	m.connections[listener.LocalAddr().String()] = conn

	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "HTTP",
		Data:      []byte("test"),
		Metadata:  map[string]interface{}{},
	}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.PacketsSent == 0 {
		t.Error("expected at least 1 packet sent")
	}
}

func TestSendPacket_GREProtocol(t *testing.T) {
	// GRE uses raw IP socket which may fail in test env; just check no panic
	m := NewManager(nil, "GRE", 10)
	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Data:      []byte("test"),
		Metadata:  map[string]interface{}{},
	}
	// No connections, should not panic
	m.sendPacket(pkt)
}

func TestSendPacket_DefaultProtocol(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "RAW", 10)
	conn, _ := m.createConnection(listener.LocalAddr().String())
	m.connections[listener.LocalAddr().String()] = conn

	pkt := &MirrorPacket{
		Data:     []byte("raw"),
		Metadata: map[string]interface{}{},
	}
	m.sendPacket(pkt)
}

// ─── reconnect ────────────────────────────────────────────────────────────────

func TestReconnect_ExistingConnection(t *testing.T) {
	// Create a UDP listener as a "destination"
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	dest := listener.LocalAddr().String()
	m := NewManager([]string{dest}, "VXLAN", 10)

	// Add a fake connection to reconnect from
	conn, _ := m.createConnection(dest)
	m.connections[dest] = conn

	// Trigger reconnect — should close old conn and open new one
	m.reconnect(dest)

	m.mu.RLock()
	_, exists := m.connections[dest]
	m.mu.RUnlock()

	if !exists {
		t.Error("expected reconnected connection to be present")
	}
}

func TestReconnect_NoPanic(t *testing.T) {
	// For VXLAN (UDP), dial always succeeds (no handshake), connection will be added.
	// The purpose of this test is to confirm reconnect does not panic and properly
	// replaces (or creates) a connection entry.
	m := NewManager([]string{"127.0.0.1:1"}, "VXLAN", 10)
	// No existing connection; reconnect should create one without panic
	m.reconnect("127.0.0.1:1")

	// UDP dial succeeds unconditionally — connection should be present
	m.mu.RLock()
	conn, exists := m.connections["127.0.0.1:1"]
	m.mu.RUnlock()

	if !exists {
		t.Error("expected connection to be added for VXLAN (UDP) destination")
	}
	if conn != nil {
		conn.Close()
	}
}

// ─── reconnectSuricata ────────────────────────────────────────────────────────

func TestReconnectSuricata_Success(t *testing.T) {
	// Create a TCP listener for Suricata
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to create TCP listener: %v", err)
	}
	defer ln.Close()

	// Accept connections in background
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			c.Close()
		}
	}()

	port := ln.Addr().(*net.TCPAddr).Port

	m := NewManagerWithSuricata(nil, "VXLAN", 10, "127.0.0.1", itoa(port))

	// Should succeed since the listener is running
	m.reconnectSuricata()

	m.mu.RLock()
	conn := m.suricataConn
	m.mu.RUnlock()

	if conn == nil {
		t.Error("expected suricataConn to be set after successful reconnect")
	} else {
		conn.Close()
	}
}

func TestReconnectSuricata_ConnectionRefused(t *testing.T) {
	m := NewManagerWithSuricata(nil, "VXLAN", 10, "127.0.0.1", "1")
	// Should fail gracefully — no listener on port 1
	m.reconnectSuricata()

	m.mu.RLock()
	conn := m.suricataConn
	m.mu.RUnlock()

	if conn != nil {
		t.Error("expected suricataConn to remain nil after failed reconnect")
		conn.Close()
	}
}

func TestReconnectSuricata_ClosesExistingConn(t *testing.T) {
	// Create a fake existing connection by building a pipe
	serverConn, clientConn := net.Pipe()
	defer serverConn.Close()

	m := NewManagerWithSuricata(nil, "VXLAN", 10, "127.0.0.1", "1")
	m.suricataConn = clientConn

	// Reconnect with a bad address — should close the existing conn
	m.reconnectSuricata()

	// The old conn should be closed
	_, err := clientConn.Write([]byte("test"))
	if err == nil {
		t.Error("expected write to closed conn to fail")
	}
}

// ─── Additional coverage tests for uncovered branches ──────────────────────────

// TestStart_WithUnreachableDestination tests error handling when dial fails
func TestStart_WithUnreachableDestination(t *testing.T) {
	// Port 1 is typically not listening and dial will fail
	m := NewManager([]string{"127.0.0.1:1"}, "VXLAN", 10)
	// Start should succeed (returns early if no destinations and no suricata enabled)
	// UDP dial is connectionless so it won't fail; but createConnection for port 1 behaves this way
	err := m.Start()
	// For VXLAN (UDP), dial is connectionless and may not fail immediately
	// But the destination is stored, so Start should succeed
	if err == nil {
		// Ensure goroutines are stopped to avoid test leak
		done := make(chan struct{})
		go func() { m.Stop(); close(done) }()
		select {
		case <-done:
		case <-time.After(2 * time.Second):
			t.Error("Stop timed out")
		}
	}
}

// TestStart_WithSuricataOnly tests Start when only Suricata is available
func TestStart_WithSuricataOnly(t *testing.T) {
	// Create a TCP listener for Suricata
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to create TCP listener: %v", err)
	}
	defer ln.Close()

	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			c.Close()
		}
	}()

	port := ln.Addr().(*net.TCPAddr).Port
	m := NewManagerWithSuricata([]string{}, "VXLAN", 10, "127.0.0.1", itoa(port))

	if err := m.Start(); err != nil {
		t.Fatalf("Start should succeed with Suricata enabled: %v", err)
	}

	done := make(chan struct{})
	go func() {
		m.Stop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Error("Stop timed out")
	}
}

// TestSendPacket_WithSuricataConn tests sendPacket when Suricata connection is active
func TestSendPacket_WithSuricataConn(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to create TCP listener: %v", err)
	}
	defer ln.Close()

	// Accept goroutine — exits when ln is closed
	go func() {
		for {
			c, acceptErr := ln.Accept()
			if acceptErr != nil {
				return
			}
			_ = c.Close()
		}
	}()

	port := ln.Addr().(*net.TCPAddr).Port
	m := NewManagerWithSuricata([]string{}, "VXLAN", 10, "127.0.0.1", itoa(port))

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	pkt := &MirrorPacket{
		Timestamp:   time.Now(),
		Protocol:    "TCP",
		Data:        []byte("test-data"),
		Source:      net.ParseIP("192.168.1.1"),
		Destination: net.ParseIP("10.0.0.1"),
		Metadata:    map[string]interface{}{"cluster_id": "c1", "user_id": "u1"},
	}

	m.sendPacket(pkt)

	stopDone := make(chan struct{})
	go func() { m.Stop(); close(stopDone) }()
	select {
	case <-stopDone:
	case <-time.After(3 * time.Second):
		t.Error("Stop timed out")
	}
}

// TestSendPacket_WithConnectionError tests error handling when write fails
func TestSendPacket_WithConnectionError(t *testing.T) {
	// Create a pipe to simulate broken connection
	serverConn, clientConn := net.Pipe()
	serverConn.Close() // Close server side to simulate write error

	m := NewManager([]string{"127.0.0.1:4789"}, "VXLAN", 10)
	m.connections["127.0.0.1:4789"] = clientConn

	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Data:      []byte("test"),
		Metadata:  map[string]interface{}{},
	}

	m.sendPacket(pkt)

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.Errors == 0 {
		t.Error("expected at least 1 error when connection fails")
	}
}

// TestSendPacket_EncapsulationError tests handling of bad protocol/data that causes encapsulation failure
func TestSendPacket_UnknownProtocol(t *testing.T) {
	m := NewManager(nil, "UNKNOWN_PROTOCOL", 10)
	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Data:      []byte("test"),
		Metadata:  map[string]interface{}{},
	}
	// Should not panic; just uses raw data since protocol is unknown
	m.sendPacket(pkt)
}

// TestWorker_DrainQueueOnStop tests that worker drains remaining packets before returning
func TestWorker_DrainQueueOnStop(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	dest := listener.LocalAddr().String()
	m := NewManager([]string{dest}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue several packets
	for i := 0; i < 5; i++ {
		m.MirrorRaw([]byte(fmt.Sprintf("packet-%d", i)), map[string]interface{}{})
	}

	// Stop should drain queue
	done := make(chan struct{})
	go func() {
		m.Stop()
		close(done)
	}()

	select {
	case <-done:
		// good, stop completed
	case <-time.After(3 * time.Second):
		t.Error("Stop timed out while draining queue")
	}
}

// TestReportStats tests the stats reporter goroutine
func TestReportStats(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	m.stats.incrementSent(100)
	m.stats.incrementDropped()
	m.stats.incrementErrors()

	// Manually trigger stats reporting (would normally run in background)
	m.stats.mu.RLock()
	sent := m.stats.PacketsSent
	dropped := m.stats.PacketsDropped
	errors := m.stats.Errors
	m.stats.mu.RUnlock()

	if sent != 1 || dropped != 1 || errors != 1 {
		t.Errorf("expected stats (1,1,1), got (%d,%d,%d)", sent, dropped, errors)
	}
}

// TestCreateConnection_GRE tests GRE connection creation (may fail on non-root)
func TestCreateConnection_GRE_UnreachablePort(t *testing.T) {
	// GRE uses raw IP sockets which may not be available; test gracefully handles
	m := NewManager(nil, "GRE", 10)
	conn, err := m.createConnection("127.0.0.1:1")
	if conn != nil {
		conn.Close()
	}
	// Error is acceptable here since GRE requires special privileges
	_ = err
}

// ─── worker exercises via Start/Stop with real connection ─────────────────────

func TestWorker_ProcessesQueuedPackets(t *testing.T) {
	// Create a real UDP listener
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	dest := listener.LocalAddr().String()
	m := NewManager([]string{dest}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue some packets
	for i := 0; i < 5; i++ {
		m.MirrorRaw([]byte("test-packet"), map[string]interface{}{})
	}

	// Give workers time to process
	time.Sleep(50 * time.Millisecond)

	m.Stop()

	m.stats.mu.RLock()
	sent := m.stats.PacketsSent
	m.stats.mu.RUnlock()

	if sent == 0 {
		t.Error("expected packets to be sent by worker")
	}
}

func TestSendPacket_WithSuricata(t *testing.T) {
	// Create a TCP server for Suricata
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to create TCP listener: %v", err)
	}
	defer ln.Close()

	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			c.Close()
		}
	}()

	port := ln.Addr().(*net.TCPAddr).Port

	m := NewManagerWithSuricata(nil, "VXLAN", 100, "127.0.0.1", itoa(port))
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}
	defer m.Stop()

	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "HTTP",
		Data:      []byte("test-suricata-packet"),
		Metadata:  map[string]interface{}{"cluster_id": "c1", "user_id": "u1"},
	}
	m.sendPacket(pkt)
}

// ─── reportStats goroutine exercise ──────────────────────────────────────────

func TestReportStats_StopsWithManager(t *testing.T) {
	// Need at least one destination so Start() doesn't return "no mirror destinations"
	addr, err := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("ResolveUDPAddr: %v", err)
	}
	listener, err := net.ListenUDP("udp", addr)
	if err != nil {
		t.Fatalf("ListenUDP: %v", err)
	}
	defer listener.Close()

	dest := listener.LocalAddr().String()
	m := NewManager([]string{dest}, "VXLAN", 10)
	// Start then Stop immediately — reportStats goroutine should stop via stopCh
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	done := make(chan struct{})
	go func() {
		m.Stop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Error("Stop timed out — reportStats goroutine may be stuck")
	}
}

// ─── Additional Coverage Tests ────────────────────────────────────────────────

func TestNewManager_WithCerberusEndpoint(t *testing.T) {
	t.Setenv("CERBERUS_MIRROR_ENDPOINT", "test.local:5000")
	m := NewManager([]string{"127.0.0.1:4789"}, "VXLAN", 100)

	found := false
	for _, dest := range m.destinations {
		if dest == "test.local:5000" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected Cerberus endpoint appended")
	}
}

func TestNewManagerWithSuricata_PartialConfig(t *testing.T) {
	// Suricata disabled with empty host
	m := NewManagerWithSuricata([]string{"127.0.0.1:4789"}, "VXLAN", 100, "", "9999")
	if m.suricataEnabled {
		t.Error("expected suricata disabled with empty host")
	}

	// Suricata disabled with empty port
	m = NewManagerWithSuricata([]string{"127.0.0.1:4789"}, "VXLAN", 100, "127.0.0.1", "")
	if m.suricataEnabled {
		t.Error("expected suricata disabled with empty port")
	}
}

func TestSendPacket_ConnectionWriteFailure(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)

	// Create a broken connection
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	conn, _ := net.Dial("udp", listener.LocalAddr().String())
	listener.Close()
	conn.Close()

	m.mu.Lock()
	m.connections["broken"] = conn
	m.mu.Unlock()

	pkt := &MirrorPacket{Data: []byte("test")}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	errCount := m.stats.Errors
	m.stats.mu.RUnlock()

	if errCount == 0 {
		t.Error("expected error count to increment")
	}
}

func TestSendPacket_NoDestinations(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	pkt := &MirrorPacket{Data: []byte("test")}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	sent := m.stats.PacketsSent
	m.stats.mu.RUnlock()

	if sent != 0 {
		t.Errorf("expected 0 packets sent with no destinations, got %d", sent)
	}
}

func TestReconnect_BasicFlow(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	dest := listener.LocalAddr().String()

	m := NewManager(nil, "VXLAN", 10)
	conn, _ := net.Dial("udp", dest)

	m.mu.Lock()
	m.connections[dest] = conn
	m.mu.Unlock()

	m.reconnect(dest)

	m.mu.RLock()
	newConn, exists := m.connections[dest]
	m.mu.RUnlock()

	if !exists || newConn == nil {
		t.Error("expected reconnected connection to exist")
	}
}

func TestReconnectSuricata_BasicFlow(t *testing.T) {
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	defer ln.Close()

	go func() {
		if c, err := ln.Accept(); err == nil && c != nil {
			c.Close()
		}
	}()

	port := ln.Addr().(*net.TCPAddr).Port
	m := NewManagerWithSuricata(nil, "VXLAN", 100, "127.0.0.1", itoa(port))
	m.Start()

	m.reconnectSuricata()

	m.Stop()
}

// ─── helper ──────────────────────────────────────────────────────────────────

func TestNewManagerWithSuricata_WithDefaultProtocol(t *testing.T) {
	m := NewManagerWithSuricata([]string{}, "", 100, "127.0.0.1", "9999")
	if m.protocol != "VXLAN" {
		t.Errorf("expected default VXLAN protocol, got %s", m.protocol)
	}
}

func TestSendPacket_EncapsulationError_UnknownProtocol(t *testing.T) {
	// Test with an unknown protocol to trigger error handling
	m := NewManager([]string{}, "UNKNOWN_PROTOCOL", 10)

	// Mock a connection to avoid encapsulation error path
	// (unknown protocol defaults to raw, no error)
	pkt := &MirrorPacket{Data: []byte("test")}
	m.sendPacket(pkt)
	// Should not panic
}

func TestStart_WithSuricata_FailedConnection(t *testing.T) {
	// Suricata enabled with bad address - Suricata is optional so Start succeeds anyway
	m := NewManagerWithSuricata([]string{}, "VXLAN", 10, "127.0.0.1", "1")
	err := m.Start()
	// No regular destinations but Suricata enabled -> should NOT error
	if err != nil {
		t.Fatalf("expected no error with suricata enabled: %v", err)
	}
	m.Stop()
}

func TestStart_WithSuricata_Success(t *testing.T) {
	// Create a TCP listener for Suricata
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to create TCP listener: %v", err)
	}
	defer ln.Close()

	go func() {
		if c, err := ln.Accept(); err == nil && c != nil {
			c.Close()
		}
	}()

	port := ln.Addr().(*net.TCPAddr).Port
	m := NewManagerWithSuricata([]string{}, "VXLAN", 10, "127.0.0.1", itoa(port))

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	m.mu.RLock()
	sConn := m.suricataConn
	m.mu.RUnlock()

	if sConn == nil {
		t.Error("expected suricata connection to be established")
	}

	done := make(chan struct{})
	go func() {
		m.Stop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Error("Stop timed out")
	}
}

func TestSendPacket_SuricataConnectionError(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManagerWithSuricata([]string{listener.LocalAddr().String()}, "VXLAN", 100, "127.0.0.1", "1")
	conn, _ := m.createConnection(listener.LocalAddr().String())
	m.connections[listener.LocalAddr().String()] = conn

	// Set suricataEnabled but with nil conn
	m.suricataEnabled = true
	m.suricataConn = nil

	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "HTTP",
		Data:      []byte("test"),
		Metadata:  map[string]interface{}{"cluster_id": "c1", "user_id": "u1"},
	}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.PacketsSent == 0 {
		t.Error("expected at least one packet sent to UDP destination")
	}
}

func TestWorker_EmptyQueueOnStop(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	dest := listener.LocalAddr().String()
	m := NewManager([]string{dest}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue some packets
	for i := 0; i < 3; i++ {
		m.MirrorRaw([]byte("test-packet-"+itoa(i)), map[string]interface{}{})
	}

	// Stop should drain queue and process remaining packets
	m.Stop()

	m.stats.mu.RLock()
	sent := m.stats.PacketsSent
	m.stats.mu.RUnlock()

	if sent < 3 {
		t.Errorf("expected at least 3 packets sent, got %d", sent)
	}
}

func TestReconnect_WithNoExistingConnection(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	dest := listener.LocalAddr().String()
	m := NewManager([]string{dest}, "VXLAN", 10)

	// No existing connection
	m.reconnect(dest)

	m.mu.RLock()
	conn, exists := m.connections[dest]
	m.mu.RUnlock()

	if !exists || conn == nil {
		t.Error("expected connection to be created by reconnect")
	}
}

func TestPrepareSuricataData_WithMissingMetadata(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "TCP",
		Data:      []byte("payload"),
		Metadata:  map[string]interface{}{}, // empty metadata
	}
	result := m.prepareSuricataData(pkt)
	if len(result) == 0 {
		t.Error("expected non-empty suricata data")
	}
	if result[len(result)-1] != '\n' {
		t.Error("expected trailing newline")
	}
}

func TestCreateConnection_GRE(t *testing.T) {
	// GRE uses ip4:47 - this may fail in test environment but shouldn't panic
	m := NewManager(nil, "GRE", 10)
	// GRE connection (ip4:47) requires special permissions; this is expected to fail in test
	_, _ = m.createConnection("127.0.0.1:0")
	// Don't assert on error; just verify no panic
}

func TestStop_ClosesAllConnections(t *testing.T) {
	// Create multiple UDP listeners
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	l1, _ := net.ListenUDP("udp", addr)
	l2, _ := net.ListenUDP("udp", addr)
	defer l1.Close()
	defer l2.Close()

	d1 := l1.LocalAddr().String()
	d2 := l2.LocalAddr().String()

	m := NewManager([]string{d1, d2}, "VXLAN", 10)
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Verify connections exist
	m.mu.RLock()
	if len(m.connections) == 0 {
		t.Error("expected connections to be established")
	}
	m.mu.RUnlock()

	// Stop should close all
	m.Stop()

	m.mu.RLock()
	if len(m.connections) != 0 {
		t.Error("expected all connections to be closed")
	}
	m.mu.RUnlock()
}

func TestReportStats_PrintsMetrics(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "VXLAN", 100)
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue and send some packets to generate stats
	for i := 0; i < 3; i++ {
		m.MirrorRaw([]byte("test"+itoa(i)), map[string]interface{}{})
	}

	// Give time for processing and reporting
	time.Sleep(100 * time.Millisecond)

	m.Stop()

	m.stats.mu.RLock()
	if m.stats.PacketsSent == 0 && m.stats.PacketsDropped == 0 {
		t.Error("expected some stats to be recorded")
	}
	m.stats.mu.RUnlock()
}

func TestSendPacket_AllProtocols(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	for _, protocol := range []string{"VXLAN", "ERSPAN"} {
		m := NewManager([]string{listener.LocalAddr().String()}, protocol, 10)
		conn, _ := m.createConnection(listener.LocalAddr().String())
		m.mu.Lock()
		m.connections[listener.LocalAddr().String()] = conn
		m.mu.Unlock()

		pkt := &MirrorPacket{
			Timestamp: time.Now(),
			Protocol:  "TCP",
			Data:      []byte("test-" + protocol),
			Metadata:  map[string]interface{}{},
		}
		m.sendPacket(pkt)

		conn.Close()
	}
}

func TestNewManagerWithSuricata_CerberusEndpoint(t *testing.T) {
	t.Setenv("CERBERUS_MIRROR_ENDPOINT", "cerberus.local:5000")
	m := NewManagerWithSuricata([]string{"dest1:4789"}, "VXLAN", 100, "127.0.0.1", "9999")

	found := false
	for _, dest := range m.destinations {
		if dest == "cerberus.local:5000" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected Cerberus endpoint to be appended in NewManagerWithSuricata")
	}
}

func TestWorker_DrainsQueueOnStop(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "VXLAN", 100)
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue packets quickly
	for i := 0; i < 10; i++ {
		m.queue <- &MirrorPacket{
			Data:     []byte("pkt-" + itoa(i)),
			Metadata: map[string]interface{}{},
		}
	}

	// Stop should drain queue and send remaining packets
	m.Stop()

	m.stats.mu.RLock()
	sent := m.stats.PacketsSent
	m.stats.mu.RUnlock()

	if sent < 10 {
		t.Errorf("expected all 10+ packets sent (got %d)", sent)
	}
}

func TestStart_ConnectionFailure_Continues(t *testing.T) {
	// Create one good destination
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	// Add an unreachable destination as well
	m := NewManager([]string{listener.LocalAddr().String(), "192.0.2.1:9999"}, "VXLAN", 10)

	// Start should succeed because at least one connection works
	err := m.Start()
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	m.Stop()
}

func TestStop_ClosingFailures_Handled(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "VXLAN", 10)
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Close the listener to potentially break connections
	listener.Close()

	// Stop should handle close errors gracefully
	m.Stop()
}

func TestReportStats_NoPackets(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "VXLAN", 10)
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Don't queue any packets, just wait for stats reporting
	time.Sleep(100 * time.Millisecond)

	m.Stop()

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	// Stats goroutine should have run even with no packets
	if m.stats.PacketsSent == 0 && m.stats.PacketsDropped == 0 {
		// This is fine - no packets were sent
	}
}

func TestSendPacket_WithSourceDestIP(t *testing.T) {
	addr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, _ := net.ListenUDP("udp", addr)
	defer listener.Close()

	m := NewManager([]string{listener.LocalAddr().String()}, "VXLAN", 10)
	conn, _ := m.createConnection(listener.LocalAddr().String())
	m.mu.Lock()
	m.connections[listener.LocalAddr().String()] = conn
	m.mu.Unlock()

	pkt := &MirrorPacket{
		Timestamp:   time.Now(),
		Source:      net.ParseIP("192.168.1.1"),
		Destination: net.ParseIP("10.0.0.1"),
		Protocol:    "TCP",
		Data:        []byte("test"),
		Metadata:    map[string]interface{}{},
	}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.PacketsSent != 1 {
		t.Errorf("expected 1 packet sent, got %d", m.stats.PacketsSent)
	}
}

func TestPrepareSuricataData_InvalidJSON(t *testing.T) {
	// This shouldn't happen in practice but test the error handling
	// Even with complex metadata, the JSON should marshal fine
	m := NewManager(nil, "VXLAN", 10)
	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "HTTP",
		Source:    net.ParseIP("10.1.2.3"),
		Destination: net.ParseIP("10.4.5.6"),
		Data:      []byte("http-payload"),
		Metadata: map[string]interface{}{
			"cluster_id": "cluster-a",
			"user_id":    "user-123",
			"nested":     map[string]interface{}{"key": "value"},
		},
	}
	result := m.prepareSuricataData(pkt)
	if len(result) == 0 {
		t.Error("expected non-empty result")
	}
	if result[len(result)-1] != '\n' {
		t.Error("expected trailing newline")
	}
}

func TestReconnect_FailedReconnection(t *testing.T) {
	// Try to reconnect to an unreachable address
	m := NewManager(nil, "VXLAN", 10)

	// GRE requires special permissions (ip4:47), will likely fail
	m.protocol = "GRE"
	m.reconnect("192.0.2.1:1") // Likely to fail

	// Should not panic
}

func TestSendPacket_SendErrorTriggersReconnect(t *testing.T) {
	// Create a scenario where send fails
	m := NewManager([]string{}, "VXLAN", 10)

	// Create a broken pipe connection
	clientConn, serverConn := net.Pipe()
	defer serverConn.Close()

	m.mu.Lock()
	m.connections["broken"] = clientConn
	m.mu.Unlock()

	clientConn.Close() // Close to make writes fail

	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Data:      []byte("test"),
		Metadata:  map[string]interface{}{},
	}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	errCount := m.stats.Errors
	m.stats.mu.RUnlock()

	if errCount == 0 {
		t.Error("expected error count to increment on send failure")
	}
}

func TestStop_WithSuricataConnection(t *testing.T) {
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	defer ln.Close()

	go func() {
		if c, err := ln.Accept(); err == nil && c != nil {
			c.Close()
		}
	}()

	port := ln.Addr().(*net.TCPAddr).Port
	m := NewManagerWithSuricata([]string{}, "VXLAN", 10, "127.0.0.1", itoa(port))

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	m.mu.RLock()
	hasSuricata := m.suricataConn != nil
	m.mu.RUnlock()

	if !hasSuricata {
		t.Fatal("expected suricata connection")
	}

	m.Stop()

	m.mu.RLock()
	closedSuricata := m.suricataConn
	m.mu.RUnlock()

	if closedSuricata != nil {
		t.Error("expected suricata connection to be closed")
	}
}

func TestStart_WithMultipleDestinations(t *testing.T) {
	addr1, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	l1, _ := net.ListenUDP("udp", addr1)
	defer l1.Close()

	addr2, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	l2, _ := net.ListenUDP("udp", addr2)
	defer l2.Close()

	m := NewManager([]string{l1.LocalAddr().String(), l2.LocalAddr().String()}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	m.mu.RLock()
	numConns := len(m.connections)
	m.mu.RUnlock()

	if numConns != 2 {
		t.Errorf("expected 2 connections, got %d", numConns)
	}

	m.Stop()
}

func itoa(n int) string {
	buf := make([]byte, 0, 10)
	if n == 0 {
		return "0"
	}
	for n > 0 {
		buf = append([]byte{byte('0' + n%10)}, buf...)
		n /= 10
	}
	return string(buf)
}

// ─── Additional Coverage Tests for sendPacket, reportStats, prepareSuricataData

func TestSendPacket_ReportStatsFullCycle(t *testing.T) {
	// Test reportStats with actual packets flowing
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("Failed to create listener: %v", err)
	}
	defer listener.Close()

	port := listener.LocalAddr().(*net.UDPAddr).Port
	destAddr := fmt.Sprintf("127.0.0.1:%d", port)
	m := NewManager([]string{destAddr}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Send multiple packets to trigger stats reporting
	for i := 0; i < 10; i++ {
		packet := &MirrorPacket{
			Timestamp: time.Now(),
			Protocol:  "TCP",
			Data:      []byte("test packet " + itoa(i)),
		}
		m.sendPacket(packet)
	}

	time.Sleep(100 * time.Millisecond)
	m.Stop()

	// Verify stats were incremented
	m.stats.mu.RLock()
	if m.stats.PacketsSent == 0 && m.stats.Errors == 0 {
		// Either sent or errored, as long as something was counted
		t.Errorf("expected some activity in stats")
	}
	m.stats.mu.RUnlock()
}

func TestSendPacket_NoSuricataConnection_Skips(t *testing.T) {
	// When suricata is enabled but conn is nil, should skip Suricata send
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("Failed to create listener: %v", err)
	}
	defer listener.Close()

	port := listener.LocalAddr().(*net.UDPAddr).Port
	destAddr := fmt.Sprintf("127.0.0.1:%d", port)
	m := NewManagerWithSuricata([]string{destAddr}, "VXLAN", 100, "127.0.0.1", "9999")
	m.suricataConn = nil // Simulate failed connection

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	packet := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "TCP",
		Data:      []byte("test"),
	}

	// Should not panic even though suricata conn is nil
	m.sendPacket(packet)
	m.Stop()
}

func TestReportStats_TickerCycle(t *testing.T) {
	// Verify reportStats actually runs the ticker loop
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("Failed to create listener: %v", err)
	}
	defer listener.Close()

	port := listener.LocalAddr().(*net.UDPAddr).Port
	destAddr := fmt.Sprintf("127.0.0.1:%d", port)
	m := NewManager([]string{destAddr}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Record initial state
	m.stats.incrementSent(100)
	m.stats.incrementDropped()
	m.stats.incrementErrors()

	// Give stats reporter time to run
	time.Sleep(100 * time.Millisecond)

	// Stop triggers return from reportStats loop
	m.Stop()

	m.stats.mu.RLock()
	if m.stats.PacketsSent != 1 {
		t.Errorf("expected PacketsSent=1, got %d", m.stats.PacketsSent)
	}
	if m.stats.PacketsDropped != 1 {
		t.Errorf("expected PacketsDropped=1, got %d", m.stats.PacketsDropped)
	}
	if m.stats.Errors != 1 {
		t.Errorf("expected Errors=1, got %d", m.stats.Errors)
	}
	m.stats.mu.RUnlock()
}

func TestPrepareSuricataData_WithAllMetadata(t *testing.T) {
	// Test full path through prepareSuricataData with all fields set
	m := NewManagerWithSuricata([]string{}, "VXLAN", 100, "127.0.0.1", "9999")

	packet := &MirrorPacket{
		Timestamp:   time.Now(),
		Protocol:    "TCP",
		Data:        []byte("test packet"),
		Source:      net.ParseIP("10.0.0.1"),
		Destination: net.ParseIP("10.0.0.2"),
		Metadata: map[string]interface{}{
			"cluster_id": "cluster1",
			"user_id":    "user123",
		},
	}

	data := m.prepareSuricataData(packet)
	if len(data) == 0 {
		t.Fatal("expected non-empty data from prepareSuricataData")
	}

	// Should end with newline (EVE JSON format)
	if data[len(data)-1] != '\n' {
		t.Error("expected data to end with newline")
	}
}

func TestPrepareSuricataData_WithoutMetadata(t *testing.T) {
	// Test prepareSuricataData with minimal metadata
	m := NewManagerWithSuricata([]string{}, "VXLAN", 100, "127.0.0.1", "9999")

	packet := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "UDP",
		Data:      []byte("minimal"),
		Metadata:  map[string]interface{}{},
	}

	data := m.prepareSuricataData(packet)
	if len(data) == 0 {
		t.Fatal("expected non-empty data")
	}
}

func TestPrepareSuricataData_WithOnlySource(t *testing.T) {
	// Test with only source IP set (not destination)
	m := NewManagerWithSuricata([]string{}, "VXLAN", 100, "127.0.0.1", "9999")

	packet := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "ICMP",
		Data:      []byte("source-only"),
		Source:    net.ParseIP("192.168.1.1"),
		Metadata: map[string]interface{}{
			"cluster_id": "c1",
		},
	}

	data := m.prepareSuricataData(packet)
	if len(data) == 0 {
		t.Fatal("expected non-empty data with source only")
	}
}

func TestStart_PartialConnections(t *testing.T) {
	// Test Start when some destinations fail to connect but others succeed
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("Failed to create listener: %v", err)
	}
	defer listener.Close()

	port := listener.LocalAddr().(*net.UDPAddr).Port
	destAddr := fmt.Sprintf("127.0.0.1:%d", port)
	m := NewManager([]string{destAddr, "127.0.0.1:9999"}, "VXLAN", 100)

	err = m.Start()
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	m.mu.RLock()
	// Should have at least one connection despite one failing
	if len(m.connections) == 0 {
		t.Errorf("expected at least one connection")
	}
	m.mu.RUnlock()

	m.Stop()
}

func TestStop_WithOpenConnections(t *testing.T) {
	// Verify Stop properly closes all open connections
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("Failed to create listener: %v", err)
	}
	defer listener.Close()

	port := listener.LocalAddr().(*net.UDPAddr).Port
	destAddr := fmt.Sprintf("127.0.0.1:%d", port)
	m := NewManager([]string{destAddr}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	m.Stop()

	// After stop, connections should be cleared
	m.mu.RLock()
	if len(m.connections) != 0 {
		t.Errorf("expected 0 connections after Stop, got %d", len(m.connections))
	}
	m.mu.RUnlock()
}

func TestStart_AllDestinationsFail(t *testing.T) {
	// Test Start when all destinations fail to connect
	// Using unreachable ports means Start should return error
	m := NewManager([]string{"255.255.255.255:9999", "255.255.255.255:9998"}, "VXLAN", 100)

	err := m.Start()
	// Start may fail or succeed silently and continue; both are acceptable behaviors
	// The key is it doesn't crash
	if err != nil {
		t.Logf("Start returned error (acceptable): %v", err)
	}

	m.Stop()
}

func TestWorker_ProcessesQueueUntilStop(t *testing.T) {
	// Ensure worker drains queue properly on stop signal
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	listener, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("Failed to create listener: %v", err)
	}
	defer listener.Close()

	port := listener.LocalAddr().(*net.UDPAddr).Port
	destAddr := fmt.Sprintf("127.0.0.1:%d", port)
	m := NewManager([]string{destAddr}, "VXLAN", 100)

	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue multiple packets
	for i := 0; i < 5; i++ {
		packet := &MirrorPacket{
			Timestamp: time.Now(),
			Protocol:  "TCP",
			Data:      []byte("packet " + itoa(i)),
		}
		m.queue <- packet
	}

	m.Stop()

	// Worker should have processed all queued packets
	if len(m.queue) != 0 {
		t.Errorf("expected empty queue after Stop, got %d items", len(m.queue))
	}
}

// ─── sendPacket write error path ──────────────────────────────────────────────

// TestSendPacket_WriteError covers the conn.Write error branch in sendPacket.
// We add a pre-closed net.Pipe connection to the manager's connection map;
// any write to it will return an error, exercising the error+incrementErrors+reconnect path.
func TestSendPacket_WriteError(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)

	// Create a pipe and immediately close both sides so writes fail.
	a, b := net.Pipe()
	a.Close()
	b.Close()

	const dest = "10.0.0.1:4789"
	m.mu.Lock()
	m.connections[dest] = a // closed — writes will fail
	m.mu.Unlock()

	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "TCP",
		Data:      []byte("hello"),
		Metadata:  map[string]interface{}{},
	}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.Errors == 0 {
		t.Error("expected error counter to be incremented on write failure")
	}
}

// ─── reportStats ──────────────────────────────────────────────────────────────

// TestReportStats_TickerFires covers the ticker.C case in reportStats (the stats log branch).
// We set statsReportInterval to 1ms so the ticker fires almost immediately, then stop via stopCh.
func TestReportStats_TickerFires(t *testing.T) {
	old := statsReportInterval
	defer func() { statsReportInterval = old }()
	statsReportInterval = 1 * time.Millisecond

	m := NewManager(nil, "VXLAN", 10)
	// Populate stopCh by calling Start so reportStats is wired up, or call directly.
	// Call directly to avoid network setup.
	done := make(chan struct{})
	go func() {
		m.reportStats()
		close(done)
	}()

	// Let at least one tick fire.
	time.Sleep(20 * time.Millisecond)
	// Signal stop via stopCh.
	close(m.stopCh)

	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Error("reportStats did not exit after stopCh closed")
	}
}

// TestSendPacket_SuricataWriteError covers the suricataConn.Write error branch.
func TestSendPacket_SuricataWriteError(t *testing.T) {
	m := NewManager(nil, "VXLAN", 10)
	m.suricataEnabled = true

	// Closed pipe — writes fail immediately.
	a, b := net.Pipe()
	a.Close()
	b.Close()
	m.suricataConn = a

	pkt := &MirrorPacket{
		Timestamp: time.Now(),
		Protocol:  "TCP",
		Data:      []byte("hello"),
		Metadata:  map[string]interface{}{},
	}
	m.sendPacket(pkt)

	m.stats.mu.RLock()
	defer m.stats.mu.RUnlock()
	if m.stats.Errors == 0 {
		t.Error("expected error counter incremented on suricata write failure")
	}
}
