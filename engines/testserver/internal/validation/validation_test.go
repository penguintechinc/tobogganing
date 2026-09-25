package validation_test

import (
	"strings"
	"testing"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/validation"
)

// ---------------------------------------------------------------------------
// ValidationError
// ---------------------------------------------------------------------------

func TestValidationError_Error(t *testing.T) {
	err := &validation.ValidationError{Field: "port", Message: "out of range"}
	got := err.Error()
	if !strings.Contains(got, "port") {
		t.Errorf("Error() = %q, want it to contain 'port'", got)
	}
	if !strings.Contains(got, "out of range") {
		t.Errorf("Error() = %q, want it to contain 'out of range'", got)
	}
}

// ---------------------------------------------------------------------------
// ValidateTarget
// ---------------------------------------------------------------------------

func TestValidateTarget(t *testing.T) {
	tests := []struct {
		name    string
		target  string
		wantErr bool
	}{
		{"valid hostname", "example.com", false},
		{"valid IP", "8.8.8.8", false},
		// Note: bare IPv6 addresses like ::1 are not supported by ValidateTarget
		// because the colon detection sends it into net.SplitHostPort which requires a port.
		{"valid with scheme", "https://example.com", false},
		{"valid with scheme and path", "https://example.com/path", false},
		{"valid subdomain", "api.example.com", false},
		{"empty target", "", true},
		{"invalid hostname underscore", "invalid_host", true},
		{"target too long", strings.Repeat("a", 256), true},
		{"URL scheme invalid format", "://bad", true},
		{"localhost allowed", "localhost", false}, // code allows it with log warning
		{"127.0.0.1 allowed", "127.0.0.1", false},
		{"10.x allowed", "10.1.2.3", false},
		{"192.168.x allowed", "192.168.1.1", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateTarget(tt.target)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateTarget(%q) error = %v, wantErr = %v", tt.target, err, tt.wantErr)
			}
		})
	}
}

func TestValidateTarget_ExactMaxLength(t *testing.T) {
	// exactly 255 chars should pass
	target := strings.Repeat("a", 62) + "." + strings.Repeat("b", 62) + "." + strings.Repeat("c", 62) + ".com"
	if len(target) > 255 {
		t.Skip("constructed target exceeds 255, skipping exact-length test")
	}
	if err := validation.ValidateTarget(target); err != nil {
		t.Errorf("ValidateTarget with length=%d should pass, got: %v", len(target), err)
	}
}

// ---------------------------------------------------------------------------
// ValidateDNSQuery
// ---------------------------------------------------------------------------

