package validation

import (
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strings"
)

// Security validation constants
const (
	MaxTargetLength      = 255
	MaxQueryLength       = 255
	MaxTimeoutSeconds    = 300  // 5 minutes max
	MaxCount             = 1000 // Max iterations
	MinPort              = 1
	MaxPort              = 65535
	MaxProtocolLength    = 50
	MaxMethodLength      = 10
	MaxHeaderNameLength  = 100
	MaxHeaderValueLength = 1000
)

// Valid protocol values (whitelist approach)
var (
	ValidHTTPProtocols = map[string]bool{
		"http1":     true,
		"http/1.1":  true,
		"http1.1":   true,
		"http2":     true,
		"http/2":    true,
		"http3":     true,
		"http/3":    true,
		"HTTP/1.1":  true,
		"HTTP/2":    true,
		"HTTP/3":    true,
	}

	ValidTCPProtocols = map[string]bool{
		"raw":     true,
		"raw_tcp": true,
		"Raw TCP": true,
		"tcp":     true,
		"tls":     true,
		"TLS":     true,
		"ssh":     true,
		"SSH":     true,
	}

	ValidUDPProtocols = map[string]bool{
		"raw":     true,
		"raw_udp": true,
		"Raw UDP": true,
		"udp":     true,
		"dns":     true,
		"DNS":     true,
	}

	ValidICMPProtocols = map[string]bool{
		"ping":       true,
		"traceroute": true,
	}

	ValidHTTPMethods = map[string]bool{
		"GET":     true,
		"POST":    true,
		"HEAD":    true,
		"OPTIONS": true,
	}
)

// Compiled regex patterns for validation
var (
	// Hostname: alphanumeric, hyphens, dots (DNS-safe)
	hostnameRegex = regexp.MustCompile(`^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$`)

	// Domain name for DNS queries
	domainRegex = regexp.MustCompile(`^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.?$`)

	// Alphanumeric and safe special chars only
	safeStringRegex = regexp.MustCompile(`^[a-zA-Z0-9._:\-/]+$`)
)

// ValidationError represents a validation error
type ValidationError struct {
	Field   string
	Message string
}

func (e *ValidationError) Error() string {
	return fmt.Sprintf("validation error for field '%s': %s", e.Field, e.Message)
}

// ValidateTarget validates a target hostname or IP address
func ValidateTarget(target string) error {
	if target == "" {
		return &ValidationError{"target", "target cannot be empty"}
	}

	if len(target) > MaxTargetLength {
		return &ValidationError{"target", fmt.Sprintf("target exceeds maximum length of %d", MaxTargetLength)}
	}

	// Remove URL scheme if present for validation
	cleanTarget := target
	if strings.Contains(target, "://") {
		u, err := url.Parse(target)
		if err != nil {
			return &ValidationError{"target", "invalid URL format"}
		}
		cleanTarget = u.Hostname()
	}

	// Remove port if present
	host := cleanTarget
	if strings.Contains(cleanTarget, ":") {
		var err error
		host, _, err = net.SplitHostPort(cleanTarget)
		if err != nil {
			// Try without port
			parts := strings.Split(cleanTarget, ":")
			host = parts[0]
		}
	}

	// Check if it's a valid IP address
	if ip := net.ParseIP(host); ip != nil {
		return nil // Valid IP
	}

	// Check if it's a valid hostname
	if !hostnameRegex.MatchString(host) {
		return &ValidationError{"target", "invalid hostname format"}
	}

	// Allow localhost/internal addresses (commonly used for development/testing)
	// Note: lowerHost == "localhost" and IP ranges (127.x, 10.x, 192.168.x, etc) are permitted
	// This is intentional to support testing against local services
	lowerHost := strings.ToLower(host)
	if lowerHost == "0.0.0.0" ||
	   strings.HasPrefix(lowerHost, "169.254.") {
		return &ValidationError{"target", "access to invalid targets is prohibited"}
	}

	return nil
}

