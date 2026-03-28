// Package middleware implements HTTP middleware components for the Tobogganing hub-router proxy.
//
// This file provides authentication middleware built on go-aaa (penguin-libs).
// It implements Tobogganing's dual authentication architecture:
//  1. X.509 client certificate validation (handled at TLS layer — not this file)
//  2. OIDC token validation via authn.OIDCRelyingParty (handled here)
//
// Scope-based authorization is enforced via authz.HasAllScopes.
// All authentication events are logged for security auditing.
package middleware

import (
	"context"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/penguintechinc/penguin-libs/packages/go-aaa/authn"
	"github.com/penguintechinc/penguin-libs/packages/go-aaa/authz"
	log "github.com/sirupsen/logrus"
)

// NewAuthMiddleware returns a gin.HandlerFunc that validates Bearer tokens using the
// provided OIDCRelyingParty. On success it stores *authn.Claims under the key "claims"
// and the tenant string under "tenant" in the gin context.
//
// If rp is nil (e.g. OIDC_ISSUER_URL was not set and dev mode is active) the middleware
// logs a warning and passes the request through without validating the token — this is
// intentional for local development only and must never be used in production.
func NewAuthMiddleware(rp *authn.OIDCRelyingParty) gin.HandlerFunc {
	if rp == nil {
		log.Warn("auth: OIDC relying party is nil — token validation is DISABLED (dev mode only)")
	}
	return func(c *gin.Context) {
		// TLS certificate validation is handled at the TLS layer.
		// Here we only validate the JWT Bearer token.

		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			log.Warn("auth: missing Authorization header")
			c.JSON(http.StatusUnauthorized, gin.H{
				"error":   "Authorization required",
				"message": "Bearer token required",
			})
			c.Abort()
			return
		}

		if !strings.HasPrefix(authHeader, "Bearer ") {
			log.Warn("auth: invalid Authorization header format")
			c.JSON(http.StatusUnauthorized, gin.H{
				"error":   "Invalid authorization format",
				"message": "Expected 'Bearer <token>'",
			})
			c.Abort()
			return
		}

		rawToken := authHeader[len("Bearer "):]

		// Dev mode: skip validation when no RP is configured.
		if rp == nil {
			log.Warn("auth: skipping token validation (dev mode — no OIDC provider configured)")
			c.Next()
			return
		}

		claims, err := rp.ValidateToken(context.Background(), rawToken)
		if err != nil {
			log.Errorf("auth: token validation failed: %v", err)
			c.JSON(http.StatusUnauthorized, gin.H{
				"error":   "Authentication failed",
				"message": err.Error(),
			})
			c.Abort()
			return
		}

		// Store claims and tenant for downstream middleware and handlers.
		c.Set("claims", claims)
		c.Set("tenant", claims.Tenant)

		log.Infof("auth: subject authenticated: %s (tenant: %s)", claims.Sub, claims.Tenant)
		c.Next()
	}
}

// ScopeRequired returns a gin.HandlerFunc that checks whether the *authn.Claims stored
// by NewAuthMiddleware contain all of the required scopes. If any scope is missing the
// request is rejected with 403 Forbidden.
func ScopeRequired(requiredScopes ...string) gin.HandlerFunc {
	return func(c *gin.Context) {
		raw, exists := c.Get("claims")
		if !exists {
			c.JSON(http.StatusForbidden, gin.H{
				"error":   "No claims found",
				"message": "Authentication required before scope check",
			})
			c.Abort()
			return
		}

		claims, ok := raw.(*authn.Claims)
		if !ok {
			c.JSON(http.StatusForbidden, gin.H{
				"error": "Invalid claims type in context",
			})
			c.Abort()
			return
		}

		if !authz.HasAllScopes(claims.Scope, requiredScopes...) {
			log.Warnf("auth: subject %s missing required scopes %v (has: %v)", claims.Sub, requiredScopes, claims.Scope)
			c.JSON(http.StatusForbidden, gin.H{
				"error":   "Insufficient scope",
				"message": "Missing one or more required scopes",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}

// TenantRequired returns a gin.HandlerFunc that rejects requests where the authenticated
// token carries no tenant claim. This enforces tenant isolation for multi-tenant paths.
func TenantRequired() gin.HandlerFunc {
	return func(c *gin.Context) {
		raw, exists := c.Get("claims")
		if !exists {
			c.JSON(http.StatusForbidden, gin.H{
				"error":   "No claims found",
				"message": "Authentication required before tenant check",
			})
			c.Abort()
			return
		}

		claims, ok := raw.(*authn.Claims)
		if !ok {
			c.JSON(http.StatusForbidden, gin.H{
				"error": "Invalid claims type in context",
			})
			c.Abort()
			return
		}

		if claims.Tenant == "" {
			log.Warnf("auth: subject %s has no tenant claim", claims.Sub)
			c.JSON(http.StatusForbidden, gin.H{
				"error":   "Tenant required",
				"message": "Token must carry a tenant claim",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}

// CertificateInfo extracts certificate information from the TLS connection and stores it
// in the gin context. Certificate validation itself is performed at the TLS layer.
func CertificateInfo() gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.Request.TLS != nil && len(c.Request.TLS.PeerCertificates) > 0 {
			cert := c.Request.TLS.PeerCertificates[0]

			c.Set("client_cert_subject", cert.Subject.String())
			c.Set("client_cert_serial", cert.SerialNumber.String())
			c.Set("client_cert_valid", true)

			log.Infof("auth: client certificate present: %s", cert.Subject.CommonName)
		} else {
			c.Set("client_cert_valid", false)
			log.Warn("auth: no client certificate provided")
		}

		c.Next()
	}
}
