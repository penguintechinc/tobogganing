package crypto

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"fmt"
)

// GenerateToken generates a cryptographically secure random token of the specified byte length.
// Returns hex-encoded string.
func GenerateToken(length int) (string, error) {
	if length <= 0 {
		return "", fmt.Errorf("token length must be positive, got %d", length)
	}

	bytes := make([]byte, length)
	if _, err := rand.Read(bytes); err != nil {
		return "", fmt.Errorf("failed to generate random token: %w", err)
	}

	return hex.EncodeToString(bytes), nil
}

// GenerateURLSafeToken generates a cryptographically secure random token of the specified byte length.
// Returns URL-safe base64 encoded string (without padding).
func GenerateURLSafeToken(length int) (string, error) {
	if length <= 0 {
		return "", fmt.Errorf("token length must be positive, got %d", length)
	}

	bytes := make([]byte, length)
	if _, err := rand.Read(bytes); err != nil {
		return "", fmt.Errorf("failed to generate random token: %w", err)
	}

	return base64.RawURLEncoding.EncodeToString(bytes), nil
}