// ValidateDNSQuery validates a DNS query string
func ValidateDNSQuery(query string) error {
	if query == "" {
		return nil // Optional field
	}

	if len(query) > MaxQueryLength {
		return &ValidationError{"query", fmt.Sprintf("query exceeds maximum length of %d", MaxQueryLength)}
	}

	if !domainRegex.MatchString(query) {
		return &ValidationError{"query", "invalid domain name format"}
	}

	return nil
}

// ValidatePort validates a port number
func ValidatePort(port int) error {
	if port < MinPort || port > MaxPort {
		return &ValidationError{"port", fmt.Sprintf("port must be between %d and %d", MinPort, MaxPort)}
	}
	return nil
}

// ValidateTimeout validates a timeout value
func ValidateTimeout(timeout int) error {
	if timeout < 1 {
		return &ValidationError{"timeout", "timeout must be at least 1 second"}
	}
	if timeout > MaxTimeoutSeconds {
		return &ValidationError{"timeout", fmt.Sprintf("timeout cannot exceed %d seconds", MaxTimeoutSeconds)}
	}
	return nil
}

// ValidateCount validates a count/iteration value
func ValidateCount(count int) error {
	if count < 1 {
		return &ValidationError{"count", "count must be at least 1"}
	}
	if count > MaxCount {
		return &ValidationError{"count", fmt.Sprintf("count cannot exceed %d", MaxCount)}
	}
	return nil
}

// ValidateHTTPProtocol validates HTTP protocol string
func ValidateHTTPProtocol(protocol string) error {
	if protocol == "" {
		return nil // Will use default
	}

	if len(protocol) > MaxProtocolLength {
		return &ValidationError{"protocol", "protocol string too long"}
	}

	if !ValidHTTPProtocols[protocol] {
		return &ValidationError{"protocol", "invalid HTTP protocol"}
	}

	return nil
}

// ValidateTCPProtocol validates TCP protocol string
func ValidateTCPProtocol(protocol string) error {
	if protocol == "" {
		return nil // Will use default
	}

	if len(protocol) > MaxProtocolLength {
		return &ValidationError{"protocol", "protocol string too long"}
	}

	if !ValidTCPProtocols[protocol] {
		return &ValidationError{"protocol", "invalid TCP protocol"}
	}

	return nil
}

// ValidateUDPProtocol validates UDP protocol string
func ValidateUDPProtocol(protocol string) error {
	if protocol == "" {
		return nil // Will use default
	}

	if len(protocol) > MaxProtocolLength {
		return &ValidationError{"protocol", "protocol string too long"}
	}

	if !ValidUDPProtocols[protocol] {
		return &ValidationError{"protocol", "invalid UDP protocol"}
	}

	return nil
}

// ValidateICMPProtocol validates ICMP protocol string
func ValidateICMPProtocol(protocol string) error {
	if protocol == "" {
		return nil // Will use default
	}

	if len(protocol) > MaxProtocolLength {
		return &ValidationError{"protocol", "protocol string too long"}
	}

	if !ValidICMPProtocols[protocol] {
		return &ValidationError{"protocol", "invalid ICMP protocol"}
	}

	return nil
}

// ValidateHTTPMethod validates HTTP method
func ValidateHTTPMethod(method string) error {
	if method == "" {
		return nil // Will use default
	}

	if len(method) > MaxMethodLength {
		return &ValidationError{"method", "method string too long"}
	}

	if !ValidHTTPMethods[method] {
		return &ValidationError{"method", "invalid HTTP method"}
	}

	return nil
}

// SanitizeString removes potentially dangerous characters
func SanitizeString(input string, maxLength int) string {
	// Trim whitespace
	s := strings.TrimSpace(input)

	// Limit length
	if len(s) > maxLength {
		s = s[:maxLength]
	}

	// Remove null bytes and other control characters
	s = strings.Map(func(r rune) rune {
		if r < 32 && r != '\t' && r != '\n' && r != '\r' {
			return -1
		}
		return r
	}, s)

	return s
}
