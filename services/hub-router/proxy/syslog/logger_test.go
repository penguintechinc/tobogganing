package syslog

import (
	"net"
	"strconv"
	"strings"
	"testing"
	"time"
)

// ─── NewSyslogLogger ──────────────────────────────────────────────────────────

func TestNewSyslogLogger_Enabled(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	if l == nil {
		t.Fatal("expected non-nil logger")
	}
	if !l.IsEnabled() {
		t.Error("expected enabled=true when host is set")
	}
	if l.syslogHost != "127.0.0.1" {
		t.Errorf("unexpected syslogHost: %s", l.syslogHost)
	}
	if l.syslogPort != "514" {
		t.Errorf("unexpected syslogPort: %s", l.syslogPort)
	}
	if l.facility != FacilityLocal0 {
		t.Errorf("unexpected facility: %d", l.facility)
	}
	if l.severity != SeverityInformational {
		t.Errorf("unexpected severity: %d", l.severity)
	}
	if l.appName != "tobogganing-hub-router" {
		t.Errorf("unexpected appName: %s", l.appName)
	}
	if cap(l.logQueue) != 1000 {
		t.Errorf("unexpected queue capacity: %d", cap(l.logQueue))
	}
	if l.workers != 3 {
		t.Errorf("unexpected workers: %d", l.workers)
	}
}

func TestNewSyslogLogger_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514")
	if l.IsEnabled() {
		t.Error("expected disabled when host is empty")
	}
}

// ─── IsEnabled / GetQueueDepth ────────────────────────────────────────────────

func TestIsEnabled(t *testing.T) {
	enabled := NewSyslogLogger("host", "514")
	disabled := NewSyslogLogger("", "514")
	if !enabled.IsEnabled() {
		t.Error("expected true for non-empty host")
	}
	if disabled.IsEnabled() {
		t.Error("expected false for empty host")
	}
}

func TestGetQueueDepth_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514")
	if l.GetQueueDepth() != 0 {
		t.Error("disabled logger should always return queue depth 0")
	}
}

func TestGetQueueDepth_Empty(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	if l.GetQueueDepth() != 0 {
		t.Error("expected queue depth 0 for empty queue")
	}
}

// ─── LogAccess – disabled ──────────────────────────────────────────────────────

func TestLogAccess_Disabled_NoOp(t *testing.T) {
	l := NewSyslogLogger("", "514")
	// Should be a no-op
	l.LogAccess(AccessLog{UserID: "user1", TargetHost: "example.com"})
	if l.GetQueueDepth() != 0 {
		t.Error("disabled logger should not queue access logs")
	}
}

// ─── LogAccess – enabled (with real UDP server) ────────────────────────────────

func TestLogAccess_Enabled_Queued(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514") // enabled but not connected
	// Manually add to queue to test without actual UDP connection
	l.LogAccess(AccessLog{
		UserID:     "user1",
		TargetHost: "example.com",
		Action:     "allow",
	})
	if l.GetQueueDepth() != 1 {
		t.Errorf("expected queue depth 1, got %d", l.GetQueueDepth())
	}
}

func TestLogAccess_SetsTimestamp(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	before := time.Now()
	l.LogAccess(AccessLog{UserID: "user1"})
	after := time.Now()

	if l.GetQueueDepth() != 1 {
		t.Fatalf("expected queue depth 1, got %d", l.GetQueueDepth())
	}
	pkt := <-l.logQueue
	if pkt.Timestamp.Before(before) || pkt.Timestamp.After(after) {
		t.Errorf("timestamp not in expected range: %v", pkt.Timestamp)
	}
}

func TestLogAccess_PreservesExistingTimestamp(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	fixedTime := time.Date(2024, 1, 15, 10, 0, 0, 0, time.UTC)
	l.LogAccess(AccessLog{
		UserID:    "user1",
		Timestamp: fixedTime,
	})

	pkt := <-l.logQueue
	if !pkt.Timestamp.Equal(fixedTime) {
		t.Errorf("expected fixed timestamp, got %v", pkt.Timestamp)
	}
}

