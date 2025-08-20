package auth

import (
    "encoding/json"
    "fmt"
    "net/http"
    "strings"
    "time"

    "github.com/golang-jwt/jwt/v5"
)

// Manager handles authentication operations for the native client
type Manager struct {
    managerURL string
    httpClient *http.Client
}

// TokenInfo holds JWT token information
type TokenInfo struct {
    AccessToken  string    `json:"access_token"`
    RefreshToken string    `json:"refresh_token"`
    ExpiresAt    time.Time `json:"expires_at"`
    TokenType    string    `json:"token_type"`
}

// New creates a new authentication manager
func New(managerURL string) (*Manager, error) {
    return &Manager{
        managerURL: managerURL,
        httpClient: &http.Client{
            Timeout: 30 * time.Second,
        },
    }, nil
}

// GetToken obtains a JWT token for the given node
func (a *Manager) GetToken(nodeID, nodeType, apiKey string) (*TokenInfo, error) {
    reqBody := map[string]string{
        "node_id":   nodeID,
        "node_type": nodeType,
        "api_key":   apiKey,
    }

    jsonData, _ := json.Marshal(reqBody)
    
    req, err := http.NewRequest("POST", a.managerURL+"/api/v1/auth/token", strings.NewReader(string(jsonData)))
    if err != nil {
        return nil, fmt.Errorf("failed to create request: %w", err)
    }

    req.Header.Set("Content-Type", "application/json")

    resp, err := a.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("token request failed: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("token request failed with status %d", resp.StatusCode)
    }

    var tokenResp TokenInfo
    if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
        return nil, fmt.Errorf("failed to parse token response: %w", err)
    }

    // Parse expires_at from token if not provided
    if tokenResp.ExpiresAt.IsZero() && tokenResp.AccessToken != "" {
        if exp, err := a.getTokenExpiry(tokenResp.AccessToken); err == nil {
            tokenResp.ExpiresAt = exp
        }
    }

    return &tokenResp, nil
}

// RefreshToken refreshes an access token using a refresh token
func (a *Manager) RefreshToken(refreshToken string) (*TokenInfo, error) {
    reqBody := map[string]string{
        "refresh_token": refreshToken,
    }

    jsonData, _ := json.Marshal(reqBody)
    
    req, err := http.NewRequest("POST", a.managerURL+"/api/v1/auth/refresh", strings.NewReader(string(jsonData)))
    if err != nil {
        return nil, fmt.Errorf("failed to create request: %w", err)
    }

    req.Header.Set("Content-Type", "application/json")

    resp, err := a.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("refresh request failed: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("refresh request failed with status %d", resp.StatusCode)
    }

    var tokenResp TokenInfo
    if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
        return nil, fmt.Errorf("failed to parse refresh response: %w", err)
    }

    // Parse expires_at from token if not provided
    if tokenResp.ExpiresAt.IsZero() && tokenResp.AccessToken != "" {
        if exp, err := a.getTokenExpiry(tokenResp.AccessToken); err == nil {
            tokenResp.ExpiresAt = exp
        }
    }

    return &tokenResp, nil
}

// ValidateToken validates a JWT token with the manager service
func (a *Manager) ValidateToken(token string) (bool, error) {
    req, err := http.NewRequest("POST", a.managerURL+"/api/v1/auth/validate", nil)
    if err != nil {
        return false, fmt.Errorf("failed to create request: %w", err)
    }

    req.Header.Set("Authorization", "Bearer "+token)

    resp, err := a.httpClient.Do(req)
    if err != nil {
        return false, fmt.Errorf("validation request failed: %w", err)
    }
    defer resp.Body.Close()

    return resp.StatusCode == http.StatusOK, nil
}

// IsTokenExpired checks if a token is expired or will expire soon
func (a *Manager) IsTokenExpired(token string, threshold time.Duration) bool {
    expiry, err := a.getTokenExpiry(token)
    if err != nil {
        return true // Assume expired if we can't parse
    }

    return time.Until(expiry) < threshold
}

// getTokenExpiry extracts expiry time from a JWT token
func (a *Manager) getTokenExpiry(tokenString string) (time.Time, error) {
    token, _, err := new(jwt.Parser).ParseUnverified(tokenString, jwt.MapClaims{})
    if err != nil {
        return time.Time{}, fmt.Errorf("failed to parse token: %w", err)
    }

    if claims, ok := token.Claims.(jwt.MapClaims); ok {
        if exp, ok := claims["exp"].(float64); ok {
            return time.Unix(int64(exp), 0), nil
        }
    }

    return time.Time{}, fmt.Errorf("no expiry found in token")
}

// RevokeToken revokes a JWT token
func (a *Manager) RevokeToken(token string) error {
    // Extract JTI from token
    parsedToken, _, err := new(jwt.Parser).ParseUnverified(token, jwt.MapClaims{})
    if err != nil {
        return fmt.Errorf("failed to parse token: %w", err)
    }

    claims, ok := parsedToken.Claims.(jwt.MapClaims)
    if !ok {
        return fmt.Errorf("invalid token claims")
    }

    jti, ok := claims["jti"].(string)
    if !ok {
        return fmt.Errorf("no JTI found in token")
    }

    reqBody := map[string]string{
        "jti": jti,
    }

    jsonData, _ := json.Marshal(reqBody)
    
    req, err := http.NewRequest("POST", a.managerURL+"/api/v1/auth/revoke", strings.NewReader(string(jsonData)))
    if err != nil {
        return fmt.Errorf("failed to create request: %w", err)
    }

    req.Header.Set("Content-Type", "application/json")

    resp, err := a.httpClient.Do(req)
    if err != nil {
        return fmt.Errorf("revoke request failed: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return fmt.Errorf("revoke request failed with status %d", resp.StatusCode)
    }

    return nil
}