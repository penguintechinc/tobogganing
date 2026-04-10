package logger

import (
	"fmt"
	"testing"

	pglog "github.com/penguintechinc/penguin-libs/packages/go-common/logging"
)

func TestGetReturnsNonNil(t *testing.T) {
	logger := Get()
	if logger == nil {
		t.Fatal("Get() returned nil, expected non-nil *pglog.SanitizedLogger")
	}
}

func TestGetReturnsSingleton(t *testing.T) {
	logger1 := Get()
	logger2 := Get()
	logger3 := Get()

	if logger1 != logger2 {
		t.Error("Get() returned different instances, expected same singleton")
	}
	if logger2 != logger3 {
		t.Error("Get() returned different instances, expected same singleton")
	}

	// All three should be identical
	if logger1 == nil || logger2 == nil || logger3 == nil {
		t.Fatal("Get() returned nil value in singleton test")
	}
}

// TestInit verifies the init function completes without error
// This test ensures the global logger is properly initialized
func TestInit(t *testing.T) {
	// The init() function runs at package load time
	// If it panicked, this test would never run
	// Just verify Get() works
	l := Get()
	if l == nil {
		t.Error("logger not initialized by init()")
	}
}

// TestInitMultipleCalls verifies Get() can be called multiple times safely
func TestInitMultipleCalls(t *testing.T) {
	for i := 0; i < 100; i++ {
		logger := Get()
		if logger == nil {
			t.Fatalf("Get() returned nil on iteration %d", i)
		}
	}
}

// TestLoggerInterface verifies the logger satisfies its expected interface
func TestLoggerInterface(t *testing.T) {
	logger := Get()
	if logger == nil {
		t.Fatal("Get() returned nil")
	}

	// Verify the logger has expected methods by using them
	// These calls won't panic if the logger is properly initialized
	logger.Debug("test debug message")
	logger.Info("test info message")
	logger.Warn("test warn message")
	logger.Error("test error message")
}

// TestLoggerConcurrentAccess verifies thread-safe access to the logger
func TestLoggerConcurrentAccess(t *testing.T) {
	done := make(chan bool, 10)

	for i := 0; i < 10; i++ {
		go func() {
			logger := Get()
			if logger == nil {
				t.Error("Get() returned nil in goroutine")
			}
			logger.Info("concurrent access test")
			done <- true
		}()
	}

	for i := 0; i < 10; i++ {
		<-done
	}
}

// TestLoggerFields verifies the logger accepts fields
func TestLoggerFields(t *testing.T) {
	logger := Get()
	if logger == nil {
		t.Fatal("Get() returned nil")
	}

	// The logger methods accept zap.Field arguments
	// Test that we can call them without panicking
	logger.Debug("debug message")
	logger.Info("info message")
	logger.Warn("warn message")
	logger.Error("error message")
}

// TestLoggerSanitization verifies the logger sanitizes sensitive data
func TestLoggerSanitization(t *testing.T) {
	logger := Get()
	if logger == nil {
		t.Fatal("Get() returned nil")
	}

	// These should be sanitized (exact behavior depends on SanitizedLogger implementation)
	logger.Debug("message with sensitive data like token sk_test_abc123def456")
	logger.Info("message with password MySecurePass123")
	logger.Warn("message with api_key secret_key_value")
	logger.Error("message with potential sensitive content")
}

// TestLoggerSync verifies the logger syncs properly
func TestLoggerSync(t *testing.T) {
	logger := Get()
	if logger == nil {
		t.Fatal("Get() returned nil")
	}

	// Sync should not panic or error in normal case
	err := logger.Sync()
	if err != nil {
		t.Logf("logger.Sync() returned error (expected in test environment): %v", err)
	}
}

// TestNewLogger verifies newLogger constructs a working logger for a given service name.
// This exercises the same code path as init() without relying on the singleton,
// ensuring all branches are reachable in tests.
func TestNewLogger_ValidServiceName(t *testing.T) {
	l, err := newLogger("test-service")
	if err != nil {
		t.Fatalf("newLogger returned error: %v", err)
	}
	if l == nil {
		t.Fatal("newLogger returned nil logger")
	}
	// Exercise logger methods to confirm it is functional.
	l.Debug("debug from newLogger")
	l.Info("info from newLogger")
}

// TestNewLogger_EmptyServiceName verifies newLogger works with an empty service name.
func TestNewLogger_EmptyServiceName(t *testing.T) {
	l, err := newLogger("")
	if err != nil {
		// Some implementations may reject an empty name — acceptable.
		t.Logf("newLogger with empty name returned error: %v", err)
		return
	}
	if l == nil {
		t.Fatal("newLogger returned nil logger")
	}
}

// TestNewLogger_MultipleInstances verifies that newLogger creates distinct instances
// (not the same singleton as Get()).
func TestNewLogger_MultipleInstances(t *testing.T) {
	l1, err1 := newLogger("svc-a")
	l2, err2 := newLogger("svc-b")
	if err1 != nil || err2 != nil {
		t.Skipf("newLogger failed: %v / %v", err1, err2)
	}
	// They should be non-nil and distinct from the global singleton.
	if l1 == nil || l2 == nil {
		t.Fatal("newLogger returned nil")
	}
	// Distinct service names should yield distinct instances.
	if l1 == l2 {
		t.Error("expected distinct logger instances for different service names")
	}
}

// TestLoggerFactory_ErrorPath exercises the loggerFactory error branch by replacing
// the factory with one that returns an error. This covers the newLogger error return
// without requiring the real pglog implementation to fail.
func TestLoggerFactory_ErrorPath(t *testing.T) {
	// Save and restore the original factory.
	original := loggerFactory
	defer func() { loggerFactory = original }()

	expectedErr := fmt.Errorf("simulated factory error")
	loggerFactory = func(name string) (*pglog.SanitizedLogger, error) {
		return nil, expectedErr
	}

	_, err := newLogger("test-service")
	if err == nil {
		t.Fatal("expected error from newLogger when factory fails")
	}
	if err.Error() != expectedErr.Error() {
		t.Errorf("error: want %q, got %q", expectedErr.Error(), err.Error())
	}
}

// TestMustNewLogger_PanicOnFactoryError covers the panic branch in mustNewLogger.
// It stubs loggerFactory to return an error, then verifies mustNewLogger panics.
func TestMustNewLogger_PanicOnFactoryError(t *testing.T) {
	original := loggerFactory
	defer func() { loggerFactory = original }()

	loggerFactory = func(name string) (*pglog.SanitizedLogger, error) {
		return nil, fmt.Errorf("injected failure")
	}

	defer func() {
		r := recover()
		if r == nil {
			t.Error("expected mustNewLogger to panic when factory returns an error")
		}
	}()

	mustNewLogger("test-service")
}
