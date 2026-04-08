package auth

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/oauth2"
)

func init() {
	gin.SetMode(gin.TestMode)
}

// ─── OAuth2Provider.ValidateToken ─────────────────────────────────────────────

func makeOAuth2Token(clientID string, claims jwt.MapClaims) string {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, _ := token.SignedString([]byte(clientID))
	return signed
}

func TestOAuth2ValidateToken_Valid(t *testing.T) {
	clientID := "test-client-id"
	provider := &OAuth2Provider{clientID: clientID}

	claims := jwt.MapClaims{
		"sub":    "user-42",
		"email":  "user@example.com",
		"name":   "Test User",
		"groups": []interface{}{"admins", "users"},
		"exp":    float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeOAuth2Token(clientID, claims)

	user, err := provider.ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user.ID != "user-42" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
	if user.Email != "user@example.com" {
		t.Errorf("unexpected email: %s", user.Email)
	}
	if user.Name != "Test User" {
		t.Errorf("unexpected name: %s", user.Name)
	}
	if len(user.Groups) != 2 {
		t.Errorf("expected 2 groups, got %d", len(user.Groups))
	}
}

func TestOAuth2ValidateToken_Expired(t *testing.T) {
	clientID := "test-client-id"
	provider := &OAuth2Provider{clientID: clientID}

	claims := jwt.MapClaims{
		"sub":   "user-42",
		"email": "user@example.com",
		"name":  "Test User",
		"exp":   float64(time.Now().Add(-time.Hour).Unix()), // expired
	}
	tokenStr := makeOAuth2Token(clientID, claims)

	_, err := provider.ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for expired token")
	}
}

func TestOAuth2ValidateToken_WrongSecret(t *testing.T) {
	provider := &OAuth2Provider{clientID: "correct-client"}

	claims := jwt.MapClaims{
		"sub":   "user-42",
		"email": "user@example.com",
		"name":  "Test User",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeOAuth2Token("wrong-client", claims)

	_, err := provider.ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for wrong signing secret")
	}
}

func TestOAuth2ValidateToken_RSAToken(t *testing.T) {
	// RSA signed token should fail because provider expects HMAC
	provider := &OAuth2Provider{clientID: "test-client"}

	// Create an RSA-signed token using the shared helper from jwt_test.go
	key := generateTestRSAKey(t)
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{
		"sub":   "user",
		"email": "user@example.com",
		"name":  "User",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
	})
	tokenStr, _ := token.SignedString(key)

	_, err := provider.ValidateToken(tokenStr)
	if err == nil {
		t.Error("expected error for wrong signing method (RSA vs HMAC)")
	}
}

func TestOAuth2ValidateToken_EmptyGroups(t *testing.T) {
	clientID := "test-client"
	provider := &OAuth2Provider{clientID: clientID}

	claims := jwt.MapClaims{
		"sub":   "user-1",
		"email": "u@x.com",
		"name":  "U",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
		// no "groups" key
	}
	tokenStr := makeOAuth2Token(clientID, claims)

	user, err := provider.ValidateToken(tokenStr)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(user.Groups) != 0 {
		t.Errorf("expected empty groups, got %v", user.Groups)
	}
}

// ─── OAuth2Provider.GetUser ───────────────────────────────────────────────────

func TestOAuth2GetUser_BearerToken(t *testing.T) {
	clientID := "test-client"
	provider := &OAuth2Provider{clientID: clientID}

	claims := jwt.MapClaims{
		"sub":   "bearer-user",
		"email": "bearer@x.com",
		"name":  "Bearer User",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeOAuth2Token(clientID, claims)

	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)
	c.Request.Header.Set("Authorization", "Bearer "+tokenStr)

	user, err := provider.GetUser(c)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user.ID != "bearer-user" {
		t.Errorf("unexpected ID: %s", user.ID)
	}
}

func TestOAuth2GetUser_NoCookieNoBearerToken(t *testing.T) {
	provider := &OAuth2Provider{clientID: "test-client"}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)

	_, err := provider.GetUser(c)
	if err == nil {
		t.Error("expected error when no authentication found")
	}
}

// ─── OAuth2Provider handler tests ─────────────────────────────────────────────

