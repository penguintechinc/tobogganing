package logger

import (
	"testing"
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
