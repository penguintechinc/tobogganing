package auth_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/auth"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
)

// ---------------------------------------------------------------------------
// ValidateServerKey
// ---------------------------------------------------------------------------

func TestValidateServerKey(t *testing.T) {
	tests := []struct {
		name        string
		provided    string
		expected    string
		wantErr     bool
	}{
		{"matching keys", "secret", "secret", false},
		{"empty keys match", "", "", false},
		{"mismatched keys", "wrong", "correct", true},
		{"provided empty expected not", "", "secret", true},
		{"provided not empty expected empty", "secret", "", true},
		{"long matching keys", "a-very-long-api-key-value-123456", "a-very-long-api-key-value-123456", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := auth.ValidateServerKey(tt.provided, tt.expected)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateServerKey(%q, %q) error = %v, wantErr = %v",
					tt.provided, tt.expected, err, tt.wantErr)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// GetUser — with nil context value
// ---------------------------------------------------------------------------

func TestGetUser_NilContext(t *testing.T) {
	ctx := context.Background()
	user := auth.GetUser(ctx)
	if user != nil {
		t.Errorf("GetUser on empty context should return nil, got %v", user)
	}
}

func TestGetUser_WrongType(t *testing.T) {
	// Store a non-*User value under the key — should return nil gracefully
	ctx := context.WithValue(context.Background(), auth.UserContextKey, "not-a-user")
	user := auth.GetUser(ctx)
	if user != nil {
		t.Errorf("GetUser with wrong type should return nil, got %v", user)
	}
}

// ---------------------------------------------------------------------------
// mockAuthDB — test double for auth.AuthDB
// ---------------------------------------------------------------------------

type mockAuthDB struct {
	jwtUser  *database.User
	jwtErr   error
	apiUser  *database.User
	apiErr   error
}

func (m *mockAuthDB) ValidateJWT(_ string) (*database.User, error) {
	return m.jwtUser, m.jwtErr
}

func (m *mockAuthDB) ValidateAPIKey(_ string) (*database.User, error) {
	return m.apiUser, m.apiErr
}

// ---------------------------------------------------------------------------
// Authenticator.Middleware — auth disabled path
// ---------------------------------------------------------------------------

func TestMiddleware_AuthDisabled(t *testing.T) {
	// When auth is disabled the middleware must call next without checking headers.
	// We pass nil for db since it won't be used when authEnabled=false.
	a := auth.New(nil, false)

	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	})

	handler := a.Middleware(next)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if !called {
		t.Error("expected next handler to be called when auth is disabled")
	}
	if rr.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", rr.Code)
	}
}

// ---------------------------------------------------------------------------
// Authenticator.Middleware — missing Authorization header
// ---------------------------------------------------------------------------

func TestMiddleware_AuthEnabled_MissingHeader(t *testing.T) {
	a := auth.New(nil, true)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("next should not be called when auth header is missing")
	})

	handler := a.Middleware(next)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", rr.Code)
	}
}

// ---------------------------------------------------------------------------
// GetUser — with a real user in context
// ---------------------------------------------------------------------------

func TestGetUser_WithUser(t *testing.T) {
	ouid := 42
	expected := &database.User{
		ID:       1,
		Username: "alice",
		Email:    "alice@example.com",
		Role:     "admin",
		OUID:     &ouid,
		IsActive: true,
	}
	ctx := context.WithValue(context.Background(), auth.UserContextKey, expected)
	got := auth.GetUser(ctx)
	if got == nil {
		t.Fatal("expected non-nil user")
	}
	if got.ID != expected.ID {
		t.Errorf("expected ID=%d, got %d", expected.ID, got.ID)
	}
	if got.Username != expected.Username {
		t.Errorf("expected Username=%q, got %q", expected.Username, got.Username)
	}
}

// ---------------------------------------------------------------------------
// Authenticator.Middleware — Bearer token valid
// ---------------------------------------------------------------------------

func TestMiddleware_BearerValid(t *testing.T) {
	user := &database.User{ID: 1, Username: "alice", IsActive: true}
	mockDB := &mockAuthDB{jwtUser: user, jwtErr: nil}
	a := auth.NewWithAuthDB(mockDB, true)

	var gotUser *database.User
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUser = auth.GetUser(r.Context())
		w.WriteHeader(http.StatusOK)
	})

	handler := a.Middleware(next)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer valid-token")
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", rr.Code)
	}
	if gotUser == nil || gotUser.ID != 1 {
		t.Errorf("expected user in context with ID=1, got %v", gotUser)
	}
}

// ---------------------------------------------------------------------------
// Authenticator.Middleware — Bearer token invalid
// ---------------------------------------------------------------------------

func TestMiddleware_BearerInvalid(t *testing.T) {
	mockDB := &mockAuthDB{jwtUser: nil, jwtErr: fmt.Errorf("invalid JWT")}
	a := auth.NewWithAuthDB(mockDB, true)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("next should not be called for invalid JWT")
	})

	handler := a.Middleware(next)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer invalid-token")
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for invalid JWT, got %d", rr.Code)
	}
}

// ---------------------------------------------------------------------------
// Authenticator.Middleware — ApiKey valid
// ---------------------------------------------------------------------------

func TestMiddleware_APIKeyValid(t *testing.T) {
	user := &database.User{ID: 2, Username: "bob", IsActive: true}
	mockDB := &mockAuthDB{apiUser: user, apiErr: nil}
	a := auth.NewWithAuthDB(mockDB, true)

	var gotUser *database.User
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUser = auth.GetUser(r.Context())
		w.WriteHeader(http.StatusOK)
	})

	handler := a.Middleware(next)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "ApiKey my-api-key-123")
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", rr.Code)
	}
	if gotUser == nil || gotUser.ID != 2 {
		t.Errorf("expected user in context with ID=2, got %v", gotUser)
	}
}

// ---------------------------------------------------------------------------
// Authenticator.Middleware — ApiKey invalid
// ---------------------------------------------------------------------------

func TestMiddleware_APIKeyInvalid(t *testing.T) {
	mockDB := &mockAuthDB{apiUser: nil, apiErr: fmt.Errorf("invalid API key")}
	a := auth.NewWithAuthDB(mockDB, true)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("next should not be called for invalid API key")
	})

	handler := a.Middleware(next)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "ApiKey wrong-key")
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for invalid API key, got %d", rr.Code)
	}
}

// ---------------------------------------------------------------------------
// Authenticator.Middleware — invalid Authorization format
// ---------------------------------------------------------------------------

func TestMiddleware_AuthEnabled_InvalidFormat(t *testing.T) {
	a := auth.New(nil, true)

	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("next should not be called with invalid auth format")
	})

	handler := a.Middleware(next)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Basic dXNlcjpwYXNz") // Basic, not Bearer/ApiKey
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for unknown auth scheme, got %d", rr.Code)
	}
}
