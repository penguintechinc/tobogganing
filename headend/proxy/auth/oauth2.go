package auth

import (
    "context"
    "encoding/json"
    "fmt"
    "net/http"
    "strings"
    "time"

    "github.com/coreos/go-oidc/v3/oidc"
    "github.com/gin-gonic/gin"
    "github.com/golang-jwt/jwt/v5"
    log "github.com/sirupsen/logrus"
    "golang.org/x/oauth2"
)

type OAuth2Provider struct {
    config       *oauth2.Config
    oidcProvider *oidc.Provider
    verifier     *oidc.IDTokenVerifier
    issuer       string
    clientID     string
}

func NewOAuth2Provider(issuer, clientID, clientSecret string) (*OAuth2Provider, error) {
    ctx := context.Background()
    
    provider, err := oidc.NewProvider(ctx, issuer)
    if err != nil {
        return nil, fmt.Errorf("failed to get provider: %w", err)
    }
    
    config := &oauth2.Config{
        ClientID:     clientID,
        ClientSecret: clientSecret,
        Endpoint:     provider.Endpoint(),
        RedirectURL:  "https://localhost:8443/auth/callback",
        Scopes:       []string{oidc.ScopeOpenID, "profile", "email", "groups"},
    }
    
    verifier := provider.Verifier(&oidc.Config{
        ClientID: clientID,
    })
    
    return &OAuth2Provider{
        config:       config,
        oidcProvider: provider,
        verifier:     verifier,
        issuer:       issuer,
        clientID:     clientID,
    }, nil
}

func (p *OAuth2Provider) LoginHandler() gin.HandlerFunc {
    return func(c *gin.Context) {
        state := generateState()
        c.SetCookie("oauth_state", state, 300, "/", "", true, true)
        
        url := p.config.AuthCodeURL(state)
        c.Redirect(http.StatusTemporaryRedirect, url)
    }
}

func (p *OAuth2Provider) CallbackHandler() gin.HandlerFunc {
    return func(c *gin.Context) {
        state, err := c.Cookie("oauth_state")
        if err != nil {
            c.JSON(http.StatusBadRequest, gin.H{"error": "state not found"})
            return
        }
        
        if c.Query("state") != state {
            c.JSON(http.StatusBadRequest, gin.H{"error": "state mismatch"})
            return
        }
        
        code := c.Query("code")
        if code == "" {
            c.JSON(http.StatusBadRequest, gin.H{"error": "code not found"})
            return
        }
        
        ctx := context.Background()
        token, err := p.config.Exchange(ctx, code)
        if err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to exchange token"})
            return
        }
        
        rawIDToken, ok := token.Extra("id_token").(string)
        if !ok {
            c.JSON(http.StatusInternalServerError, gin.H{"error": "no id_token"})
            return
        }
        
        idToken, err := p.verifier.Verify(ctx, rawIDToken)
        if err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to verify id_token"})
            return
        }
        
        var claims struct {
            Email    string   `json:"email"`
            Name     string   `json:"name"`
            Subject  string   `json:"sub"`
            Groups   []string `json:"groups"`
            Verified bool     `json:"email_verified"`
        }
        
        if err := idToken.Claims(&claims); err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to parse claims"})
            return
        }
        
        // Create session token
        sessionToken := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
            "sub":    claims.Subject,
            "email":  claims.Email,
            "name":   claims.Name,
            "groups": claims.Groups,
            "exp":    time.Now().Add(24 * time.Hour).Unix(),
        })
        
        tokenString, err := sessionToken.SignedString([]byte(p.clientID))
        if err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create session"})
            return
        }
        
        c.SetCookie("session_token", tokenString, 86400, "/", "", true, true)
        c.Redirect(http.StatusTemporaryRedirect, "/")
    }
}

func (p *OAuth2Provider) LogoutHandler() gin.HandlerFunc {
    return func(c *gin.Context) {
        c.SetCookie("session_token", "", -1, "/", "", true, true)
        c.JSON(http.StatusOK, gin.H{"message": "logged out"})
    }
}

func (p *OAuth2Provider) ValidateToken(tokenString string) (*User, error) {
    token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
        if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
            return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
        }
        return []byte(p.clientID), nil
    })
    
    if err != nil {
        return nil, err
    }
    
    if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
        groups := []string{}
        if g, ok := claims["groups"].([]interface{}); ok {
            for _, group := range g {
                if s, ok := group.(string); ok {
                    groups = append(groups, s)
                }
            }
        }
        
        return &User{
            ID:     claims["sub"].(string),
            Email:  claims["email"].(string),
            Name:   claims["name"].(string),
            Groups: groups,
        }, nil
    }
    
    return nil, fmt.Errorf("invalid token")
}

func (p *OAuth2Provider) GetUser(c *gin.Context) (*User, error) {
    // Check Bearer token first
    authHeader := c.GetHeader("Authorization")
    if authHeader != "" && strings.HasPrefix(authHeader, "Bearer ") {
        token := strings.TrimPrefix(authHeader, "Bearer ")
        return p.ValidateToken(token)
    }
    
    // Check session cookie
    cookie, err := c.Cookie("session_token")
    if err != nil {
        return nil, fmt.Errorf("no authentication found")
    }
    
    return p.ValidateToken(cookie)
}

func generateState() string {
    // In production, use a cryptographically secure random generator
    return fmt.Sprintf("%d", time.Now().UnixNano())
}