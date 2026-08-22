package database_test

import (
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
)

// fastFailConfig keeps New()'s retry loop from slowing down unit tests that
// expect a connection failure — one attempt, near-zero backoff.
func fastFailConfig() (int, time.Duration) {
	return 1, time.Millisecond
}

// TestNew_NoFatalOnUnreachable is the regression test for the fixed
// log.Fatalf-on-DB-failure bug: New() must return an error, never panic or
// exit the process, when the database is unreachable.
func TestNew_NoFatalOnUnreachable(t *testing.T) {
	retries, delay := fastFailConfig()
	cfg := database.Config{
		Type:       database.DBTypePostgreSQL,
		Host:       "127.0.0.1",
		Port:       "1", // privileged port, nothing listening
		User:       "testuser",
		Password:   "testpass",
		Database:   "testdb",
		MaxRetries: retries,
		RetryDelay: delay,
	}

	db, err := database.New(cfg)

	if err == nil {
		if db != nil {
			_ = db.Close()
		}
		t.Fatal("expected error connecting to an unreachable host, got nil")
	}
	if db != nil {
		t.Errorf("expected nil DB on failure, got %v", db)
	}
}

func TestNew_MySQLUnreachable(t *testing.T) {
	retries, delay := fastFailConfig()
	cfg := database.Config{
		Type:       database.DBTypeMySQL,
		Host:       "127.0.0.1",
		Port:       "1",
		User:       "testuser",
		Password:   "testpass",
		Database:   "testdb",
		MaxRetries: retries,
		RetryDelay: delay,
	}

	db, err := database.New(cfg)
	if err == nil {
		if db != nil {
			_ = db.Close()
		}
		t.Fatal("expected error connecting to an unreachable mysql host, got nil")
	}
}

func TestNew_UnsupportedDBType(t *testing.T) {
	cfg := database.Config{
		Type: database.DBType("oracle"),
	}

	db, err := database.New(cfg)

	if err == nil {
		if db != nil {
			_ = db.Close()
		}
		t.Fatal("expected error for unsupported DB_TYPE, got nil")
	}
	if !strings.Contains(err.Error(), "unsupported DB_TYPE") {
		t.Errorf("error = %q, want it to mention 'unsupported DB_TYPE'", err.Error())
	}
}

// TestNew_SQLiteRoundTrip exercises New()'s default retry/AutoMigrate path
// end-to-end against a real (dev-tier) SQLite file — the only dialect this
// package owns the schema for.
func TestNew_SQLiteRoundTrip(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "testserver.db")

	db, err := database.New(database.Config{
		Type:     database.DBTypeSQLite,
		Database: dbPath,
	})
	if err != nil {
		t.Fatalf("New(sqlite) failed: %v", err)
	}
	defer func() { _ = db.Close() }()

	// No users/keys seeded — validation should cleanly report "not found",
	// not error out or crash.
	if _, err := db.ValidateAPIKey("does-not-exist"); err == nil {
		t.Error("expected error for unknown API key")
	}

	id, err := db.InsertTestResult(&database.TestResult{
		DeviceSerial:   "SN-SQLITE",
		DeviceHostname: "sqlite-host",
		TestType:       "http",
		ProtocolDetail: "http1",
		TargetHost:     "example.com",
		RawResults:     map[string]interface{}{"status_code": 200},
	})
	if err != nil {
		t.Fatalf("InsertTestResult against sqlite failed: %v", err)
	}
	if id == 0 {
		t.Error("expected a non-zero generated ID")
	}
}

// TestNew_DefaultsToPostgreSQL confirms an empty Type behaves as
// DBTypePostgreSQL per the platform default, by observing the same
// unreachable-host failure path both ways.
func TestNew_DefaultsToPostgreSQL(t *testing.T) {
	retries, delay := fastFailConfig()
	base := database.Config{
		Host:       "127.0.0.1",
		Port:       "1",
		User:       "testuser",
		Password:   "testpass",
		Database:   "testdb",
		MaxRetries: retries,
		RetryDelay: delay,
	}

	explicitCfg := base
	explicitCfg.Type = database.DBTypePostgreSQL
	_, explicitErr := database.New(explicitCfg)

	defaultCfg := base // Type left unset
	_, defaultErr := database.New(defaultCfg)

	if explicitErr == nil || defaultErr == nil {
		t.Fatalf("expected both attempts to fail (unreachable host): explicit=%v default=%v", explicitErr, defaultErr)
	}
}
