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