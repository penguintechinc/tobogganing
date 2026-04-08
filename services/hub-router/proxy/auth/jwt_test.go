package auth

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// generateTestRSAKey generates a fresh RSA key for test token signing.
func generateTestRSAKey(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("failed to generate RSA key: %v", err)
	}
	return key
}

// makeTestJWTToken creates a signed JWT using RS256 with the given claims and key.
func makeTestJWTToken(t *testing.T, key *rsa.PrivateKey, claims jwt.MapClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	tokenStr, err := token.SignedString(key)
	if err != nil {
		t.Fatalf("failed to sign token: %v", err)
	}
	return tokenStr
}

// encodeRSAPublicKeyToPEM encodes an RSA public key as PKIX PEM.
func encodeRSAPublicKeyToPEM(pub *rsa.PublicKey) ([]byte, error) {
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		return nil, err
	}
	block := &pem.Block{
		Type:  "PUBLIC KEY",
		Bytes: der,
	}
	return pem.EncodeToMemory(block), nil
}

// setupJWTServerReal starts a test server serving the RSA public key.
func setupJWTServerReal(t *testing.T, key *rsa.PrivateKey) *httptest.Server {
	t.Helper()

	pubKeyPEM, err := encodeRSAPublicKeyToPEM(&key.PublicKey)
	if err != nil {
		t.Fatalf("failed to encode public key: %v", err)
	}

	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/auth/public-key" {
			http.NotFound(w, r)
			return
		}
		resp := map[string]string{
			"public_key": string(pubKeyPEM),
			"algorithm":  "RS256",
		}
		body, _ := json.Marshal(resp)
		w.Header().Set("Content-Type", "application/json")
		_ = w.Write(body)
	}))
}

// ─── NewJWTProvider ───────────────────────────────────────────────────────────

func TestNewJWTProvider_Success(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if provider == nil {
		t.Fatal("expected non-nil provider")
	}
}

func TestNewJWTProvider_ServerUnavailable(t *testing.T) {
	_, err := NewJWTProvider("http://127.0.0.1:1", "")
	if err == nil {
		t.Error("expected error when server unavailable")
	}
}

func TestNewJWTProvider_BadStatusCode(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "forbidden", http.StatusForbidden)
	}))
	defer ts.Close()

	_, err := NewJWTProvider(ts.URL, "")
	if err == nil {
		t.Error("expected error for non-200 response")
	}
}

func TestNewJWTProvider_InvalidJSON(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("not-json"))
	}))
	defer ts.Close()

	_, err := NewJWTProvider(ts.URL, "")
	if err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestNewJWTProvider_InvalidPublicKey(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := map[string]string{
			"public_key": "not-a-valid-pem",
			"algorithm":  "RS256",
		}
		body, _ := json.Marshal(resp)
		w.Write(body)
	}))
	defer ts.Close()

	_, err := NewJWTProvider(ts.URL, "")
	if err == nil {
		t.Error("expected error for invalid public key PEM")
	}
}

// ─── ValidateToken ─────────────────────────────────────────────────────────────

func TestJWTValidateToken_Valid(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	claims := jwt.MapClaims{
		"sub":         "node-abc",
		"node_type":   "headend",
		"type":        "access",
		"permissions": []interface{}{"forward", "proxy"},
		"metadata":    map[string]interface{}{"version": "1.0"},
		"exp":         float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	user, err := provider.(*JWTProvider).ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user.ID != "node-abc" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
	if user.Metadata["node_type"] != "headend" {
		t.Errorf("unexpected node_type: %v", user.Metadata["node_type"])
	}
}

func TestJWTValidateToken_WrongType(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	claims := jwt.MapClaims{
		"sub":  "node-abc",
		"type": "refresh", // wrong type
		"exp":  float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	_, err = provider.(*JWTProvider).ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for wrong token type")
	}
}

func TestJWTValidateToken_Expired(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	claims := jwt.MapClaims{
		"sub":  "node-abc",
		"type": "access",
		"exp":  float64(time.Now().Add(-time.Hour).Unix()), // expired
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	_, err = provider.(*JWTProvider).ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for expired token")
	}
}

func TestJWTValidateToken_WrongSigningMethod(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	// Sign with HMAC instead of RSA
	hmacToken := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":  "node-abc",
		"type": "access",
		"exp":  float64(time.Now().Add(time.Hour).Unix()),
	})
	tokenStr, _ := hmacToken.SignedString([]byte("secret"))

	_, err = provider.(*JWTProvider).ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for wrong signing method")
	}
}

func TestJWTValidateToken_WrongKey(t *testing.T) {
	key1 := generateTestRSAKey(t)
	key2 := generateTestRSAKey(t)

	ts := setupJWTServerReal(t, key1)
	defer ts.Close()

	// Provider is configured with key1's public key
	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	// Token signed with key2
	claims := jwt.MapClaims{
		"sub":  "node-abc",
		"type": "access",
		"exp":  float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeTestJWTToken(t, key2, claims)

	_, err = provider.(*JWTProvider).ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for token signed with wrong key")
	}
}

