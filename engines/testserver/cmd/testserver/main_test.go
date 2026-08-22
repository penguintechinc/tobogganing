package main

import (
	"errors"
	"os"
	"testing"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
)

func TestGetEnv_Default(t *testing.T) {
	key := "TESTSERVER_UNSET_VAR_FOR_TEST"
	if err := os.Unsetenv(key); err != nil {
		t.Fatalf("os.Unsetenv(%q) failed: %v", key, err)
	}

	if got := getEnv(key, "fallback"); got != "fallback" {
		t.Errorf("getEnv(%q) = %q, want %q", key, got, "fallback")
	}
}

func TestGetEnv_Override(t *testing.T) {
	key := "TESTSERVER_SET_VAR_FOR_TEST"
	t.Setenv(key, "overridden")

	if got := getEnv(key, "fallback"); got != "overridden" {
		t.Errorf("getEnv(%q) = %q, want %q", key, got, "overridden")
	}
}

// TestSwitchableStore_UnavailableByDefault covers the degrade-gracefully
// path used before the database has connected (or if it never does): every
// call must surface errDBUnavailable rather than touch a nil pointer.
func TestSwitchableStore_UnavailableByDefault(t *testing.T) {
	store := newSwitchableStore()

	if _, err := store.InsertTestResult(nil); !errors.Is(err, errDBUnavailable) {
		t.Errorf("InsertTestResult err = %v, want %v", err, errDBUnavailable)
	}
	if user, err := store.ValidateAPIKey("any-key"); user != nil || !errors.Is(err, errDBUnavailable) {
		t.Errorf("ValidateAPIKey = (%v, %v), want (nil, %v)", user, err, errDBUnavailable)
	}
	if user, err := store.ValidateJWT("any-token"); user != nil || !errors.Is(err, errDBUnavailable) {
		t.Errorf("ValidateJWT = (%v, %v), want (nil, %v)", user, err, errDBUnavailable)
	}
}

// TestSwitchableStore_SwapsToLiveDB covers connectDB's success path: once a
// *database.DB is stored, calls delegate to it instead of returning
// errDBUnavailable.
func TestSwitchableStore_SwapsToLiveDB(t *testing.T) {
	dbPath := t.TempDir() + "/switchable.db"
	db, err := database.New(database.Config{
		Type:     database.DBTypeSQLite,
		Database: dbPath,
	})
	if err != nil {
		t.Fatalf("database.New(sqlite) failed: %v", err)
	}
	defer func() { _ = db.Close() }()

	store := newSwitchableStore()
	store.db.Store(db)

	if _, err := store.ValidateAPIKey("does-not-exist"); err == nil || errors.Is(err, errDBUnavailable) {
		t.Errorf("expected a real (not-found) DB error once swapped in, got %v", err)
	}
}

// TestConnectDB_NeverPanicsOnUnreachableHost is the regression test for the
// fixed log.Fatalf-on-DB-failure bug at the main() call site: connectDB must
// return normally (store stays unavailable) rather than crash the process.
func TestConnectDB_NeverPanicsOnUnreachableHost(t *testing.T) {
	store := newSwitchableStore()
	cfg := database.Config{
		Type:       database.DBTypePostgreSQL,
		Host:       "127.0.0.1",
		Port:       "1",
		Database:   "testdb",
		MaxRetries: 1,
		RetryDelay: 1,
	}

	connectDB(cfg, store) // must not panic/exit

	if db := store.db.Load(); db != nil {
		t.Error("expected store to remain unavailable after a failed connect")
	}
}
