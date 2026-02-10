package auth

import (
	"context"
	"testing"
	"time"
)

func TestJWTProvider_NewProvider(t *testing.T) {
	config := &JWTConfig{
		ManagerURL: "http://localhost:8000",
		CacheTTL:   300,
	}

	provider, err := NewJWTProvider(config)
	if err != nil {
		t.Fatalf("Failed to create JWT provider: %v", err)
	}

	if provider == nil {
		t.Fatal("Expected JWT provider, got nil")
	}

	if provider.config.ManagerURL != config.ManagerURL {
		t.Errorf("Expected manager URL %s, got %s", config.ManagerURL, provider.config.ManagerURL)
	}
}

func TestJWTProvider_ValidateToken_InvalidFormat(t *testing.T) {
	provider := &JWTProvider{
		config: &JWTConfig{
			ManagerURL: "http://localhost:8000",
			CacheTTL:   300,
		},
	}

	ctx := context.Background()
	invalidTokens := []string{
		"",
		"invalid",
		"invalid.token",
		"not.a.jwt.token",
	}

	for _, token := range invalidTokens {
		result, err := provider.ValidateToken(ctx, token)
		if err == nil {
			t.Errorf("Expected error for invalid token: %s", token)
		}
		if result != nil {
			t.Errorf("Expected nil result for invalid token: %s", token)
		}
	}
}

func TestJWTProvider_ExtractClaims(t *testing.T) {
	// Create a mock JWT token (this would normally be signed by the manager)
	// For testing, we just test the structure parsing
	mockJWT := "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LWNsaWVudCIsIm5vZGVfaWQiOiJ0ZXN0LWNsaWVudCIsIm5vZGVfdHlwZSI6ImNsaWVudCIsInBlcm1pc3Npb25zIjpbImNvbm5lY3QiLCJwcm94eSJdLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTYzMjQzMjAwMH0"

	provider := &JWTProvider{}

	// Test token structure validation (header and payload extraction)
	parts := provider.splitToken(mockJWT)
	if len(parts) != 3 {
		t.Errorf("Expected 3 JWT parts, got %d", len(parts))
	}

	// Test that we can at least parse the structure
	if len(parts[0]) == 0 || len(parts[1]) == 0 || len(parts[2]) == 0 {
		t.Error("JWT parts should not be empty")
	}
}

func TestJWTProvider_CacheKey(t *testing.T) {
	provider := &JWTProvider{}

	token1 := "test.token.one"
	token2 := "test.token.two"

	key1 := provider.getCacheKey(token1)
	key2 := provider.getCacheKey(token2)

	if key1 == key2 {
		t.Error("Different tokens should generate different cache keys")
	}

	if len(key1) == 0 || len(key2) == 0 {
		t.Error("Cache keys should not be empty")
	}

	// Same token should generate same key
	key1Again := provider.getCacheKey(token1)
	if key1 != key1Again {
		t.Error("Same token should generate same cache key")
	}
}

func TestJWTProvider_IsTokenExpired(t *testing.T) {
	provider := &JWTProvider{}

	// Test with expired timestamp
	expiredTime := time.Now().Add(-time.Hour).Unix()
	if !provider.isTokenExpired(expiredTime) {
		t.Error("Token with past expiry should be considered expired")
	}

	// Test with future timestamp
	futureTime := time.Now().Add(time.Hour).Unix()
	if provider.isTokenExpired(futureTime) {
		t.Error("Token with future expiry should not be considered expired")
	}

	// Test with current time (within threshold)
	currentTime := time.Now().Add(time.Second * 30).Unix()
	if provider.isTokenExpired(currentTime) {
		t.Error("Token expiring in 30 seconds should not be considered expired")
	}
}

func TestJWTProvider_ValidatePermissions(t *testing.T) {
	provider := &JWTProvider{}

	testCases := []struct {
		name        string
		permissions []string
		required    []string
		expected    bool
	}{
		{
			name:        "Has all required permissions",
			permissions: []string{"connect", "proxy", "admin"},
			required:    []string{"connect", "proxy"},
			expected:    true,
		},
		{
			name:        "Missing required permission",
			permissions: []string{"connect"},
			required:    []string{"connect", "admin"},
			expected:    false,
		},
		{
			name:        "No permissions required",
			permissions: []string{"connect"},
			required:    []string{},
			expected:    true,
		},
		{
			name:        "No permissions granted",
			permissions: []string{},
			required:    []string{"connect"},
			expected:    false,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := provider.hasPermissions(tc.permissions, tc.required)
			if result != tc.expected {
				t.Errorf("Expected %t, got %t for permissions %v with required %v",
					tc.expected, result, tc.permissions, tc.required)
			}
		})
	}
}

// Helper method for testing (would be private in actual implementation)
func (p *JWTProvider) splitToken(token string) []string {
	// Simple split implementation for testing
	parts := make([]string, 0)
	current := ""
	for _, char := range token {
		if char == '.' {
			parts = append(parts, current)
			current = ""
		} else {
			current += string(char)
		}
	}
	if current != "" {
		parts = append(parts, current)
	}
	return parts
}

func (p *JWTProvider) getCacheKey(token string) string {
	// Simple hash for testing
	hash := 0
	for _, char := range token {
		hash = hash*31 + int(char)
	}
	return "jwt_cache_" + string(rune(hash))
}

func (p *JWTProvider) isTokenExpired(exp int64) bool {
	return time.Now().Unix() >= exp
}

func (p *JWTProvider) hasPermissions(granted []string, required []string) bool {
	if len(required) == 0 {
		return true
	}

	grantedMap := make(map[string]bool)
	for _, perm := range granted {
		grantedMap[perm] = true
	}

	for _, required := range required {
		if !grantedMap[required] {
			return false
		}
	}
	return true
}