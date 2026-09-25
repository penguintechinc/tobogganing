// Package main implements the SASEWaddle headend proxy server.
package main

import "testing"

func TestTokenMatchConstantTime(t *testing.T) {
	if !tokensEqual("abc", "abc") {
		t.Fatal("equal tokens should match")
	}
	if tokensEqual("abc", "abd") {
		t.Fatal("different tokens must not match")
	}
	if tokensEqual("", "") {
		t.Fatal("empty expected token must never match")
	}
}

func TestExtractJWTFromPacket(t *testing.T) {
	tests := []struct {
		name     string
		data     []byte
		expected string
	}{
		{
			name:     "valid JWT with newline",
			data:     []byte("JWT:abc123token\nHOST:example.com"),
			expected: "abc123token",
		},
		{
			name:     "valid JWT without trailing newline",
			data:     []byte("JWT:token456"),
			expected: "token456",
		},
		{
			name:     "empty packet",
			data:     []byte(""),
			expected: "",
		},
		{
			name:     "no JWT marker",
			data:     []byte("HOST:example.com"),
			expected: "",
		},
		{
			name:     "JWT with spaces",
			data:     []byte("JWT: bearer xyz \nHOST:example.com"),
			expected: "bearer xyz",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := extractJWTFromPacket(tt.data)
			if got != tt.expected {
				t.Errorf("extractJWTFromPacket() = %q, want %q", got, tt.expected)
			}
		})
	}
}

func TestExtractTargetFromPacket(t *testing.T) {
	tests := []struct {
		name     string
		data     []byte
		expected string
	}{
		{
			name:     "valid target with newline",
			data:     []byte("JWT:token123\nHOST:example.com\n"),
			expected: "example.com",
		},
		{
			name:     "valid target without trailing newline",
			data:     []byte("HOST:target.example.com"),
			expected: "target.example.com",
		},
		{
			name:     "empty packet",
			data:     []byte(""),
			expected: "",
		},
		{
			name:     "no HOST marker",
			data:     []byte("JWT:token123"),
			expected: "",
		},
		{
			name:     "target with port",
			data:     []byte("HOST:example.com:8443\n"),
			expected: "example.com:8443",
		},
		{
			name:     "target with spaces",
			data:     []byte("HOST: example.com \n"),
			expected: "example.com",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := extractTargetFromPacket(tt.data)
			if got != tt.expected {
				t.Errorf("extractTargetFromPacket() = %q, want %q", got, tt.expected)
			}
		})
	}
}
