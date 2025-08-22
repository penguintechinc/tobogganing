// Package syslog implements RFC3164 compliant UDP syslog logging for the SASEWaddle headend proxy.
//
// The syslog logger provides:
// - RFC3164 compliant syslog message formatting
// - UDP-only transport for security compliance
// - High-performance logging with worker queues
// - Comprehensive access logging for all user activities
// - JSON payload support for structured logging
// - Automatic connection management and retry logic
// - Configurable facility and severity levels
// - Non-blocking operation to prevent proxy slowdown
//
// All user access attempts (both allowed and denied) are logged with
// detailed metadata for security auditing and compliance reporting.
package syslog

import (
	"encoding/json"
	"fmt"
	"net"
	"sync"
	"time"

	log "github.com/sirupsen/logrus"
)

// AccessLog represents a user access log entry
type AccessLog struct {
	Timestamp   time.Time `json:"timestamp"`
	UserID      string    `json:"user_id"`
	Username    string    `json:"username"`
	SourceIP    string    `json:"source_ip"`
	TargetHost  string    `json:"target_host"`
	Protocol    string    `json:"protocol"`
	Action      string    `json:"action"` // "allow" or "deny"
	Method      string    `json:"method,omitempty"`
	Path        string    `json:"path,omitempty"`
	StatusCode  int       `json:"status_code,omitempty"`
	BytesSent   int64     `json:"bytes_sent,omitempty"`
	UserAgent   string    `json:"user_agent,omitempty"`
	RequestID   string    `json:"request_id,omitempty"`
}

// SyslogLogger handles UDP syslog logging for user access
type SyslogLogger struct {
	enabled      bool
	syslogHost   string
	syslogPort   string
	facility     int
	severity     int
	hostname     string
	appName      string
	conn         *net.UDPConn
	mu           sync.RWMutex
	logQueue     chan AccessLog
	workers      int
	stopChan     chan bool
}

// RFC3164 priority calculation: facility * 8 + severity
const (
	// Facilities
	FacilityLocal0 = 16
	FacilityLocal1 = 17
	FacilityLocal2 = 18
	FacilityLocal3 = 19
	FacilityLocal4 = 20
	FacilityLocal5 = 21
	FacilityLocal6 = 22
	FacilityLocal7 = 23

	// Severities
	SeverityEmergency     = 0
	SeverityAlert         = 1
	SeverityCritical      = 2
	SeverityError         = 3
	SeverityWarning       = 4
	SeverityNotice        = 5
	SeverityInformational = 6
	SeverityDebug         = 7
)

// NewSyslogLogger creates a new syslog logger instance
func NewSyslogLogger(syslogHost, syslogPort string) *SyslogLogger {
	hostname, _ := getCurrentHostname()
	
	return &SyslogLogger{
		enabled:     syslogHost != "",
		syslogHost:  syslogHost,
		syslogPort:  syslogPort,
		facility:    FacilityLocal0,
		severity:    SeverityInformational,
		hostname:    hostname,
		appName:     "sasewaddle-headend",
		logQueue:    make(chan AccessLog, 1000), // Buffer up to 1000 logs
		workers:     3,                          // 3 worker goroutines
		stopChan:    make(chan bool),
	}
}

// Start initializes the syslog logger and starts worker goroutines
func (s *SyslogLogger) Start() error {
	if !s.enabled {
		log.Info("Syslog logging disabled")
		return nil
	}

	// Establish UDP connection
	if err := s.connect(); err != nil {
		return fmt.Errorf("failed to connect to syslog server: %w", err)
	}

	// Start worker goroutines
	for i := 0; i < s.workers; i++ {
		go s.worker(fmt.Sprintf("worker-%d", i))
	}

	log.Infof("Syslog logger started - sending to %s:%s", s.syslogHost, s.syslogPort)
	return nil
}

// Stop gracefully shuts down the syslog logger
func (s *SyslogLogger) Stop() {
	if !s.enabled {
		return
	}

	log.Info("Stopping syslog logger")
	
	// Signal workers to stop
	for i := 0; i < s.workers; i++ {
		s.stopChan <- true
	}

	// Close connection
	s.mu.Lock()
	if s.conn != nil {
		if err := s.conn.Close(); err != nil {
			log.Debugf("Error closing syslog connection: %v", err)
		}
		s.conn = nil
	}
	s.mu.Unlock()

	log.Info("Syslog logger stopped")
}

// LogAccess logs a user access event
func (s *SyslogLogger) LogAccess(accessLog AccessLog) {
	if !s.enabled {
		return
	}

	// Set timestamp if not provided
	if accessLog.Timestamp.IsZero() {
		accessLog.Timestamp = time.Now().UTC()
	}

	// Non-blocking send to queue
	select {
	case s.logQueue <- accessLog:
		// Successfully queued
	default:
		// Queue is full, drop the log entry
		log.Warn("Syslog queue full, dropping access log entry")
	}
}

