package auth

import (
    "crypto/rsa"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "time"

    "github.com/golang-jwt/jwt/v5"
    log "github.com/sirupsen/logrus"
)

// JWTProvider implements JWT-based authentication for the headend proxy
type JWTProvider struct {
    managerURL    string
    publicKey     *rsa.PublicKey
    publicKeyPEM  []byte
    client        *http.Client
    lastKeyFetch  time.Time
}

// NewJWTProvider creates a new JWT authentication provider
func NewJWTProvider(managerURL, publicKeyPath string) (Provider, error) {
    provider := &JWTProvider{
        managerURL: managerURL,
        client: &http.Client{
            Timeout: 30 * time.Second,
        },
    }
    
    // Fetch public key from manager
    if err := provider.fetchPublicKey(); err != nil {
        return nil, fmt.Errorf("failed to fetch public key: %w", err)
    }
    
    log.Info("JWT provider initialized successfully")
    return provider, nil
}

func (j *JWTProvider) fetchPublicKey() error {
    url := j.managerURL + "/api/v1/auth/public-key"
    
    resp, err := j.client.Get(url)
    if err != nil {
        return fmt.Errorf("failed to fetch public key: %w", err)
    }
    defer resp.Body.Close()
    
    if resp.StatusCode != http.StatusOK {
        return fmt.Errorf("manager returned status %d", resp.StatusCode)
    }
    
    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return fmt.Errorf("failed to read response: %w", err)
    }
    
    var keyResponse struct {
        PublicKey string `json:"public_key"`
        Algorithm string `json:"algorithm"`
    }
    
    if err := json.Unmarshal(body, &keyResponse); err != nil {
        return fmt.Errorf("failed to parse response: %w", err)
    }
    
    // Parse the RSA public key
    publicKey, err := jwt.ParseRSAPublicKeyFromPEM([]byte(keyResponse.PublicKey))
    if err != nil {
        return fmt.Errorf("failed to parse RSA public key: %w", err)
    }
    
    j.publicKey = publicKey
    j.publicKeyPEM = []byte(keyResponse.PublicKey)
    j.lastKeyFetch = time.Now()
    
    log.Info("Successfully fetched public key from manager")
    return nil
}

func (j *JWTProvider) ValidateToken(tokenString string) (*User, error) {
    // Refresh public key periodically
    if time.Since(j.lastKeyFetch) > 1*time.Hour {
        if err := j.fetchPublicKey(); err != nil {
            log.Warnf("Failed to refresh public key: %v", err)
        }
    }
    
    // Parse and validate the token
    token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
        // Validate signing method
        if _, ok := token.Method.(*jwt.SigningMethodRSA); !ok {
            return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
        }
        return j.publicKey, nil
    })
    
    if err != nil {
        return nil, fmt.Errorf("token validation failed: %w", err)
    }
    
    if !token.Valid {
        return nil, fmt.Errorf("invalid token")
    }
    
    // Extract claims
    claims, ok := token.Claims.(jwt.MapClaims)
    if !ok {
        return nil, fmt.Errorf("invalid token claims")
    }
    
    // Validate token type
    tokenType, _ := claims["type"].(string)
    if tokenType != "access" {
        return nil, fmt.Errorf("invalid token type: %s", tokenType)
    }
    
    // Extract user information
    nodeID, _ := claims["sub"].(string)
    nodeType, _ := claims["node_type"].(string)
    permissions := []string{}
    
    if permsInterface, ok := claims["permissions"].([]interface{}); ok {
        for _, perm := range permsInterface {
            if permStr, ok := perm.(string); ok {
                permissions = append(permissions, permStr)
            }
        }
    }
    
    // Extract metadata
    metadata := make(map[string]interface{})
    if metaInterface, ok := claims["metadata"].(map[string]interface{}); ok {
        metadata = metaInterface
    }
    
    user := &User{
        ID:          nodeID,
        Username:    fmt.Sprintf("%s-%s", nodeType, nodeID),
        Email:       fmt.Sprintf("%s@sasewaddle.local", nodeID),
        Groups:      []string{nodeType},
        Permissions: permissions,
        Metadata:    metadata,
    }
    
    return user, nil
}

func (j *JWTProvider) LoginHandler() func(interface{}) {
    return func(c interface{}) {
        // For JWT provider, login is handled by the manager service
        // This endpoint returns information about JWT authentication
        response := map[string]interface{}{
            "auth_type": "jwt",
            "message":   "JWT authentication managed by SASEWaddle Manager Service",
            "endpoints": map[string]string{
                "token":    j.managerURL + "/api/v1/auth/token",
                "refresh":  j.managerURL + "/api/v1/auth/refresh",
                "validate": j.managerURL + "/api/v1/auth/validate",
            },
        }
        
        // This would need to be adapted based on the web framework being used
        // For now, it's a placeholder that would need gin.Context type assertion
        log.Info("JWT login info requested")
        _ = response // Placeholder to avoid unused variable error
    }
}

func (j *JWTProvider) CallbackHandler() func(interface{}) {
    return func(c interface{}) {
        // JWT doesn't use callback - this is a no-op
        log.Info("JWT callback requested (no-op)")
    }
}

func (j *JWTProvider) LogoutHandler() func(interface{}) {
    return func(c interface{}) {
        // For JWT, logout means token revocation at the manager
        log.Info("JWT logout requested")
        // Would need to implement token revocation call to manager
    }
}

func (j *JWTProvider) GetUserInfo(userID string) (*User, error) {
    // For JWT, user info is embedded in the token
    return nil, fmt.Errorf("user info retrieval not supported for JWT provider - info is in token")
}