func TestLogAccess_QueueFull_Drops(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	// Manually fill the queue to capacity
	for i := 0; i < 1000; i++ {
		l.logQueue <- AccessLog{}
	}

	// This should drop rather than block
	done := make(chan struct{})
	go func() {
		l.LogAccess(AccessLog{UserID: "overflow"})
		close(done)
	}()

	select {
	case <-done:
		// good, did not block
	case <-time.After(time.Second):
		t.Error("LogAccess blocked on full queue")
	}

	// Drain the queue
	for len(l.logQueue) > 0 {
		<-l.logQueue
	}
}

// ─── LogHTTPAccess ────────────────────────────────────────────────────────────

func TestLogHTTPAccess_Allow(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogHTTPAccess("user1", "alice", "192.168.1.1", "example.com", "GET", "/path", "curl/7.0", "req-1", 200, 1024, true)

	if l.GetQueueDepth() != 1 {
		t.Fatalf("expected queue depth 1, got %d", l.GetQueueDepth())
	}
	pkt := <-l.logQueue
	if pkt.Action != "allow" {
		t.Errorf("expected allow, got %s", pkt.Action)
	}
	if pkt.Protocol != "HTTP" {
		t.Errorf("expected HTTP, got %s", pkt.Protocol)
	}
	if pkt.Method != "GET" {
		t.Errorf("expected GET, got %s", pkt.Method)
	}
	if pkt.StatusCode != 200 {
		t.Errorf("expected 200, got %d", pkt.StatusCode)
	}
	if pkt.BytesSent != 1024 {
		t.Errorf("expected 1024, got %d", pkt.BytesSent)
	}
}

func TestLogHTTPAccess_Deny(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogHTTPAccess("user1", "alice", "192.168.1.1", "blocked.com", "POST", "/api", "curl/7.0", "req-2", 403, 0, false)

	pkt := <-l.logQueue
	if pkt.Action != "deny" {
		t.Errorf("expected deny, got %s", pkt.Action)
	}
}

// ─── LogTCPAccess ─────────────────────────────────────────────────────────────

func TestLogTCPAccess_Allow(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogTCPAccess("user1", "alice", "192.168.1.1", "10.0.0.1:22", true)

	pkt := <-l.logQueue
	if pkt.Action != "allow" {
		t.Errorf("expected allow, got %s", pkt.Action)
	}
	if pkt.Protocol != "TCP" {
		t.Errorf("expected TCP, got %s", pkt.Protocol)
	}
}

func TestLogTCPAccess_Deny(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogTCPAccess("user1", "alice", "192.168.1.1", "10.0.0.1:22", false)

	pkt := <-l.logQueue
	if pkt.Action != "deny" {
		t.Errorf("expected deny, got %s", pkt.Action)
	}
}

// ─── LogUDPAccess ─────────────────────────────────────────────────────────────

func TestLogUDPAccess_Allow(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogUDPAccess("user1", "alice", "192.168.1.1", "10.0.0.1:53", true)

	pkt := <-l.logQueue
	if pkt.Action != "allow" {
		t.Errorf("expected allow, got %s", pkt.Action)
	}
	if pkt.Protocol != "UDP" {
		t.Errorf("expected UDP, got %s", pkt.Protocol)
	}
}

func TestLogUDPAccess_Deny(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogUDPAccess("user1", "alice", "192.168.1.1", "10.0.0.1:53", false)

	pkt := <-l.logQueue
	if pkt.Action != "deny" {
		t.Errorf("expected deny, got %s", pkt.Action)
	}
}

// ─── sendLog ─────────────────────────────────────────────────────────────────