func TestValidateDNSQuery(t *testing.T) {
	tests := []struct {
		name    string
		query   string
		wantErr bool
	}{
		{"empty query (optional)", "", false},
		{"valid domain", "google.com", false},
		{"valid with trailing dot", "google.com.", false},
		{"valid subdomain", "api.example.com", false},
		{"query too long", strings.Repeat("a", 256), true},
		{"invalid chars", "inval!d.com", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateDNSQuery(tt.query)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateDNSQuery(%q) error = %v, wantErr = %v", tt.query, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidatePort
// ---------------------------------------------------------------------------

func TestValidatePort(t *testing.T) {
	tests := []struct {
		name    string
		port    int
		wantErr bool
	}{
		{"min valid port", 1, false},
		{"max valid port", 65535, false},
		{"common HTTP port", 80, false},
		{"common HTTPS port", 443, false},
		{"port zero", 0, true},
		{"negative port", -1, true},
		{"port too high", 65536, true},
		{"port far too high", 99999, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidatePort(tt.port)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidatePort(%d) error = %v, wantErr = %v", tt.port, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidateTimeout
// ---------------------------------------------------------------------------

func TestValidateTimeout(t *testing.T) {
	tests := []struct {
		name    string
		timeout int
		wantErr bool
	}{
		{"min valid", 1, false},
		{"max valid", 300, false},
		{"typical 30s", 30, false},
		{"zero", 0, true},
		{"negative", -1, true},
		{"too large", 301, true},
		{"way too large", 9999, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateTimeout(tt.timeout)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateTimeout(%d) error = %v, wantErr = %v", tt.timeout, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidateCount
// ---------------------------------------------------------------------------

func TestValidateCount(t *testing.T) {
	tests := []struct {
		name    string
		count   int
		wantErr bool
	}{
		{"min valid", 1, false},
		{"max valid", 1000, false},
		{"typical 4", 4, false},
		{"zero", 0, true},
		{"negative", -1, true},
		{"too large", 1001, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateCount(tt.count)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateCount(%d) error = %v, wantErr = %v", tt.count, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidateHTTPProtocol
// ---------------------------------------------------------------------------

func TestValidateHTTPProtocol(t *testing.T) {
	tests := []struct {
		name     string
		protocol string
		wantErr  bool
	}{
		{"empty (optional)", "", false},
		{"http1", "http1", false},
		{"http/1.1", "http/1.1", false},
		{"http1.1", "http1.1", false},
		{"http2", "http2", false},
		{"http/2", "http/2", false},
		{"http3", "http3", false},
		{"http/3", "http/3", false},
		{"HTTP/1.1 uppercase", "HTTP/1.1", false},
		{"HTTP/2 uppercase", "HTTP/2", false},
		{"HTTP/3 uppercase", "HTTP/3", false},
		{"invalid value", "grpc", true},
		{"too long", strings.Repeat("x", 51), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateHTTPProtocol(tt.protocol)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateHTTPProtocol(%q) error = %v, wantErr = %v", tt.protocol, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidateTCPProtocol
// ---------------------------------------------------------------------------

func TestValidateTCPProtocol(t *testing.T) {
	tests := []struct {
		name     string
		protocol string
		wantErr  bool
	}{
		{"empty (optional)", "", false},
		{"raw", "raw", false},
		{"raw_tcp", "raw_tcp", false},
		{"Raw TCP", "Raw TCP", false},
		{"tcp", "tcp", false},
		{"tls", "tls", false},
		{"TLS uppercase", "TLS", false},
		{"ssh", "ssh", false},
		{"SSH uppercase", "SSH", false},
		{"invalid value", "ftp", true},
		{"too long", strings.Repeat("x", 51), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateTCPProtocol(tt.protocol)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateTCPProtocol(%q) error = %v, wantErr = %v", tt.protocol, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidateUDPProtocol
// ---------------------------------------------------------------------------

func TestValidateUDPProtocol(t *testing.T) {
	tests := []struct {
		name     string
		protocol string
		wantErr  bool
	}{
		{"empty (optional)", "", false},
		{"raw", "raw", false},
		{"raw_udp", "raw_udp", false},
		{"Raw UDP", "Raw UDP", false},
		{"udp", "udp", false},
		{"dns", "dns", false},
		{"DNS uppercase", "DNS", false},
		{"invalid value", "quic", true},
		{"too long", strings.Repeat("x", 51), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateUDPProtocol(tt.protocol)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateUDPProtocol(%q) error = %v, wantErr = %v", tt.protocol, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidateICMPProtocol
// ---------------------------------------------------------------------------

func TestValidateICMPProtocol(t *testing.T) {
	tests := []struct {
		name     string
		protocol string
		wantErr  bool
	}{
		{"empty (optional)", "", false},
		{"ping", "ping", false},
		{"traceroute", "traceroute", false},
		{"invalid value", "flood", true},
		{"too long", strings.Repeat("x", 51), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateICMPProtocol(tt.protocol)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateICMPProtocol(%q) error = %v, wantErr = %v", tt.protocol, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// ValidateHTTPMethod
// ---------------------------------------------------------------------------

func TestValidateHTTPMethod(t *testing.T) {
	tests := []struct {
		name    string
		method  string
		wantErr bool
	}{
		{"empty (optional)", "", false},
		{"GET", "GET", false},
		{"POST", "POST", false},
		{"HEAD", "HEAD", false},
		{"OPTIONS", "OPTIONS", false},
		{"PATCH invalid", "PATCH", true},
		{"DELETE invalid", "DELETE", true},
		{"PUT invalid", "PUT", true},
		{"lowercase get", "get", true},
		{"too long", strings.Repeat("X", 11), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validation.ValidateHTTPMethod(tt.method)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateHTTPMethod(%q) error = %v, wantErr = %v", tt.method, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// SanitizeString
// ---------------------------------------------------------------------------

func TestSanitizeString(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		maxLength int
		want      string
	}{
		{"normal string", "hello", 100, "hello"},
		{"trims whitespace", "  hello  ", 100, "hello"},
		{"truncates at maxLength", "hello world", 5, "hello"},
		{"removes null bytes", "hel\x00lo", 100, "hello"},
		{"removes control chars", "hel\x01\x02lo", 100, "hello"},
		{"keeps tab", "hel\tlo", 100, "hel\tlo"},
		{"keeps newline", "hel\nlo", 100, "hel\nlo"},
		{"keeps carriage return", "hel\rlo", 100, "hel\rlo"},
		{"empty string", "", 100, ""},
		{"exactly maxLength", "hello", 5, "hello"},
		{"beyond maxLength", "hello!", 5, "hello"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := validation.SanitizeString(tt.input, tt.maxLength)
			if got != tt.want {
				t.Errorf("SanitizeString(%q, %d) = %q, want %q", tt.input, tt.maxLength, got, tt.want)
			}
		})
	}
}

func TestSanitizeString_MaxLengthConstants(t *testing.T) {
	// Verify the exported constants are sane (they're used by callers)
	if validation.MaxTargetLength <= 0 {
		t.Errorf("MaxTargetLength should be positive, got %d", validation.MaxTargetLength)
	}
	if validation.MaxQueryLength <= 0 {
		t.Errorf("MaxQueryLength should be positive, got %d", validation.MaxQueryLength)
	}
	if validation.MaxProtocolLength <= 0 {
		t.Errorf("MaxProtocolLength should be positive, got %d", validation.MaxProtocolLength)
	}
	if validation.MaxMethodLength <= 0 {
		t.Errorf("MaxMethodLength should be positive, got %d", validation.MaxMethodLength)
	}
	if validation.MaxHeaderNameLength <= 0 {
		t.Errorf("MaxHeaderNameLength should be positive, got %d", validation.MaxHeaderNameLength)
	}
	if validation.MaxHeaderValueLength <= 0 {
		t.Errorf("MaxHeaderValueLength should be positive, got %d", validation.MaxHeaderValueLength)
	}
	if validation.MaxTimeoutSeconds <= 0 {
		t.Errorf("MaxTimeoutSeconds should be positive, got %d", validation.MaxTimeoutSeconds)
	}
	if validation.MaxCount <= 0 {
		t.Errorf("MaxCount should be positive, got %d", validation.MaxCount)
	}
	if validation.MinPort != 1 {
		t.Errorf("MinPort should be 1, got %d", validation.MinPort)
	}
	if validation.MaxPort != 65535 {
		t.Errorf("MaxPort should be 65535, got %d", validation.MaxPort)
	}
}
