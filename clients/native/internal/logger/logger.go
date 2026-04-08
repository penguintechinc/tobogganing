// Package logger provides a shared, sanitized logger for the Tobogganing native client.
// It wraps go-common's SanitizedLogger which automatically redacts sensitive values
// (tokens, keys, passwords) to prevent accidental credential exposure in logs.
package logger

import (
	pglog "github.com/penguintechinc/penguin-libs/packages/go-common/logging"
)

var log *pglog.SanitizedLogger //nolint:gochecknoglobals

func init() { //nolint:gochecknoinits
	var err error
	log, err = pglog.NewSanitizedLogger("tobogganing-client")
	if err != nil {
		panic("failed to initialize logger: " + err.Error())
	}
}

// Get returns the shared sanitized logger instance.
func Get() *pglog.SanitizedLogger {
	return log
}