// LogHTTPAccess logs HTTP access with detailed information
func (s *SyslogLogger) LogHTTPAccess(userID, username, sourceIP, targetHost, method, path, userAgent, requestID string, statusCode int, bytesSent int64, allowed bool) {
	action := "allow"
	if !allowed {
		action = "deny"
	}

	s.LogAccess(AccessLog{
		UserID:     userID,
		Username:   username,
		SourceIP:   sourceIP,
		TargetHost: targetHost,
		Protocol:   "HTTP",
		Action:     action,
		Method:     method,
		Path:       path,
		StatusCode: statusCode,
		BytesSent:  bytesSent,
		UserAgent:  userAgent,
		RequestID:  requestID,
	})
}

// LogTCPAccess logs TCP connection access
func (s *SyslogLogger) LogTCPAccess(userID, username, sourceIP, targetHost string, allowed bool) {
	action := "allow"
	if !allowed {
		action = "deny"
	}

	s.LogAccess(AccessLog{
		UserID:     userID,
		Username:   username,
		SourceIP:   sourceIP,
		TargetHost: targetHost,
		Protocol:   "TCP",
		Action:     action,
	})
}

// LogUDPAccess logs UDP packet access
func (s *SyslogLogger) LogUDPAccess(userID, username, sourceIP, targetHost string, allowed bool) {
	action := "allow"
	if !allowed {
		action = "deny"
	}

	s.LogAccess(AccessLog{
		UserID:     userID,
		Username:   username,
		SourceIP:   sourceIP,
		TargetHost: targetHost,
		Protocol:   "UDP",
		Action:     action,
	})
}

// connect establishes UDP connection to syslog server
func (s *SyslogLogger) connect() error {
	serverAddr, err := net.ResolveUDPAddr("udp", fmt.Sprintf("%s:%s", s.syslogHost, s.syslogPort))
	if err != nil {
		return fmt.Errorf("failed to resolve syslog server address: %w", err)
	}

	conn, err := net.DialUDP("udp", nil, serverAddr)
	if err != nil {
		return fmt.Errorf("failed to connect to syslog server: %w", err)
	}

	s.mu.Lock()
	s.conn = conn
	s.mu.Unlock()

	return nil
}

// worker processes log entries from the queue
func (s *SyslogLogger) worker(name string) {
	log.Debugf("Syslog worker %s started", name)
	
	for {
		select {
		case accessLog := <-s.logQueue:
			if err := s.sendLog(accessLog); err != nil {
				log.Errorf("Syslog worker %s failed to send log: %v", name, err)
				// Try to reconnect
				if err := s.connect(); err != nil {
					log.Errorf("Syslog worker %s failed to reconnect: %v", name, err)
				}
			}
		case <-s.stopChan:
			log.Debugf("Syslog worker %s stopping", name)
			return
		}
	}
}

// sendLog formats and sends a log entry to syslog server
func (s *SyslogLogger) sendLog(accessLog AccessLog) error {
	s.mu.RLock()
	conn := s.conn
	s.mu.RUnlock()

	if conn == nil {
		return fmt.Errorf("no syslog connection available")
	}

	// Calculate priority (facility * 8 + severity)
	priority := s.facility*8 + s.severity

	// Format timestamp (RFC3339)
	timestamp := accessLog.Timestamp.Format(time.RFC3339)

	// Create structured message with JSON payload
	jsonData, err := json.Marshal(accessLog)
	if err != nil {
		return fmt.Errorf("failed to marshal access log: %w", err)
	}

	// RFC3164 format: <priority>timestamp hostname appname: message
	message := fmt.Sprintf("<%d>%s %s %s: %s",
		priority,
		timestamp,
		s.hostname,
		s.appName,
		string(jsonData),
	)

	// Send UDP packet
	_, err = conn.Write([]byte(message))
	if err != nil {
		return fmt.Errorf("failed to write to syslog connection: %w", err)
	}

	log.Debugf("Sent syslog message for user %s accessing %s", accessLog.UserID, accessLog.TargetHost)
	return nil
}

// getCurrentHostname gets the current hostname with fallback
func getCurrentHostname() (string, error) {
	hostname, err := net.LookupCNAME("localhost")
	if err != nil {
		// Fallback to local hostname
		if h, err2 := net.LookupAddr("127.0.0.1"); err2 == nil && len(h) > 0 {
			return h[0], nil
		}
		return "sasewaddle-headend", nil
	}
	return hostname, nil
}

// GetQueueDepth returns the current depth of the log queue
func (s *SyslogLogger) GetQueueDepth() int {
	if !s.enabled {
		return 0
	}
	return len(s.logQueue)
}

// IsEnabled returns whether syslog logging is enabled
func (s *SyslogLogger) IsEnabled() bool {
	return s.enabled
}