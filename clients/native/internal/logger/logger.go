// Package logger provides a shared, sanitized logger for the Tobogganing native client.
// It wraps go-common's SanitizedLogger which automatically redacts sensitive values
// (tokens, keys, passwords) to prevent accidental credential exposure in logs.
package logger

import (
	pglog "github.com/penguintechinc/penguin-libs/packages/go-common/logging"
)

var log *pglog.SanitizedLogger //nolint:gochecknoglobals

// loggerFactory is the function used to construct a SanitizedLogger.
// Tests may replace this variable to inject a factory that simulates errors,
// exercising the init() error-handling branch without modifying the global singleton.
var loggerFactory = func(name string) (*pglog.SanitizedLogger, error) { //nolint:gochecknoglobals
	return pglog.NewSanitizedLogger(name)
}

func init() { //nolint:gochecknoinits
	log = mustNewLogger("tobogganing-client")
}

// mustNewLogger creates a SanitizedLogger or panics.
// It is a separate function so tests can invoke it with the loggerFactory stubbed
// to an error-returning implementation, covering the panic branch via recover().
func mustNewLogger(serviceName string) *pglog.SanitizedLogger {
	l, err := loggerFactory(serviceName)
	if err != nil {
		panic("failed to initialize logger: " + err.Error())
	}
	return l
}

// Get returns the shared sanitized logger instance.
func Get() *pglog.SanitizedLogger {
	return log
}

// newLogger creates a new SanitizedLogger with the given service name.
// Exposed for testing so all configuration branches of logger creation can be exercised
// without relying on the package-level init() singleton.
func newLogger(serviceName string) (*pglog.SanitizedLogger, error) {
	return loggerFactory(serviceName)
}
