// Package auth implements authentication providers for the SASEWaddle headend proxy.
//
// The auth package provides a unified interface for multiple authentication methods:
// - JWT token-based authentication for API access
// - SAML2 integration with enterprise identity providers
// - OAuth2 support for cloud-based authentication
// - Local user management with secure password hashing
//
// The Provider interface abstracts different authentication mechanisms,
// allowing the proxy to support various enterprise authentication systems
// while maintaining a consistent internal API for user validation and authorization.
package auth

import (
	"fmt"

	"github.com/gin-gonic/gin"
)

type User struct {
	ID       string                 `json:"id"`
	Email    string                 `json:"email"`
	Name     string                 `json:"name"`
	Groups   []string               `json:"groups"`
	Metadata map[string]interface{} `json:"metadata"`
}

type Provider interface {
	LoginHandler() gin.HandlerFunc
	CallbackHandler() gin.HandlerFunc
	LogoutHandler() gin.HandlerFunc
	ValidateToken(token string) (*User, error)
	GetUser(ctx *gin.Context) (*User, error)
}

// minSessionSigningKeyBytes is the minimum acceptable length (in bytes) for the
// proxy session-signing secret. 32 bytes gives an HS256 key at least 256 bits
// of nominal entropy, matching the HMAC-SHA256 output size.
const minSessionSigningKeyBytes = 32

// validateSessionSigningKey enforces that the proxy session-signing secret is
// present and sufficiently high-entropy before it is used to sign or verify
// session JWTs. Session tokens MUST be signed with a dedicated, high-entropy
// server secret (PROXY_SESSION_SIGNING_KEY) — never a value derivable from
// public request data such as an OAuth2 client_id or SAML SP entity ID, both
// of which are exposed in redirect URLs and would let anyone forge a valid
// session token with arbitrary claims.
func validateSessionSigningKey(key string) ([]byte, error) {
	if len(key) < minSessionSigningKeyBytes {
		return nil, fmt.Errorf("session signing key must be set and at least %d bytes (got %d); set PROXY_SESSION_SIGNING_KEY", minSessionSigningKeyBytes, len(key))
	}
	return []byte(key), nil
}
