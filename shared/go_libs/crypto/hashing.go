package crypto

import (
	"fmt"

	"golang.org/x/crypto/bcrypt"
)

const (
	// DefaultBcryptCost is the default cost for bcrypt hashing
	DefaultBcryptCost = 12
)

// HashPassword hashes a password using bcrypt with the default cost.
func HashPassword(password string) (string, error) {
	return HashPasswordWithCost(password, DefaultBcryptCost)
}

// HashPasswordWithCost hashes a password using bcrypt with a specified cost.
// Cost should be between 4 and 31 (10-12 recommended for production).
func HashPasswordWithCost(password string, cost int) (string, error) {
	if password == "" {
		return "", fmt.Errorf("password cannot be empty")
	}

	if cost < bcrypt.MinCost || cost > bcrypt.MaxCost {
		return "", fmt.Errorf("invalid bcrypt cost: must be between %d and %d", bcrypt.MinCost, bcrypt.MaxCost)
	}

	hashedBytes, err := bcrypt.GenerateFromPassword([]byte(password), cost)
	if err != nil {
		return "", fmt.Errorf("failed to hash password: %w", err)
	}

	return string(hashedBytes), nil
}

// VerifyPassword verifies that a plaintext password matches a bcrypt hash.
// Returns true if the password is correct, false otherwise.
func VerifyPassword(password, hash string) (bool, error) {
	if password == "" || hash == "" {
		return false, fmt.Errorf("password and hash cannot be empty")
	}

	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	if err != nil {
		if err == bcrypt.ErrMismatchedHashAndPassword {
			return false, nil
		}
		return false, fmt.Errorf("failed to verify password: %w", err)
	}

	return true, nil
}
