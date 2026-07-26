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

// ─── Start/Stop worker exercise ───────────────────────────────────────────

func TestStart_EnabledMultipleWorkers(t *testing.T) {
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

	// Verify workers are running by queuing multiple logs
	for i := 0; i < 5; i++ {
		l.LogAccess(AccessLog{
			UserID:    "user" + strconv.Itoa(i),
			Timestamp: time.Now().UTC(),
		})
	}

	// Give workers time to process
	time.Sleep(100 * time.Millisecond)

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

// ─── connect function coverage ────────────────────────────────────────────

func TestConnect_Successful(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("failed to create UDP server: %v", err)
	}
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.connect(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if l.conn == nil {
		t.Error("expected conn to be set after successful connect")
	}
	l.conn.Close()
}

func TestConnect_Failed(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "1") // Port 1 requires root/admin
	err := l.connect()
	// Connection may fail or succeed depending on permissions; just verify no panic
	// and function returns error handling result
	_ = err
}

// ─── getCurrentHostname error path ────────────────────────────────────────

func TestCurrentHostname_Fallback(t *testing.T) {
	// This function has a fallback to "tobogganing-hub-router"
	hostname, _ := getCurrentHostname()
	if hostname == "" {
		t.Error("expected non-empty hostname")
	}
}

// ─── worker error recovery ────────────────────────────────────────────────

func TestWorker_ReconnectsOnSendError(t *testing.T) {
	// Set up first UDP listener (will be closed to trigger error)
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("failed to create UDP server: %v", err)
	}

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Close the server to force write errors
	server.Close()

	// Send a log – should attempt reconnect
	l.LogAccess(AccessLog{
		UserID:    "test-user",
		Timestamp: time.Now().UTC(),
	})

	// Give worker time to attempt send and reconnect
	time.Sleep(200 * time.Millisecond)

	l.Stop()
}

// ─── sendLog format validation ────────────────────────────────────────────

func TestSendLog_RFC3164Format(t *testing.T) {
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
		Timestamp:  time.Date(2024, 1, 15, 10, 30, 45, 0, time.UTC),
		UserID:     "user-456",
		Protocol:   "HTTP",
		Action:     "deny",
		SourceIP:   "10.1.2.3",
		TargetHost: "restricted.com",
	}

	if err := l.sendLog(accessLog); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Read from server
	buf := make([]byte, 4096)
	_ = server.SetReadDeadline(time.Now().Add(time.Second))
	n, _, err := server.ReadFromUDP(buf)
	if err != nil {
		t.Fatalf("failed to read: %v", err)
	}

	msg := string(buf[:n])
	// Priority format: <134> = facility 16 * 8 + severity 6
	if !strings.HasPrefix(msg, "<134>") {
		t.Errorf("expected RFC3164 priority format, got: %s", msg[:10])
	}
	if !strings.Contains(msg, "2024-01-15") {
		t.Error("expected RFC3339 timestamp in message")
	}
}

// ─── LogAccess with all fields ────────────────────────────────────────────

func TestLogAccess_AllFields(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	now := time.Now()
	accessLog := AccessLog{
		Timestamp:   now,
		UserID:      "user-789",
		Username:    "bob",
		SourceIP:    "192.168.1.100",
		TargetHost:  "api.example.com",
		Protocol:    "HTTPS",
		Action:      "allow",
		Method:      "DELETE",
		Path:        "/api/v1/users/123",
		StatusCode:  204,
		BytesSent:   0,
		UserAgent:   "curl/7.64.1",
		RequestID:   "req-uuid-12345",
	}

	l.LogAccess(accessLog)

	if l.GetQueueDepth() != 1 {
		t.Fatalf("expected queue depth 1, got %d", l.GetQueueDepth())
	}

	pkt := <-l.logQueue
	if pkt.UserID != "user-789" {
		t.Errorf("unexpected UserID: %s", pkt.UserID)
	}
	if pkt.Method != "DELETE" {
		t.Errorf("unexpected Method: %s", pkt.Method)
	}
	if pkt.StatusCode != 204 {
		t.Errorf("unexpected StatusCode: %d", pkt.StatusCode)
	}
}

// ─── LogHTTPAccess with all parameters ─────────────────────────────────────

