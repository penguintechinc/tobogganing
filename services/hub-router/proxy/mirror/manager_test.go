package mirror

import (
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

// ─── helper ──────────────────────────────────────────────────────────────────

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