func TestSendLog_NoConnection(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	// conn is nil
	err := l.sendLog(AccessLog{UserID: "test", Timestamp: time.Now()})
	if err == nil {
		t.Error("expected error when no syslog connection")
	}
}

func TestSendLog_WithRealUDP(t *testing.T) {
	// Create a real UDP listener to receive syslog messages
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("failed to create UDP server: %v", err)
	}
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port

	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.connect(); err != nil {
		t.Fatalf("failed to connect: %v", err)
	}
	defer l.conn.Close()

	accessLog := AccessLog{
		Timestamp:  time.Now().UTC(),
		UserID:     "user-123",
		Username:   "alice",
		SourceIP:   "192.168.1.1",
		TargetHost: "example.com",
		Protocol:   "HTTP",
		Action:     "allow",
	}

	if err := l.sendLog(accessLog); err != nil {
		t.Fatalf("unexpected error sending log: %v", err)
	}

	// Read from server
	buf := make([]byte, 4096)
	_ = server.SetReadDeadline(time.Now().Add(time.Second))
	n, _, err := server.ReadFromUDP(buf)
	if err != nil {
		t.Fatalf("failed to read UDP data: %v", err)
	}

	msg := string(buf[:n])
	// Verify RFC3164 format: starts with <priority>
	if !strings.HasPrefix(msg, "<") {
		t.Errorf("expected RFC3164 format starting with <, got: %s", msg[:min(20, len(msg))])
	}
	// Verify contains app name
	if !strings.Contains(msg, "tobogganing-hub-router") {
		t.Error("expected app name in syslog message")
	}
	// Verify contains user ID
	if !strings.Contains(msg, "user-123") {
		t.Error("expected user ID in syslog message")
	}
	// Verify priority calculation (facility 16 * 8 + severity 6 = 134)
	if !strings.HasPrefix(msg, "<134>") {
		t.Errorf("expected priority 134, got message: %s", msg[:min(10, len(msg))])
	}
}

// ─── Start/Stop with real UDP server ─────────────────────────────────────────

func TestStart_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514")
	if err := l.Start(); err != nil {
		t.Fatalf("unexpected error for disabled logger: %v", err)
	}
}

func TestStart_Enabled_Success(t *testing.T) {
	// Set up a real UDP listener
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("failed to create UDP server: %v", err)
	}
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Send a log to exercise the worker
	l.LogAccess(AccessLog{
		UserID:    "test-user",
		Timestamp: time.Now().UTC(),
	})

	// Give worker time to process
	time.Sleep(100 * time.Millisecond)

	// Stop
	done := make(chan struct{})
	go func() {
		l.Stop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Error("Stop timed out")
	}
}

func TestStop_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514")
	// Should be a no-op
	l.Stop()
}

// ─── Constants ───────────────────────────────────────────────────────────────

func TestFacilityConstants(t *testing.T) {
	if FacilityLocal0 != 16 {
		t.Errorf("unexpected FacilityLocal0: %d", FacilityLocal0)
	}
	if FacilityLocal7 != 23 {
		t.Errorf("unexpected FacilityLocal7: %d", FacilityLocal7)
	}
}

func TestSeverityConstants(t *testing.T) {
	if SeverityEmergency != 0 {
		t.Errorf("unexpected SeverityEmergency: %d", SeverityEmergency)
	}
	if SeverityDebug != 7 {
		t.Errorf("unexpected SeverityDebug: %d", SeverityDebug)
	}
	if SeverityInformational != 6 {
		t.Errorf("unexpected SeverityInformational: %d", SeverityInformational)
	}
}

// ─── getCurrentHostname ───────────────────────────────────────────────────────

func TestGetCurrentHostname_ReturnsSomething(t *testing.T) {
	hostname, _ := getCurrentHostname()
	if hostname == "" {
		t.Error("expected non-empty hostname")
	}
}

// ─── helpers ──────────────────────────────────────────────────────────────────

func itoa(n int) string {
	return strconv.Itoa(n)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