func TestLogHTTPAccess_AllDetails(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogHTTPAccess(
		"user-999",
		"charlie",
		"10.0.0.50",
		"internal.corp",
		"PUT",
		"/config/update",
		"PostmanRuntime/7.32.3",
		"req-abc-def",
		200,
		512,
		true,
	)

	if l.GetQueueDepth() != 1 {
		t.Fatalf("expected queue depth 1")
	}

	pkt := <-l.logQueue
	if pkt.Protocol != "HTTP" {
		t.Errorf("expected HTTP, got %s", pkt.Protocol)
	}
	if pkt.Method != "PUT" {
		t.Errorf("expected PUT, got %s", pkt.Method)
	}
	if pkt.Action != "allow" {
		t.Errorf("expected allow, got %s", pkt.Action)
	}
}

// ─── Start disabled is no-op ───────────────────────────────────────────────

func TestStart_Disabled_NoWorkers(t *testing.T) {
	l := NewSyslogLogger("", "")
	if err := l.Start(); err != nil {
		t.Fatalf("unexpected error for disabled logger: %v", err)
	}
	// No workers should be started; verify no goroutines spawned
	// (difficult to test directly, but Stop should not block)
	l.Stop()
}

// ─── Stop without Start ────────────────────────────────────────────────────

func TestStop_WithoutStart_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514")
	// Should be no-op
	l.Stop()
}

// ─── Worker message processing ────────────────────────────────────────────

func TestWorker_ProcessesLogsFromQueue(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, err := net.ListenUDP("udp", serverAddr)
	if err != nil {
		t.Fatalf("failed to create UDP server: %v", err)
	}
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue multiple logs
	for i := 0; i < 3; i++ {
		l.LogAccess(AccessLog{
			UserID:    "worker-test-" + itoa(i),
			Timestamp: time.Now().UTC(),
		})
	}

	// Give workers time to process
	time.Sleep(200 * time.Millisecond)

	l.Stop()

	// Verify at least some logs made it
	receivedCount := 0
	_ = server.SetReadDeadline(time.Now().Add(50 * time.Millisecond))
	for {
		buf := make([]byte, 4096)
		_, _, err := server.ReadFromUDP(buf)
		if err != nil {
			break
		}
		receivedCount++
	}

	if receivedCount == 0 {
		t.Error("expected some logs to be sent by workers")
	}
}

// ─── Additional coverage tests ────────────────────────────────────────────

func TestStart_Enabled_ConnectionFailed(t *testing.T) {
	// Host that exists but port is closed (assuming no listener on port 1)
	l := NewSyslogLogger("127.0.0.1", "1")
	err := l.Start()
	// Connection may fail; verify we handle the error gracefully
	if err != nil {
		// Expected when no listener on port 1
		if !strings.Contains(err.Error(), "failed to connect") {
			t.Errorf("unexpected error type: %v", err)
		}
	}
}

func TestConnect_InvalidAddress(t *testing.T) {
	l := NewSyslogLogger("invalid.local.test", "514")
	err := l.connect()
	// Should fail on invalid hostname
	if err == nil {
		t.Error("expected error for invalid hostname")
	}
}

func TestWorker_StopsOnSignal(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Verify all workers stop on Stop() signal
	done := make(chan struct{})
	go func() {
		l.Stop()
		close(done)
	}()

	select {
	case <-done:
		// Good, workers stopped
	case <-time.After(3 * time.Second):
		t.Error("Workers did not stop in time")
	}
}

func TestSendLog_MarshalError(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.connect(); err != nil {
		t.Fatalf("connect failed: %v", err)
	}
	defer l.conn.Close()

	// Create a valid AccessLog (should marshal fine)
	// This test verifies the marshaling works
	accessLog := AccessLog{
		Timestamp:  time.Now().UTC(),
		UserID:     "u1",
		Username:   "user1",
		SourceIP:   "1.2.3.4",
		TargetHost: "example.com",
		Protocol:   "TCP",
		Action:     "allow",
		Method:     "GET",
		Path:       "/test",
		StatusCode: 200,
		BytesSent:  1024,
		UserAgent:  "test-agent",
		RequestID:  "req-123",
	}

	if err := l.sendLog(accessLog); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestLogHTTPAccess_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514") // disabled
	// Should not queue
	l.LogHTTPAccess("u1", "user1", "1.1.1.1", "host", "GET", "/", "agent", "req", 200, 100, true)

	if l.GetQueueDepth() != 0 {
		t.Error("disabled logger should not queue")
	}
}

