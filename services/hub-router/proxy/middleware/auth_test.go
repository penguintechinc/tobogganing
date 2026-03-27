package middleware

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/tobogganing/headend/proxy/auth"
)

func init() {
	gin.SetMode(gin.TestMode)
}

// mockProvider satisfies auth.Provider for testing.
type mockProvider struct {
	user *auth.User
	err  error
}

func (m *mockProvider) ValidateToken(token string) (*auth.User, error) {
	return m.user, m.err
}
func (m *mockProvider) LoginHandler() gin.HandlerFunc {
	return func(c *gin.Context) {}
}
func (m *mockProvider) CallbackHandler() gin.HandlerFunc {
	return func(c *gin.Context) {}
}
func (m *mockProvider) LogoutHandler() gin.HandlerFunc {
	return func(c *gin.Context) {}
}
func (m *mockProvider) GetUser(ctx *gin.Context) (*auth.User, error) {
	return m.user, m.err
}

func makeRouter(provider auth.Provider) *gin.Engine {
	r := gin.New()
	r.Use(AuthRequired(provider))
	r.GET("/protected", func(c *gin.Context) {
		user, _ := c.Get("user")
		c.JSON(http.StatusOK, gin.H{"user_id": user.(*auth.User).ID})
	})
	return r
}

// ─── AuthRequired ────────────────────────────────────────────────────────────