func TestOAuth2LogoutHandler(t *testing.T) {
	provider := &OAuth2Provider{clientID: "test-client"}

	r := gin.New()
	r.GET("/logout", provider.LogoutHandler())

	req := httptest.NewRequest(http.MethodGet, "/logout", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var resp map[string]interface{}
	_ = json.NewDecoder(w.Body).Decode(&resp)
	if resp["message"] != "logged out" {
		t.Errorf("unexpected message: %v", resp["message"])
	}
}

// ─── OAuth2Provider.LoginHandler ─────────────────────────────────────────────

func TestOAuth2LoginHandler_Redirects(t *testing.T) {
	// Construct a provider with a minimal oauth2.Config so LoginHandler doesn't panic
	provider := &OAuth2Provider{
		clientID: "test-client",
		config: &oauth2.Config{
			ClientID:    "test-client",
			RedirectURL: "https://localhost/callback",
			Endpoint: oauth2.Endpoint{
				AuthURL:  "https://auth.example.com/oauth/authorize",
				TokenURL: "https://auth.example.com/oauth/token",
			},
		},
	}

	r := gin.New()
	r.GET("/login", provider.LoginHandler())

	req := httptest.NewRequest(http.MethodGet, "/login", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusTemporaryRedirect {
		t.Errorf("expected 307, got %d", w.Code)
	}
	loc := w.Header().Get("Location")
	if !strings.Contains(loc, "auth.example.com") {
		t.Errorf("expected redirect to auth server, got: %s", loc)
	}
}

// ─── OAuth2Provider.CallbackHandler ──────────────────────────────────────────

func TestOAuth2CallbackHandler_NoState(t *testing.T) {
	provider := &OAuth2Provider{clientID: "test-client"}

	r := gin.New()
	r.GET("/callback", provider.CallbackHandler())

	req := httptest.NewRequest(http.MethodGet, "/callback", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestOAuth2CallbackHandler_StateMismatch(t *testing.T) {
	provider := &OAuth2Provider{clientID: "test-client"}

	r := gin.New()
	r.GET("/callback", provider.CallbackHandler())

	req := httptest.NewRequest(http.MethodGet, "/callback?state=wrong-state", nil)
	req.AddCookie(&http.Cookie{Name: "oauth_state", Value: "correct-state"})
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestOAuth2CallbackHandler_NoCode(t *testing.T) {
	provider := &OAuth2Provider{clientID: "test-client"}

	r := gin.New()
	r.GET("/callback", provider.CallbackHandler())

	req := httptest.NewRequest(http.MethodGet, "/callback?state=mystate", nil)
	req.AddCookie(&http.Cookie{Name: "oauth_state", Value: "mystate"})
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestOAuth2CallbackHandler_CodeExchangeFailure(t *testing.T) {
	// Set up a fake token endpoint that returns an error
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "invalid_grant", http.StatusBadRequest)
	}))
	defer ts.Close()

	provider := &OAuth2Provider{
		clientID: "test-client",
		config: &oauth2.Config{
			ClientID: "test-client",
			Endpoint: oauth2.Endpoint{
				AuthURL:  ts.URL + "/authorize",
				TokenURL: ts.URL + "/token",
			},
		},
	}

	r := gin.New()
	r.GET("/callback", provider.CallbackHandler())

	req := httptest.NewRequest(http.MethodGet, "/callback?state=mystate&code=mycode", nil)
	req.AddCookie(&http.Cookie{Name: "oauth_state", Value: "mystate"})
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500 on token exchange failure, got %d", w.Code)
	}
}

// ─── NewOAuth2Provider ────────────────────────────────────────────────────────

func TestNewOAuth2Provider_InvalidIssuer(t *testing.T) {
	_, err := NewOAuth2Provider("http://127.0.0.1:1", "client-id", "client-secret")
	if err == nil {
		t.Error("expected error for unreachable OIDC issuer")
	}
}

// ─── generateState ────────────────────────────────────────────────────────────

func TestGenerateState(t *testing.T) {
	s1 := generateState()
	s2 := generateState()
	if s1 == "" || s2 == "" {
		t.Error("generateState should return non-empty strings")
	}
	// They may be equal within the same nanosecond, but should not panic
}

// ─── GetUser - cookie path ────────────────────────────────────────────────────

func TestOAuth2GetUser_SessionCookie(t *testing.T) {
	clientID := "test-client"
	provider := &OAuth2Provider{clientID: clientID}

	claims := jwt.MapClaims{
		"sub":   "cookie-user",
		"email": "cookie@x.com",
		"name":  "Cookie User",
		"exp":   float64(time.Now().Add(time.Hour).Unix()),
	}
	tokenStr := makeOAuth2Token(clientID, claims)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/", nil)
	c.Request.AddCookie(&http.Cookie{Name: "session_token", Value: tokenStr})

	user, err := provider.GetUser(c)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if user.ID != "cookie-user" {
		t.Errorf("unexpected user ID: %s", user.ID)
	}
}