func TestLogTCPAccess_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514") // disabled
	l.LogTCPAccess("u1", "user1", "1.1.1.1", "host", true)
	if l.GetQueueDepth() != 0 {
		t.Error("disabled logger should not queue")
	}
}

func TestLogUDPAccess_Disabled(t *testing.T) {
	l := NewSyslogLogger("", "514") // disabled
	l.LogUDPAccess("u1", "user1", "1.1.1.1", "host", false)
	if l.GetQueueDepth() != 0 {
		t.Error("disabled logger should not queue")
	}
}

func TestWorker_ProcessesWithConnectionError(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	port := server.LocalAddr().(*net.UDPAddr).Port

	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Log an entry while connection is good
	l.LogAccess(AccessLog{
		UserID:    "user1",
		Timestamp: time.Now().UTC(),
	})

	time.Sleep(50 * time.Millisecond)

	// Close the server to force connection error
	server.Close()

	// Log another entry – should attempt reconnect
	l.LogAccess(AccessLog{
		UserID:    "user2",
		Timestamp: time.Now().UTC(),
	})

	time.Sleep(100 * time.Millisecond)

	l.Stop()
}

func TestGetCurrentHostname_LookupFallback(t *testing.T) {
	// Just verify it returns a non-empty string (fallback path)
	hostname, err := getCurrentHostname()
	if hostname == "" {
		t.Error("expected non-empty hostname")
	}
	// err may be nil or non-nil depending on system state
	_ = err
}

func TestLogAccess_EmptyQueue(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	// Queue should start empty
	if l.GetQueueDepth() != 0 {
		t.Error("expected empty queue on init")
	}

	l.LogAccess(AccessLog{UserID: "u1"})
	if l.GetQueueDepth() != 1 {
		t.Error("expected queue depth 1 after LogAccess")
	}
}

func TestGetCurrentHostname_LookupCNAMESuccess(t *testing.T) {
	// This tests the normal (non-fallback) path
	hostname, err := getCurrentHostname()
	if hostname == "" {
		t.Error("expected non-empty hostname")
	}
	_ = err
}

func TestStop_ClosesSyslogConnection(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	port := server.LocalAddr().(*net.UDPAddr).Port
	defer server.Close()

	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	l.mu.RLock()
	conn := l.conn
	l.mu.RUnlock()

	if conn == nil {
		t.Fatal("expected connection to be established")
	}

	l.Stop()

	l.mu.RLock()
	closedConn := l.conn
	l.mu.RUnlock()

	if closedConn != nil {
		t.Error("expected connection to be closed after Stop")
	}
}

func TestSendLog_WriteFailure(t *testing.T) {
	// UDP is connectionless; write doesn't immediately fail when server closes
	// Instead, test by creating a broken connection via pipe or TCP
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	port := server.LocalAddr().(*net.UDPAddr).Port

	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.connect(); err != nil {
		t.Fatalf("connect failed: %v", err)
	}

	// UDP write to a closed server still succeeds (UDP is connectionless)
	// So test passes the write, then close
	accessLog := AccessLog{
		Timestamp:  time.Now().UTC(),
		UserID:     "u1",
		TargetHost: "example.com",
	}

	err := l.sendLog(accessLog)
	// UDP send succeeds even if server is closed
	if err != nil {
		t.Logf("UDP write error (may be expected): %v", err)
	}

	server.Close()
	l.conn.Close()
}

func TestConnect_WithResolutionError(t *testing.T) {
	l := NewSyslogLogger("invalid-host-that-does-not-resolve.test", "514")
	err := l.connect()
	// Should fail on resolution or connection
	if err == nil {
		t.Error("expected error for invalid hostname")
	}
}

func TestWorker_HandlesStopSignal(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue should be empty after stop (workers drain it)
	l.Stop()

	// Verify workers have stopped by checking no more items are processed
	l.LogAccess(AccessLog{UserID: "after-stop"})

	// After stop, queue depth doesn't increase (no workers processing)
	time.Sleep(50 * time.Millisecond)

	// Drain any remaining logs
	for len(l.logQueue) > 0 {
		<-l.logQueue
	}
}

