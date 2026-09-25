package auth

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestOAuth2SessionToken_RejectsForgeryWithClientID(t *testing.T) {
	realSecret := "real-high-entropy-session-signing-key-32bytes+"
	p := &OAuth2Provider{
		clientID:          "public-oauth2-client-id",
		sessionSigningKey: []byte(realSecret),
	}

	// Forge a token the way pre-fix code would have: signed with the PUBLIC
	// client_id (present in every /authorize redirect URL) instead of a
	// real server secret.
	forged := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":    "attacker",
		"email":  "attacker@example.com",
		"name":   "Attacker",
		"groups": []string{"admin"},
		"exp":    time.Now().Add(time.Hour).Unix(),
	})
	forgedString, err := forged.SignedString([]byte(p.clientID))
	if err != nil {
		t.Fatalf("failed to build forged token fixture: %v", err)
	}

	if _, err := p.ValidateToken(forgedString); err == nil {
		t.Fatal("expected forged token signed with public client_id to be rejected, got no error")
	}
}

func TestOAuth2SessionToken_AcceptsRealServerSecret(t *testing.T) {
	realSecret := "real-high-entropy-session-signing-key-32bytes+"
	p := &OAuth2Provider{
		clientID:          "public-oauth2-client-id",
		sessionSigningKey: []byte(realSecret),
	}

	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":    "user-1",
		"email":  "user@example.com",
		"name":   "User One",
		"groups": []string{"member"},
		"exp":    time.Now().Add(time.Hour).Unix(),
	})
	tokString, err := tok.SignedString(p.sessionSigningKey)
	if err != nil {
		t.Fatalf("failed to sign token with real secret: %v", err)
	}

	user, err := p.ValidateToken(tokString)
	if err != nil {
		t.Fatalf("expected token signed with real session secret to validate, got error: %v", err)
	}
	if user.ID != "user-1" || user.Email != "user@example.com" {
		t.Errorf("unexpected user claims: %+v", user)
	}
}

func TestOAuth2SessionToken_RejectsNoneAlg(t *testing.T) {
	realSecret := "real-high-entropy-session-signing-key-32bytes+"
	p := &OAuth2Provider{
		clientID:          "public-oauth2-client-id",
		sessionSigningKey: []byte(realSecret),
	}

	// alg=none forgery attempt — ValidateToken must reject any signing
	// method other than HMAC, regardless of the (absent) signature.
	unsigned := jwt.NewWithClaims(jwt.SigningMethodNone, jwt.MapClaims{
		"sub":   "attacker",
		"email": "attacker@example.com",
		"name":  "Attacker",
		"exp":   time.Now().Add(time.Hour).Unix(),
	})
	unsignedString, err := unsigned.SignedString(jwt.UnsafeAllowNoneSignatureType)
	if err != nil {
		t.Fatalf("failed to build alg=none fixture: %v", err)
	}

	if _, err := p.ValidateToken(unsignedString); err == nil {
		t.Fatal("expected alg=none token to be rejected, got no error")
	}
}

func TestNewOAuth2Provider_FailsClosedWithoutSessionSigningKey(t *testing.T) {
	// The session-signing-key check must run before any network call
	// (OIDC discovery), so these fail fast against an unreachable issuer.
	if _, err := NewOAuth2Provider("https://issuer.invalid.example", "client-id", "client-secret", ""); err == nil {
		t.Fatal("expected error for empty session signing key")
	}
	if _, err := NewOAuth2Provider("https://issuer.invalid.example", "client-id", "client-secret", "short"); err == nil {
		t.Fatal("expected error for too-short session signing key")
	}
}
