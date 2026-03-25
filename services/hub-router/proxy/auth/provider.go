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
    "strings"

    "github.com/gin-gonic/gin"
)

type User struct {
    ID       string                 `json:"id"`
    Email    string                 `json:"email"`
    Name     string                 `json:"name"`
    Groups   []string               `json:"groups"`
    Metadata map[string]interface{} `json:"metadata"`
    Tenant   string                 `json:"tenant"`
    Scopes   []string               `json:"scopes"`
    Teams    []string               `json:"teams"`
    Roles    []string               `json:"roles"`
}

// HasScope returns true when the user holds a scope that satisfies the requirement.
// Supports wildcards: "*:read" satisfies "policies:read", "*:*" satisfies everything.
func (u *User) HasScope(required string) bool {
    reqParts := strings.SplitN(required, ":", 2)
    reqResource := reqParts[0]
    reqAction := ""
    if len(reqParts) == 2 {
        reqAction = reqParts[1]
    }

    for _, s := range u.Scopes {
        if s == required {
            return true
        }
        parts := strings.SplitN(s, ":", 2)
        if len(parts) != 2 {
            continue
        }
        resource, action := parts[0], parts[1]

        // "*:*" matches everything
        if resource == "*" && action == "*" {
            return true
        }
        // "*:action" matches any resource with the same action
        if resource == "*" && action == reqAction {
            return true
        }
        // "resource:*" matches any action on the same resource
        if resource == reqResource && action == "*" {
            return true
        }
    }
    return false
}

type Provider interface {
    LoginHandler() gin.HandlerFunc
    CallbackHandler() gin.HandlerFunc
    LogoutHandler() gin.HandlerFunc
    ValidateToken(token string) (*User, error)
    GetUser(ctx *gin.Context) (*User, error)
}