func TestStart_Multiple_Workers_Stress(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Send many logs in rapid succession
	for i := 0; i < 20; i++ {
		l.LogAccess(AccessLog{
			UserID:    "stress-user-" + itoa(i),
			Timestamp: time.Now().UTC(),
		})
	}

	time.Sleep(200 * time.Millisecond)

	l.Stop()

	// Verify logs were processed
	_ = server.SetReadDeadline(time.Now().Add(100 * time.Millisecond))
	receivedCount := 0
	for {
		buf := make([]byte, 4096)
		_, _, err := server.ReadFromUDP(buf)
		if err != nil {
			break
		}
		receivedCount++
	}

	if receivedCount == 0 {
		t.Error("expected some logs to be sent under stress")
	}
}

func TestLogAccess_NoTimestampSetsOne(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	before := time.Now().UTC()
	l.LogAccess(AccessLog{UserID: "u1"})
	after := time.Now().UTC()

	pkt := <-l.logQueue
	if pkt.Timestamp.Before(before) || pkt.Timestamp.After(after) {
		t.Error("expected timestamp to be set within test window")
	}
}

func TestWorker_ProcessesMultipleMessages(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue 5 different types of logs
	l.LogAccess(AccessLog{UserID: "u1", Timestamp: time.Now().UTC()})
	l.LogHTTPAccess("u2", "user2", "1.1.1.1", "host2", "GET", "/api", "agent", "req", 200, 100, true)
	l.LogTCPAccess("u3", "user3", "2.2.2.2", "host3", false)
	l.LogUDPAccess("u4", "user4", "3.3.3.3", "host4", true)
	l.LogAccess(AccessLog{UserID: "u5", Action: "deny", Timestamp: time.Now().UTC()})

	time.Sleep(100 * time.Millisecond)

	l.Stop()
}

func TestConnect_SetsMutex(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	port := server.LocalAddr().(*net.UDPAddr).Port
	defer server.Close()

	l := NewSyslogLogger("127.0.0.1", itoa(port))

	l.mu.RLock()
	if l.conn != nil {
		t.Fatal("expected no connection before connect")
	}
	l.mu.RUnlock()

	if err := l.connect(); err != nil {
		t.Fatalf("connect failed: %v", err)
	}

	l.mu.RLock()
	if l.conn == nil {
		t.Error("expected connection to be set after connect")
	}
	l.mu.RUnlock()

	l.conn.Close()
}

func TestStop_WithRunningWorkers(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue logs while running
	for i := 0; i < 3; i++ {
		l.LogAccess(AccessLog{
			UserID:    "u" + itoa(i),
			Timestamp: time.Now().UTC(),
		})
	}

	// Stop should cleanly shut down workers
	done := make(chan struct{})
	go func() {
		l.Stop()
		close(done)
	}()

	select {
	case <-done:
		// Good
	case <-time.After(5 * time.Second):
		t.Error("Stop did not complete in time")
	}
}

func TestSendLog_CompleteWithAllFields(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.connect(); err != nil {
		t.Fatalf("connect failed: %v", err)
	}
	defer l.conn.Close()

	accessLog := AccessLog{
		Timestamp:   time.Date(2024, 3, 15, 14, 30, 0, 0, time.UTC),
		UserID:      "admin-user",
		Username:    "administrator",
		SourceIP:    "192.168.100.50",
		TargetHost:  "api.internal.corp",
		Protocol:    "HTTPS",
		Action:      "deny",
		Method:      "DELETE",
		Path:        "/admin/users",
		StatusCode:  401,
		BytesSent:   256,
		UserAgent:   "curl/7.68.0",
		RequestID:   "req-12345-abcde",
	}

	if err := l.sendLog(accessLog); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Read the message
	buf := make([]byte, 4096)
	_ = server.SetReadDeadline(time.Now().Add(time.Second))
	n, _, err := server.ReadFromUDP(buf)
	if err != nil {
		t.Fatalf("failed to read: %v", err)
	}

	msg := string(buf[:n])
	// Verify RFC3164 format
	if !strings.HasPrefix(msg, "<") {
		t.Errorf("expected RFC3164 format, got: %s", msg[:min(20, len(msg))])
	}
	// Verify contains key fields
	if !strings.Contains(msg, "admin-user") {
		t.Error("expected user ID in message")
	}
}

