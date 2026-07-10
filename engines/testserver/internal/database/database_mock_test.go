package database_test

import (
	"encoding/json"
	"testing"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
)

// ---------------------------------------------------------------------------
// TestResult struct field tests — these cover the struct and json marshaling
// without requiring a real database connection.
// ---------------------------------------------------------------------------

func TestTestResult_AllFieldsSet(t *testing.T) {
	latency := 12.5
	throughput := 100.0
	jitter := 1.5
	packetLoss := 0.0
	userID := 42

	result := &database.TestResult{
		UserID:            &userID,
		DeviceSerial:      "SN-12345",
		DeviceHostname:    "test-host",
		DeviceOS:          "Linux",
		DeviceOSVersion:   "6.1",
		TestType:          "http",
		ProtocolDetail:    "http1",
		TargetHost:        "example.com",
		TargetIP:          "93.184.216.34",
		ClientIP:          "192.168.1.100",
		LatencyMS:         &latency,
		ThroughputMbps:    &throughput,
		JitterMS:          &jitter,
		PacketLossPercent: &packetLoss,
		RawResults: map[string]interface{}{
			"status_code": 200,
			"ttfb_ms":     5.0,
		},
	}

	if result.DeviceSerial != "SN-12345" {
		t.Errorf("DeviceSerial mismatch: got %q", result.DeviceSerial)
	}
	if result.TestType != "http" {
		t.Errorf("TestType mismatch: got %q", result.TestType)
	}
	if result.LatencyMS == nil || *result.LatencyMS != 12.5 {
		t.Errorf("LatencyMS mismatch")
	}
	if result.UserID == nil || *result.UserID != 42 {
		t.Errorf("UserID mismatch")
	}
}

func TestTestResult_NilPointerFields(t *testing.T) {
	// A TestResult with all pointer fields nil should be constructible.
	result := &database.TestResult{
		DeviceSerial:   "SN-NULL",
		DeviceHostname: "null-host",
		TestType:       "tcp",
	}

	if result.LatencyMS != nil {
		t.Error("expected LatencyMS to be nil")
	}
	if result.ThroughputMbps != nil {
		t.Error("expected ThroughputMbps to be nil")
	}
	if result.JitterMS != nil {
		t.Error("expected JitterMS to be nil")
	}
	if result.PacketLossPercent != nil {
		t.Error("expected PacketLossPercent to be nil")
	}
	if result.UserID != nil {
		t.Error("expected UserID to be nil")
	}
}

func TestTestResult_RawResultsMarshaling(t *testing.T) {
	result := &database.TestResult{
		RawResults: map[string]interface{}{
			"hop_count":   5,
			"status_code": 200,
			"ttfb_ms":     3.5,
			"nested":      map[string]interface{}{"key": "value"},
		},
	}

	data, err := json.Marshal(result.RawResults)
	if err != nil {
		t.Fatalf("json.Marshal(RawResults) failed: %v", err)
	}
	if len(data) == 0 {
		t.Error("expected non-empty JSON from RawResults")
	}

	// Verify round-trip
	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("json.Unmarshal failed: %v", err)
	}
	if decoded["hop_count"] == nil {
		t.Error("expected hop_count in decoded map")
	}
}

func TestTestResult_EmptyRawResults(t *testing.T) {
	result := &database.TestResult{
		RawResults: map[string]interface{}{},
	}

	data, err := json.Marshal(result.RawResults)
	if err != nil {
		t.Fatalf("json.Marshal failed: %v", err)
	}
	if string(data) != "{}" {
		t.Errorf("expected '{}', got %q", string(data))
	}
}

func TestTestResult_AllTestTypes(t *testing.T) {
	testTypes := []string{"http", "tcp", "udp", "icmp", "http_trace", "tcp_trace", "udp_trace", "traceroute", "speedtest"}
	for _, tt := range testTypes {
		t.Run(tt, func(t *testing.T) {
			result := &database.TestResult{
				TestType: tt,
			}
			if result.TestType != tt {
				t.Errorf("TestType mismatch: got %q, want %q", result.TestType, tt)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// User struct tests
// ---------------------------------------------------------------------------

func TestUser_Fields(t *testing.T) {
	ouID := 7
	user := database.User{
		ID:       1,
		Username: "testuser",
		Email:    "test@example.com",
		Role:     "Admin",
		OUID:     &ouID,
		IsActive: true,
	}

	if user.ID != 1 {
		t.Errorf("User.ID mismatch: got %d", user.ID)
	}
	if user.Username != "testuser" {
		t.Errorf("User.Username mismatch: got %q", user.Username)
	}
	if user.Role != "Admin" {
		t.Errorf("User.Role mismatch: got %q", user.Role)
	}
	if !user.IsActive {
		t.Error("expected IsActive=true")
	}
	if user.OUID == nil || *user.OUID != 7 {
		t.Error("OUID mismatch")
	}
}

func TestUser_NilOUID(t *testing.T) {
	user := database.User{
		ID:       2,
		Username: "noou",
		IsActive: false,
	}

	if user.OUID != nil {
		t.Error("expected OUID to be nil for user without OU")
	}
	if user.IsActive {
		t.Error("expected IsActive=false")
	}
}

// ---------------------------------------------------------------------------
// Config struct tests
// ---------------------------------------------------------------------------

func TestConfig_Fields(t *testing.T) {
	cfg := database.Config{
		Host:     "localhost",
		Port:     "3306",
		User:     "testuser",
		Password: "secret",
		Database: "testdb",
	}

	if cfg.Host != "localhost" {
		t.Errorf("Config.Host mismatch: got %q", cfg.Host)
	}
	if cfg.Port != "3306" {
		t.Errorf("Config.Port mismatch: got %q", cfg.Port)
	}
	if cfg.Database != "testdb" {
		t.Errorf("Config.Database mismatch: got %q", cfg.Database)
	}
}
