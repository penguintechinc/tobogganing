package main

import (
	"errors"
	"net/http"
	"net/http/httptest"
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

// TestParseAllowedOrigins covers the TESTSERVER_ALLOWED_ORIGINS parsing
// used to build the CORS allowlist: comma-separated, whitespace-trimmed,
// empty entries dropped, and an empty/unset input yielding an empty set
// (deny-all — never a wildcard).
func TestParseAllowedOrigins(t *testing.T) {
	tests := []struct {
		name string
		raw  string
		want []string
	}{
		{"empty", "", nil},
		{"single", "https://a.example.com", []string{"https://a.example.com"}},
		{"multiple", "https://a.example.com,https://b.example.com", []string{"https://a.example.com", "https://b.example.com"}},
		{"whitespace and blanks trimmed", " https://a.example.com , , https://b.example.com ", []string{"https://a.example.com", "https://b.example.com"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parseAllowedOrigins(tt.raw)
			if len(got) != len(tt.want) {
				t.Fatalf("parseAllowedOrigins(%q) = %v, want %v", tt.raw, got, tt.want)
			}
			for _, o := range tt.want {
				if !got[o] {
					t.Errorf("parseAllowedOrigins(%q) missing origin %q, got %v", tt.raw, o, got)
				}
			}
		})
	}
}

// TestCORSMiddleware_AllowlistedOriginEchoed is the regression test for the
// wildcard-CORS finding: a request from a configured origin must get that
// exact origin echoed back on Access-Control-Allow-Origin (never "*"), and
// Access-Control-Allow-Credentials must never be set alongside it.
func TestCORSMiddleware_AllowlistedOriginEchoed(t *testing.T) {
	mw := newCORSMiddleware(parseAllowedOrigins("https://allowed.example.com"))
	handler := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/speedtest/info", nil)
	req.Header.Set("Origin", "https://allowed.example.com")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "https://allowed.example.com" {
		t.Errorf("Access-Control-Allow-Origin = %q, want %q", got, "https://allowed.example.com")
	}
	if got := rec.Header().Get("Access-Control-Allow-Credentials"); got != "" {
		t.Errorf("Access-Control-Allow-Credentials = %q, want unset (never paired with an origin allowlist)", got)
	}
}

// TestCORSMiddleware_NonAllowlistedOriginGetsNoWildcard is the primary
// regression test for the wildcard-CORS finding: an origin absent from the
// allowlist must never receive "*", and must not get an
// Access-Control-Allow-Origin header at all — deny by default.
func TestCORSMiddleware_NonAllowlistedOriginGetsNoWildcard(t *testing.T) {
	mw := newCORSMiddleware(parseAllowedOrigins("https://allowed.example.com"))
	handler := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/speedtest/info", nil)
	req.Header.Set("Origin", "https://evil.example.com")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	got := rec.Header().Get("Access-Control-Allow-Origin")
	if got == "*" {
		t.Fatal("Access-Control-Allow-Origin = \"*\", wildcard must never be emitted")
	}
	if got != "" {
		t.Errorf("Access-Control-Allow-Origin = %q, want unset for a non-allowlisted origin", got)
	}
}

// TestCORSMiddleware_EmptyAllowlistDeniesAll covers the deny-by-default
// fallback: with TESTSERVER_ALLOWED_ORIGINS unset (empty allowlist), no
// origin gets a CORS allow header — never a wildcard fallback.
func TestCORSMiddleware_EmptyAllowlistDeniesAll(t *testing.T) {
	mw := newCORSMiddleware(parseAllowedOrigins(""))
	handler := mw(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/speedtest/info", nil)
	req.Header.Set("Origin", "https://anything.example.com")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if got := rec.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Errorf("Access-Control-Allow-Origin = %q, want unset with an empty allowlist", got)
	}
}
