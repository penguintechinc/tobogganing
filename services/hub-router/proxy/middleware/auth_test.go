package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/penguintechinc/penguin-libs/packages/go-aaa/authn"
)

func init() {
	gin.SetMode(gin.TestMode)
}

// makeClaims returns a minimal valid *authn.Claims for use in tests.
func makeClaims(sub, tenant string, scopes []string) *authn.Claims {
	now := time.Now()
	return &authn.Claims{
		Sub:    sub,
		Iss:    "https://auth.example.com",
		Aud:    []string{"tobogganing"},
		Iat:    now,
		Exp:    now.Add(time.Hour),
		Scope:  scopes,
		Tenant: tenant,
	}
}

// injectClaims is a test-only middleware that pre-populates claims so we can
// test ScopeRequired and TenantRequired in isolation without a real OIDC provider.
func injectClaims(claims *authn.Claims) gin.HandlerFunc {
	return func(c *gin.Context) {
		if claims != nil {
			c.Set("claims", claims)
			c.Set("tenant", claims.Tenant)
		}
		c.Next()
	}
}

// ─── NewAuthMiddleware ────────────────────────────────────────────────────────

func TestNewAuthMiddleware_NilRP_DevMode_PassThrough(t *testing.T) {
	// nil RP = dev mode: request must pass through even without a valid token.
	r := gin.New()
	r.Use(NewAuthMiddleware(nil))
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer any-token")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200 in dev mode, got %d", w.Code)
	}
}

func TestNewAuthMiddleware_MissingAuthorizationHeader(t *testing.T) {
	r := gin.New()
	r.Use(NewAuthMiddleware(nil)) // nil RP but no header → still 401
	// Override: use a fresh router where the header check fires first.
	r2 := gin.New()
	r2.Use(NewAuthMiddleware(nil))
	r2.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	// No Authorization header at all — even dev mode must reject this.
	// Re-read the middleware: it returns 401 before checking rp==nil.
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r2.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for missing header, got %d", w.Code)
	}
	var resp map[string]interface{}
	_ = json.NewDecoder(w.Body).Decode(&resp)
	if resp["error"] == nil {
		t.Error("expected error field in response")
	}
}

func TestNewAuthMiddleware_InvalidHeaderFormat(t *testing.T) {
	r := gin.New()
	r.Use(NewAuthMiddleware(nil))
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Basic dXNlcjpwYXNz") // not Bearer
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for non-Bearer header, got %d", w.Code)
	}
}

// ─── ScopeRequired ───────────────────────────────────────────────────────────

func TestScopeRequired_HasRequiredScope(t *testing.T) {
	claims := makeClaims("user-1", "tenant-a", []string{"proxy:read", "proxy:write"})
	r := gin.New()
	r.Use(injectClaims(claims))
	r.Use(ScopeRequired("proxy:read"))
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestScopeRequired_HasAllRequiredScopes(t *testing.T) {
	claims := makeClaims("user-1", "tenant-a", []string{"proxy:read", "proxy:write", "metrics:read"})
	r := gin.New()
	r.Use(injectClaims(claims))
	r.Use(ScopeRequired("proxy:read", "proxy:write"))
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestScopeRequired_MissingScope(t *testing.T) {
	claims := makeClaims("user-1", "tenant-a", []string{"proxy:read"})
	r := gin.New()
	r.Use(injectClaims(claims))
	r.Use(ScopeRequired("proxy:write"))
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestScopeRequired_NoClaims(t *testing.T) {
	r := gin.New()
	// No injectClaims — claims are absent.
	r.Use(ScopeRequired("proxy:read"))
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 when no claims in context, got %d", w.Code)
	}
}

func TestScopeRequired_WrongClaimsType(t *testing.T) {
	r := gin.New()
	r.Use(func(c *gin.Context) {
		c.Set("claims", "not-a-claims-struct") // wrong type
		c.Next()
	})
	r.Use(ScopeRequired("proxy:read"))
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for wrong claims type, got %d", w.Code)
	}
}

// ─── TenantRequired ───────────────────────────────────────────────────────────

func TestTenantRequired_HasTenant(t *testing.T) {
	claims := makeClaims("user-1", "tenant-a", nil)
	r := gin.New()
	r.Use(injectClaims(claims))
	r.Use(TenantRequired())
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestTenantRequired_EmptyTenant(t *testing.T) {
	claims := makeClaims("user-1", "", nil) // no tenant
	r := gin.New()
	r.Use(injectClaims(claims))
	r.Use(TenantRequired())
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for empty tenant, got %d", w.Code)
	}
}

func TestTenantRequired_NoClaims(t *testing.T) {
	r := gin.New()
	r.Use(TenantRequired())
	r.GET("/", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 when no claims in context, got %d", w.Code)
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