func TestJWTValidateToken_PermissionsExtraction(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	claims := jwt.MapClaims{
		"sub":         "node-abc",
		"node_type":   "client",
		"type":        "access",
		"permissions": []interface{}{"read", "write", "admin"},
		"exp":         float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	user, err := provider.(*JWTProvider).ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	perms, ok := user.Metadata["permissions"].([]string)
	if !ok {
		t.Fatalf("unexpected permissions type: %T", user.Metadata["permissions"])
	}
	if len(perms) != 3 {
		t.Errorf("expected 3 permissions, got %d", len(perms))
	}
}

func TestJWTValidateToken_NoPermissions(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	claims := jwt.MapClaims{
		"sub":       "node-noperm",
		"node_type": "client",
		"type":      "access",
		"exp":       float64(time.Now().Add(time.Hour).Unix()),
		// no "permissions" key
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	user, err := provider.(*JWTProvider).ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	_ = len(user.Groups)
	if user.ID != "node-noperm" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
}

func TestJWTValidateToken_WithMetadata(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	claims := jwt.MapClaims{
		"sub":       "node-meta",
		"node_type": "gateway",
		"type":      "access",
		"metadata":  map[string]interface{}{"region": "us-east", "version": "2.0"},
		"exp":       float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	user, err := provider.(*JWTProvider).ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	extra, ok := user.Metadata["extra"].(map[string]interface{})
	if !ok {
		t.Fatalf("expected extra metadata, got %T", user.Metadata["extra"])
	}
	if extra["region"] != "us-east" {
		t.Errorf("unexpected region: %v", extra["region"])
	}
}

// ─── JWTProvider handler tests ────────────────────────────────────────────────

func TestJWTLoginHandler(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	r := gin.New()
	r.GET("/login", provider.(*JWTProvider).LoginHandler())

	req := httptest.NewRequest(http.MethodGet, "/login", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var resp map[string]interface{}
	_ = json.NewDecoder(w.Body).Decode(&resp)
	if resp["auth_type"] != "jwt" {
		t.Errorf("unexpected auth_type: %v", resp["auth_type"])
	}
	endpoints, ok := resp["endpoints"].(map[string]interface{})
	if !ok {
		t.Error("expected endpoints in response")
	}
	if endpoints["token"] == nil {
		t.Error("expected token endpoint")
	}
}

func TestJWTCallbackHandler(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	r := gin.New()
	r.GET("/callback", provider.(*JWTProvider).CallbackHandler())

	req := httptest.NewRequest(http.MethodGet, "/callback", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestJWTLogoutHandler(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	r := gin.New()
	r.GET("/logout", provider.(*JWTProvider).LogoutHandler())

	req := httptest.NewRequest(http.MethodGet, "/logout", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var resp map[string]interface{}
	_ = json.NewDecoder(w.Body).Decode(&resp)
	if resp["message"] == nil {
		t.Error("expected message in logout response")
	}
}

// ─── GetUser ──────────────────────────────────────────────────────────────────

func TestJWTGetUser_MissingHeader(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)

	_, err = provider.(*JWTProvider).GetUser(c)
	if err == nil {
		t.Error("expected error for missing header")
	}
}

func TestJWTGetUser_ValidBearerToken(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	claims := jwt.MapClaims{
		"sub":       "node-getuser",
		"node_type": "client",
		"type":      "access",
		"exp":       float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)
	c.Request.Header.Set("Authorization", "Bearer "+tokenStr)

	user, err := provider.(*JWTProvider).GetUser(c)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user.ID != "node-getuser" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
}

func TestJWTGetUser_NonBearerHeader(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)
	c.Request.Header.Set("Authorization", "Basic dXNlcjpwYXNz")

	_, err = provider.(*JWTProvider).GetUser(c)
	if err == nil {
		t.Error("expected error for non-Bearer auth header")
	}
}

// ─── GetUserInfo ──────────────────────────────────────────────────────────────

func TestJWTGetUserInfo_NotSupported(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	_, err = provider.(*JWTProvider).GetUserInfo("any-id")
	if err == nil {
		t.Error("expected error – GetUserInfo not supported for JWT provider")
	}
}

// ─── Key refresh ──────────────────────────────────────────────────────────────

func TestJWTKeyRefresh_OnStaleKey(t *testing.T) {
	key := generateTestRSAKey(t)
	ts := setupJWTServerReal(t, key)
	defer ts.Close()

	provider, err := NewJWTProvider(ts.URL, "")
	if err != nil {
		t.Fatalf("failed to create provider: %v", err)
	}

	// Backdate lastKeyFetch to force a refresh
	jwtP := provider.(*JWTProvider)
	jwtP.lastKeyFetch = time.Now().Add(-2 * time.Hour)

	claims := jwt.MapClaims{
		"sub":       "refresh-test",
		"node_type": "headend",
		"type":      "access",
		"exp":       float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeTestJWTToken(t, key, claims)

	user, err := jwtP.ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error after key refresh: %v", err)
	}
	if user.ID != "refresh-test" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
}