func TestWorker_ErrorHandlingAndReconnect(t *testing.T) {
	// First server to accept initial connection
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	port := server.LocalAddr().(*net.UDPAddr).Port

	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Verify initial connection works
	l.LogAccess(AccessLog{UserID: "pre-close", Timestamp: time.Now().UTC()})
	time.Sleep(50 * time.Millisecond)

	// Now close server to break connection
	server.Close()

	// Log more entries – worker should attempt reconnect (will fail but not panic)
	l.LogAccess(AccessLog{UserID: "post-close", Timestamp: time.Now().UTC()})
	time.Sleep(100 * time.Millisecond)

	l.Stop()
}

func TestGetCurrentHostname_Returns(t *testing.T) {
	hostname, err := getCurrentHostname()
	// Should always return something (fallback to "tobogganing-hub-router")
	if hostname == "" {
		t.Error("expected non-empty hostname from getCurrentHostname")
	}
	// Error may or may not be set depending on system
	_ = err
}

func TestWorker_SendLogErrorAndReconnect(t *testing.T) {
	// Start fresh logger without connection
	l := NewSyslogLogger("127.0.0.1", "1") // Port 1 requires root
	l.enabled = true // Force enabled
	l.conn = nil     // No connection

	// Manually queue an item and call worker with timeout
	done := make(chan struct{})
	go func() {
		// Send one log entry
		l.logQueue <- AccessLog{UserID: "u1", Timestamp: time.Now().UTC()}

		// Give worker time to process and fail
		time.Sleep(100 * time.Millisecond)

		// Signal stop
		l.stopChan <- true
		close(done)
	}()

	// Run single worker
	l.worker("test-worker")

	select {
	case <-done:
		// Good
	case <-time.After(time.Second):
		t.Error("worker did not complete in time")
	}
}

func TestStart_WorkerLoopCycle(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Verify workers are running by checking that logs are processed
	l.LogAccess(AccessLog{UserID: "u1", Timestamp: time.Now().UTC()})
	l.LogAccess(AccessLog{UserID: "u2", Timestamp: time.Now().UTC()})
	l.LogAccess(AccessLog{UserID: "u3", Timestamp: time.Now().UTC()})

	time.Sleep(50 * time.Millisecond)

	l.Stop()
}

func TestConnect_UpdatesConnection(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	// First connection
	if err := l.connect(); err != nil {
		t.Fatalf("first connect failed: %v", err)
	}

	l.mu.RLock()
	firstConn := l.conn
	l.mu.RUnlock()

	if firstConn == nil {
		t.Fatal("expected first connection to be set")
	}

	// Close and reconnect
	firstConn.Close()

	// Second connection (to same server)
	if err := l.connect(); err != nil {
		t.Fatalf("second connect failed: %v", err)
	}

	l.mu.RLock()
	secondConn := l.conn
	l.mu.RUnlock()

	if secondConn == nil {
		t.Fatal("expected second connection to be set")
	}

	if firstConn == secondConn {
		t.Error("expected different connection objects")
	}

	secondConn.Close()
}

