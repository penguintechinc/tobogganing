// Package middleware implements HTTP middleware components for the SASEWaddle headend proxy.
//
// This file provides authentication middleware that implements SASEWaddle's
// dual authentication architecture:
// 1. X.509 client certificate validation (handled at TLS layer)
// 2. JWT/SSO token validation (handled by middleware)
//
// The middleware integrates with various authentication providers (JWT, SAML2, OAuth2)
// and enforces access controls before requests are proxied to backend services.
// All authentication events are logged for security auditing.
package middleware

import (
    "net/http"
    "strings"

    "github.com/gin-gonic/gin"
    log "github.com/sirupsen/logrus"

    "github.com/sasewaddle/headend/proxy/auth"
)

// AuthRequired middleware validates both certificate and JWT/SSO authentication
// This implements the dual authentication architecture:
// 1. Client certificate (handled at TLS layer)
// 2. JWT/SSO token (handled here)
func AuthRequired(authProvider auth.Provider) gin.HandlerFunc {
    return func(c *gin.Context) {
        // Step 1: Verify client certificate (already handled by TLS)
        // The certificate validation happens at the TLS layer
        
        // Step 2: Verify JWT or SSO authentication  
        authHeader := c.GetHeader("Authorization")
        if authHeader == "" {
            log.Warn("Missing Authorization header")
            c.JSON(http.StatusUnauthorized, gin.H{
                "error": "Authorization required",
                "message": "Both client certificate and JWT/SSO authentication required",
            })
            c.Abort()
            return
        }
        
        var token string
        if strings.HasPrefix(authHeader, "Bearer ") {
            token = authHeader[7:] // Remove 'Bearer ' prefix
        } else {
            log.Warn("Invalid Authorization header format")
            c.JSON(http.StatusUnauthorized, gin.H{
                "error": "Invalid authorization format", 
                "message": "Expected 'Bearer <token>'",
            })
            c.Abort()
            return
        }
        
        // Validate the token using the configured auth provider (JWT/SSO)
        user, err := authProvider.ValidateToken(token)
        if err != nil {
            log.Errorf("Authentication failed: %v", err)
            c.JSON(http.StatusUnauthorized, gin.H{
                "error": "Authentication failed",
                "message": err.Error(),
            })
            c.Abort()
            return
        }
        
        // Store user information in context
        c.Set("user", user)
        c.Set("user_id", user.ID)
        
        // Extract permissions from metadata
        if permissions, ok := user.Metadata["permissions"]; ok {
            c.Set("permissions", permissions)
        }
        
        log.Infof("User authenticated: %s (name: %s)", user.ID, user.Name)
        c.Next()
    }
}

// PermissionRequired middleware checks if user has required permissions
func PermissionRequired(requiredPermissions ...string) gin.HandlerFunc {
    return func(c *gin.Context) {
        userPerms, exists := c.Get("permissions")
        if !exists {
            c.JSON(http.StatusForbidden, gin.H{
                "error": "No permissions found",
                "message": "User authentication required",
            })
            c.Abort()
            return
        }
        
        permissions, ok := userPerms.([]string)
        if !ok {
            c.JSON(http.StatusForbidden, gin.H{
                "error": "Invalid permissions format",
            })
            c.Abort()
            return
        }
        
        // Check if user has required permissions
        for _, required := range requiredPermissions {
            found := false
            for _, userPerm := range permissions {
                if userPerm == required {
                    found = true
                    break
                }
            }
            if !found {
                log.Warnf("User missing required permission: %s", required)
                c.JSON(http.StatusForbidden, gin.H{
                    "error": "Insufficient permissions",
                    "message": "Missing required permission: " + required,
                })
                c.Abort()
                return
            }
        }
        
        c.Next()
    }
}

// CertificateInfo extracts certificate information from TLS connection
func CertificateInfo() gin.HandlerFunc {
    return func(c *gin.Context) {
        if c.Request.TLS != nil && len(c.Request.TLS.PeerCertificates) > 0 {
            cert := c.Request.TLS.PeerCertificates[0]
            
            // Store certificate information in context
            c.Set("client_cert_subject", cert.Subject.String())
            c.Set("client_cert_serial", cert.SerialNumber.String())
            c.Set("client_cert_valid", true)
            
            log.Infof("Client certificate validated: %s", cert.Subject.CommonName)
        } else {
            c.Set("client_cert_valid", false)
            log.Warn("No client certificate provided")
        }
        
        c.Next()
    }
}