func TestAuthRequired_MissingAuthorizationHeader(t *testing.T) {
	provider := &mockProvider{user: nil, err: nil}
	router := makeRouter(provider)

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestAuthRequired_InvalidHeaderFormat(t *testing.T) {
	provider := &mockProvider{user: nil, err: nil}
	router := makeRouter(provider)

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Basic dXNlcjpwYXNz") // not Bearer
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
	var resp map[string]interface{}
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["error"] == nil {
		t.Error("expected error field in response")
	}
}

func TestAuthRequired_ValidToken(t *testing.T) {
	user := &auth.User{
		ID:       "node-123",
		Name:     "headend-node-123",
		Email:    "node-123@tobogganing.local",
		Groups:   []string{"headend"},
		Metadata: map[string]interface{}{"permissions": []string{"forward"}},
	}
	provider := &mockProvider{user: user, err: nil}
	router := makeRouter(provider)

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer valid-token")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var resp map[string]interface{}
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["user_id"] != "node-123" {
		t.Errorf("unexpected user_id: %v", resp["user_id"])
	}
}

func TestAuthRequired_InvalidToken(t *testing.T) {
	provider := &mockProvider{user: nil, err: fmt.Errorf("token expired")}
	router := makeRouter(provider)

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer bad-token")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestAuthRequired_ContextUserSet(t *testing.T) {
	user := &auth.User{
		ID:       "ctx-user",
		Metadata: map[string]interface{}{"permissions": []string{"admin", "forward"}},
	}
	provider := &mockProvider{user: user, err: nil}

	var capturedUser interface{}
	var capturedPerms interface{}

	r := gin.New()
	r.Use(AuthRequired(provider))
	r.GET("/check", func(c *gin.Context) {
		capturedUser, _ = c.Get("user_id")
		capturedPerms, _ = c.Get("permissions")
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/check", nil)
	req.Header.Set("Authorization", "Bearer token")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if capturedUser != "ctx-user" {
		t.Errorf("expected ctx-user, got %v", capturedUser)
	}
	if capturedPerms == nil {
		t.Error("expected permissions to be set in context")
	}
}

func TestAuthRequired_UserMetadataNoPermissions(t *testing.T) {
	// When user has no permissions key in Metadata, context key should not be set
	user := &auth.User{
		ID:       "user-no-perms",
		Metadata: map[string]interface{}{}, // no "permissions" key
	}
	provider := &mockProvider{user: user, err: nil}

	var permsExists bool
	r := gin.New()
	r.Use(AuthRequired(provider))
	r.GET("/check", func(c *gin.Context) {
		_, permsExists = c.Get("permissions")
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/check", nil)
	req.Header.Set("Authorization", "Bearer token")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if permsExists {
		t.Error("permissions should not be set when not in metadata")
	}
}

// ─── PermissionRequired ───────────────────────────────────────────────────────

func makeRouterWithPermission(provider auth.Provider, required ...string) *gin.Engine {
	r := gin.New()
	r.Use(AuthRequired(provider))
	r.Use(PermissionRequired(required...))
	r.GET("/admin", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})
	return r
}

func TestPermissionRequired_HasPermission(t *testing.T) {
	user := &auth.User{
		ID:       "admin-user",
		Metadata: map[string]interface{}{"permissions": []string{"admin", "forward"}},
	}
	provider := &mockProvider{user: user, err: nil}
	router := makeRouterWithPermission(provider, "admin")

	req := httptest.NewRequest(http.MethodGet, "/admin", nil)
	req.Header.Set("Authorization", "Bearer token")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestPermissionRequired_MissingPermission(t *testing.T) {
	user := &auth.User{
		ID:       "limited-user",
		Metadata: map[string]interface{}{"permissions": []string{"forward"}},
	}
	provider := &mockProvider{user: user, err: nil}
	router := makeRouterWithPermission(provider, "admin")

	req := httptest.NewRequest(http.MethodGet, "/admin", nil)
	req.Header.Set("Authorization", "Bearer token")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestPermissionRequired_NoPermissionsInContext(t *testing.T) {
	// Bypass AuthRequired to test PermissionRequired alone
	r := gin.New()
	r.Use(PermissionRequired("admin"))
	r.GET("/admin", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/admin", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestPermissionRequired_MultiplePermissions(t *testing.T) {
	user := &auth.User{
		ID:       "full-user",
		Metadata: map[string]interface{}{"permissions": []string{"read", "write", "admin"}},
	}
	provider := &mockProvider{user: user, err: nil}
	router := makeRouterWithPermission(provider, "read", "write", "admin")

	req := httptest.NewRequest(http.MethodGet, "/admin", nil)
	req.Header.Set("Authorization", "Bearer token")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestPermissionRequired_WrongPermissionsType(t *testing.T) {
	// Manually set wrong type in context
	r := gin.New()
	r.Use(func(c *gin.Context) {
		// Set permissions as a non-[]string value
		c.Set("permissions", 12345)
		c.Next()
	})
	r.Use(PermissionRequired("admin"))
	r.GET("/admin", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/admin", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for wrong permissions type, got %d", w.Code)
	}
}

// ─── CertificateInfo ─────────────────────────────────────────────────────────

func TestCertificateInfo_NoTLS(t *testing.T) {
	var certValid interface{}

	r := gin.New()
	r.Use(CertificateInfo())
	r.GET("/", func(c *gin.Context) {
		certValid, _ = c.Get("client_cert_valid")
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	// No TLS on request
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if certValid != false {
		t.Errorf("expected client_cert_valid=false, got %v", certValid)
	}
}

// ─── Logger middleware ────────────────────────────────────────────────────────

func TestLogger_DoesNotPanic(t *testing.T) {
	r := gin.New()
	r.Use(Logger())
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })
	r.GET("/err", func(c *gin.Context) { c.Status(http.StatusInternalServerError) })
	r.GET("/client-err", func(c *gin.Context) { c.Status(http.StatusBadRequest) })

	for _, path := range []string{"/", "/err", "/client-err"} {
		req := httptest.NewRequest(http.MethodGet, path+"?foo=bar", nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
	}
}

// ─── Metrics middleware ───────────────────────────────────────────────────────

func TestMetrics_DoesNotPanic(t *testing.T) {
	r := gin.New()
	r.Use(Metrics())
	r.GET("/metrics-test", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/metrics-test", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}