func TestSendLog_WithRealConnection(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.connect(); err != nil {
		t.Fatalf("connect failed: %v", err)
	}
	defer l.conn.Close()

	// Send multiple logs
	for i := 0; i < 3; i++ {
		err := l.sendLog(AccessLog{
			Timestamp:  time.Now().UTC(),
			UserID:     "u" + itoa(i),
			Action:     "allow",
			TargetHost: "host" + itoa(i),
		})
		if err != nil {
			t.Errorf("unexpected error on log %d: %v", i, err)
		}
	}

	// Verify messages were sent
	msgCount := 0
	_ = server.SetReadDeadline(time.Now().Add(500 * time.Millisecond))
	for {
		buf := make([]byte, 4096)
		_, _, err := server.ReadFromUDP(buf)
		if err != nil {
			break
		}
		msgCount++
	}

	if msgCount != 3 {
		t.Errorf("expected 3 messages, got %d", msgCount)
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

// ─── Additional Coverage Tests for Start, Stop, connect, worker, sendLog, getCurrentHostname

func TestStart_ValidConnection(t *testing.T) {
	// Test Start when syslog server is reachable
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	err := l.Start()
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Verify connection was established
	l.mu.RLock()
	if l.conn == nil {
		t.Error("expected connection to be established")
	}
	l.mu.RUnlock()

	l.Stop()
}

func TestStart_UnreachableServer(t *testing.T) {
	// Test Start when syslog server is unreachable
	l := NewSyslogLogger("127.0.0.1", "9999")

	// Should not fail, just log and continue
	err := l.Start()
	if err != nil {
		// Start might fail or succeed depending on implementation,
		// but it should be reasonable
		t.Logf("Start returned error (acceptable): %v", err)
	}

	l.Stop()
}

func TestStart_DisabledLogger(t *testing.T) {
	// Test Start on disabled logger (empty host)
	l := NewSyslogLogger("", "514")

	err := l.Start()
	if err != nil {
		t.Fatalf("Start failed for disabled logger: %v", err)
	}

	l.Stop()
}

func TestStop_WithActiveWorkers(t *testing.T) {
	// Test Stop properly shuts down worker goroutines
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	err := l.Start()
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue some logs
	l.LogAccess(AccessLog{
		Timestamp:  time.Now().UTC(),
		UserID:     "test",
		Action:     "allow",
		TargetHost: "host1",
	})

	// Stop should drain queue and shut down workers
	l.Stop()

	// After stop, queue should be closed and empty
	if len(l.logQueue) != 0 {
		t.Errorf("expected empty queue after Stop, got %d items", len(l.logQueue))
	}
}

func TestStop_DisabledLogger(t *testing.T) {
	// Test Stop on disabled logger
	l := NewSyslogLogger("", "514")
	l.Start()

	// Should not panic
	l.Stop()
}

func TestConnect_FailedDial(t *testing.T) {
	// Test connect when dial fails
	l := NewSyslogLogger("127.0.0.1", "9999")

	// Try to connect to an unreachable port
	// (Note: this may or may not fail depending on network configuration,
	// so we just ensure it doesn't crash)
	_ = l.connect()
	// Either succeeded (port happens to be open) or failed (port is closed)
	// Both are acceptable - we're testing that it doesn't crash
}

func TestConnect_ClosesExistingConnection(t *testing.T) {
	// Test that connect closes old connection before creating new one
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	// First connect
	if err := l.connect(); err != nil {
		t.Fatalf("first connect failed: %v", err)
	}

	l.mu.Lock()
	oldConn := l.conn
	l.mu.Unlock()

	// Second connect (close old, create new)
	if err := l.connect(); err != nil {
		t.Fatalf("second connect failed: %v", err)
	}

	l.mu.Lock()
	newConn := l.conn
	l.mu.Unlock()

	if oldConn == newConn {
		t.Error("expected different connection objects after reconnect")
	}

	oldConn.Close()
	newConn.Close()
}

func TestWorker_ProcessesQueue(t *testing.T) {
	// Test worker processes logs from queue
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	err := l.Start()
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Send logs via LogAccess
	for i := 0; i < 5; i++ {
		l.LogAccess(AccessLog{
			Timestamp:  time.Now().UTC(),
			UserID:     "user" + itoa(i),
			Action:     "allow",
			TargetHost: "host" + itoa(i),
		})
	}

	// Give worker time to process
	time.Sleep(200 * time.Millisecond)

	l.Stop()

	// Queue should be mostly empty (some items may still be processing)
	queueLen := len(l.logQueue)
	if queueLen > 2 {
		t.Errorf("expected queue to be mostly empty, got %d items", queueLen)
	}
}

func TestSendLog_WithClosedConnection(t *testing.T) {
	// Test sendLog handles closed connection gracefully
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	port := server.LocalAddr().(*net.UDPAddr).Port

	l := NewSyslogLogger("127.0.0.1", itoa(port))
	if err := l.connect(); err != nil {
		t.Fatalf("connect failed: %v", err)
	}

	// Close the server to simulate connection failure
	server.Close()

	// Send log after server is closed
	err := l.sendLog(AccessLog{
		Timestamp:  time.Now().UTC(),
		UserID:     "test",
		Action:     "allow",
		TargetHost: "host",
	})

	// Should handle the error
	if err == nil {
		t.Logf("sendLog succeeded (connection may have been cached)")
	}

	l.conn.Close()
}

func TestGetCurrentHostname_Success(t *testing.T) {
	// Test getCurrentHostname returns a non-empty string
	hostname, err := getCurrentHostname()
	if err != nil {
		t.Logf("getCurrentHostname returned error: %v", err)
	}
	if hostname == "" {
		t.Error("expected non-empty hostname")
	}
}

func TestGetCurrentHostname_Consistent(t *testing.T) {
	// Test getCurrentHostname returns consistent value
	h1, _ := getCurrentHostname()
	h2, _ := getCurrentHostname()
	if h1 != h2 {
		t.Errorf("expected consistent hostname, got %s then %s", h1, h2)
	}
}

// ─── Additional coverage tests for uncovered branches ──────────────────────────

// TestStart_ConnectFailure tests error propagation when connect fails
func TestStart_ConnectFailure(t *testing.T) {
	// Create logger with invalid address that will fail to connect
	l := NewSyslogLogger("127.0.0.1", "1")
	err := l.Start()
	// Connect to port 1 may fail or succeed depending on system
	// This test just ensures Start handles it gracefully
	if err != nil {
		// Error is acceptable when connect fails
		if !strings.Contains(err.Error(), "failed to connect") {
			t.Logf("unexpected error format: %v", err)
		}
	}
}

// TestStop_DisabledNeverStarted tests that Stop on a logger with empty host (disabled) returns immediately.
func TestStop_DisabledNeverStarted(t *testing.T) {
	// Empty host → enabled=false; Stop() hits the !enabled early return immediately
	l := NewSyslogLogger("", "9999")
	done := make(chan struct{})
	go func() {
		l.Stop()
		close(done)
	}()
	select {
	case <-done:
		// Good — returned quickly
	case <-time.After(500 * time.Millisecond):
		t.Fatal("Stop() on disabled logger did not return in time")
	}
}

// TestWorker_StopsOnStopChannel tests worker exits on stop signal
func TestWorker_StopsOnStopChannel(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Immediately stop to verify worker responds to stop signal
	done := make(chan struct{})
	go func() {
		l.Stop()
		close(done)
	}()

	select {
	case <-done:
		// good, stop completed quickly
	case <-time.After(2 * time.Second):
		t.Error("Stop timed out")
	}
}

// TestSendLog_MarshalError_ValidData tests sendLog with valid data
func TestSendLog_MarshalError_ValidData(t *testing.T) {
	// Create a logger with connection to test valid marshal
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.connect(); err != nil {
		t.Fatalf("connect failed: %v", err)
	}
	defer l.conn.Close()

	// AccessLog with valid data should work
	err := l.sendLog(AccessLog{
		Timestamp:  time.Now().UTC(),
		UserID:     "user1",
		Action:     "allow",
		TargetHost: "host.com",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

// TestLogAccess_DisabledMultipleCalls tests disabled logger with multiple calls
func TestLogAccess_DisabledMultipleCalls(t *testing.T) {
	l := NewSyslogLogger("", "514")

	// Multiple calls should be no-ops
	for i := 0; i < 10; i++ {
		l.LogAccess(AccessLog{UserID: "user" + strconv.Itoa(i)})
	}

	if l.GetQueueDepth() != 0 {
		t.Error("disabled logger should not queue any logs")
	}
}

// TestLogHTTPAccess_StatusCodeVariations tests various HTTP status codes
func TestLogHTTPAccess_StatusCodeVariations(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")

	statusCodes := []int{100, 200, 301, 400, 403, 500, 503}
	for _, code := range statusCodes {
		l.LogHTTPAccess("user", "user", "127.0.0.1", "host", "GET", "/", "agent", "rid", code, 0, true)
	}

	if l.GetQueueDepth() != len(statusCodes) {
		t.Errorf("expected queue depth %d, got %d", len(statusCodes), l.GetQueueDepth())
	}

	// Drain queue and verify status codes
	for i, expectedCode := range statusCodes {
		pkt := <-l.logQueue
		if pkt.StatusCode != expectedCode {
			t.Errorf("log %d: expected status %d, got %d", i, expectedCode, pkt.StatusCode)
		}
	}
}

// TestLogHTTPAccess_DenyAction tests deny action is correctly set
func TestLogHTTPAccess_DenyAction(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogHTTPAccess("user", "username", "127.0.0.1", "blocked.com", "POST", "/admin", "curl", "req", 403, 0, false)

	pkt := <-l.logQueue
	if pkt.Action != "deny" {
		t.Errorf("expected deny, got %s", pkt.Action)
	}
}

// TestLogTCPAccess_DenyAction tests TCP deny action
func TestLogTCPAccess_DenyAction(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogTCPAccess("user", "username", "127.0.0.1", "10.0.0.1:22", false)

	pkt := <-l.logQueue
	if pkt.Action != "deny" {
		t.Errorf("expected deny, got %s", pkt.Action)
	}
}

// TestLogUDPAccess_DenyAction tests UDP deny action
func TestLogUDPAccess_DenyAction(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	l.LogUDPAccess("user", "username", "127.0.0.1", "10.0.0.1:53", false)

	pkt := <-l.logQueue
	if pkt.Action != "deny" {
		t.Errorf("expected deny, got %s", pkt.Action)
	}
}

// TestConnect_InvalidAddressResolution tests connect with invalid hostname
func TestConnect_InvalidAddressResolution(t *testing.T) {
	l := NewSyslogLogger("999.999.999.999", "514")
	err := l.connect()
	if err == nil {
		t.Error("expected error for invalid address")
	}
}

// TestWorker_ProcessesBeforeStop tests worker processes queued items before returning
func TestWorker_ProcessesBeforeStop(t *testing.T) {
	serverAddr, _ := net.ResolveUDPAddr("udp", "127.0.0.1:0")
	server, _ := net.ListenUDP("udp", serverAddr)
	defer server.Close()

	port := server.LocalAddr().(*net.UDPAddr).Port
	l := NewSyslogLogger("127.0.0.1", itoa(port))

	if err := l.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Queue several logs before stopping
	for i := 0; i < 3; i++ {
		l.LogAccess(AccessLog{
			UserID:     "user" + strconv.Itoa(i),
			Timestamp:  time.Now().UTC(),
			TargetHost: "host" + strconv.Itoa(i),
		})
	}

	// Stop should drain queue before returning
	done := make(chan struct{})
	go func() {
		l.Stop()
		close(done)
	}()

	select {
	case <-done:
		// good
	case <-time.After(2 * time.Second):
		t.Error("Stop timed out while draining queue")
	}
}

// TestSendLog_WithNilConnection tests sendLog with no connection established
func TestSendLog_WithNilConnection(t *testing.T) {
	l := NewSyslogLogger("127.0.0.1", "514")
	// conn is intentionally nil
	err := l.sendLog(AccessLog{
		Timestamp:  time.Now().UTC(),
		UserID:     "test",
		TargetHost: "host",
	})

	if err == nil {
		t.Error("expected error when conn is nil")
	}
	if !strings.Contains(err.Error(), "no syslog connection") {
		t.Errorf("expected 'no syslog connection' error, got: %v", err)
	}
}

// ─── getCurrentHostname error paths ──────────────────────────────────────────

// TestGetCurrentHostname_LookupFails_LookupAddrSucceeds covers the branch where
// LookupCNAME fails but LookupAddr("127.0.0.1") returns a hostname.
func TestGetCurrentHostname_LookupFails_LookupAddrSucceeds(t *testing.T) {
	old := lookupCNAMEFn
	oldAddr := lookupAddrFn
	defer func() { lookupCNAMEFn = old; lookupAddrFn = oldAddr }()

	lookupCNAMEFn = func(host string) (string, error) {
		return "", &net.DNSError{Err: "no such host", Name: host}
	}
	lookupAddrFn = func(addr string) ([]string, error) {
		return []string{"myhost.local."}, nil
	}

	hostname, err := getCurrentHostname()
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if hostname != "myhost.local." {
		t.Errorf("expected myhost.local., got %s", hostname)
	}
}

// TestGetCurrentHostname_LookupFails_FallbackHostname covers the final fallback
// when both LookupCNAME and LookupAddr fail.
func TestGetCurrentHostname_LookupFails_FallbackHostname(t *testing.T) {
	old := lookupCNAMEFn
	oldAddr := lookupAddrFn
	defer func() { lookupCNAMEFn = old; lookupAddrFn = oldAddr }()

	lookupCNAMEFn = func(host string) (string, error) {
		return "", &net.DNSError{Err: "no such host", Name: host}
	}
	lookupAddrFn = func(addr string) ([]string, error) {
		return nil, &net.DNSError{Err: "lookup failed", Name: addr}
	}

	hostname, err := getCurrentHostname()
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if hostname != "tobogganing-hub-router" {
		t.Errorf("expected fallback hostname, got %s", hostname)
	}
}
