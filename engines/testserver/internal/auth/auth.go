package auth

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"strings"

	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
)

type contextKey string

const (
	UserContextKey contextKey = "user"
)

// AuthDB is satisfied by *database.DB and allows test injection.
type AuthDB interface {
	ValidateJWT(tokenHash string) (*database.User, error)
	ValidateAPIKey(apiKey string) (*database.User, error)
}

type Authenticator struct {
	db          AuthDB
	authEnabled bool
}

// New creates an Authenticator backed by a real *database.DB.
func New(db *database.DB, authEnabled bool) *Authenticator {
	return &Authenticator{
		db:          db,
		authEnabled: authEnabled,
	}
}

// NewWithAuthDB creates an Authenticator backed by any AuthDB implementation.
// This is used in tests to inject a mock auth store.
func NewWithAuthDB(db AuthDB, authEnabled bool) *Authenticator {
	return &Authenticator{
		db:          db,
		authEnabled: authEnabled,
	}
}

func (a *Authenticator) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !a.authEnabled {
			next.ServeHTTP(w, r)
			return
		}

		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, "Authorization required", http.StatusUnauthorized)
			return
		}

		var user *database.User
		var err error

		if strings.HasPrefix(authHeader, "Bearer ") {
			token := strings.TrimPrefix(authHeader, "Bearer ")
			tokenHash := hashString(token)
			user, err = a.db.ValidateJWT(tokenHash)
		} else if strings.HasPrefix(authHeader, "ApiKey ") {
			apiKey := strings.TrimPrefix(authHeader, "ApiKey ")
			user, err = a.db.ValidateAPIKey(apiKey)
		} else {
			http.Error(w, "Invalid authorization format", http.StatusUnauthorized)
			return
		}

		if err != nil {
			http.Error(w, "Invalid credentials", http.StatusUnauthorized)
			return
		}

		ctx := context.WithValue(r.Context(), UserContextKey, user)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func GetUser(ctx context.Context) *database.User {
	if user, ok := ctx.Value(UserContextKey).(*database.User); ok {
		return user
	}
	return nil
}

func hashString(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

func ValidateServerKey(providedKey, expectedKey string) error {
	providedHash := hashString(providedKey)
	expectedHash := hashString(expectedKey)

	if providedHash != expectedHash {
		return fmt.Errorf("invalid server key")
	}
	return nil
}
