package middleware

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/tobogganing/headend/proxy/auth"
)

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

func init() {
	gin.SetMode(gin.TestMode)
}

// setupTestRouter creates a gin engine that pre-injects user into the context
// to simulate the AuthRequired middleware having already run.
func setupTestRouter(user *auth.User) *gin.Engine {
	r := gin.New()
	r.Use(func(c *gin.Context) {
		if user != nil {
			c.Set("user", user)
		}
		c.Next()
	})
	return r
}

// doRequest sends a GET to path on r and returns the recorder.
func doRequest(r *gin.Engine, path string) *httptest.ResponseRecorder {
	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, path, nil)
	r.ServeHTTP(w, req)
	return w
}

// bodyJSON decodes the response body into a map for assertion.
func bodyJSON(t *testing.T, w *httptest.ResponseRecorder) map[string]interface{} {
	t.Helper()
	var m map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &m); err != nil {
		t.Fatalf("failed to decode response JSON: %v (body: %s)", err, w.Body.String())
	}
	return m
}

// ---------------------------------------------------------------------------
// TenantRequired
// ---------------------------------------------------------------------------

func TestTenantRequired_Present(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"*:read"}}
	r := setupTestRouter(user)
	r.GET("/test", TenantRequired(), func(c *gin.Context) {
		tenant, exists := c.Get("tenant")
		if !exists {
			c.JSON(500, gin.H{"error": "tenant not set"})
			return
		}
		c.JSON(200, gin.H{"tenant": tenant})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	body := bodyJSON(t, w)
	if body["tenant"] != "acme" {
		t.Errorf("expected tenant=acme in response, got %v", body["tenant"])
	}
}

func TestTenantRequired_Missing(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "", Scopes: []string{"*:read"}}
	r := setupTestRouter(user)
	r.GET("/test", TenantRequired(), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for empty tenant, got %d", w.Code)
	}
}

func TestTenantRequired_NoUser(t *testing.T) {
	r := setupTestRouter(nil)
	r.GET("/test", TenantRequired(), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 when no user in context, got %d", w.Code)
	}
}

func TestTenantRequired_SetsContextValue(t *testing.T) {
	user := &auth.User{ID: "u2", Tenant: "corp", Scopes: []string{"*:read"}}
	r := setupTestRouter(user)

	var capturedTenant interface{}
	r.GET("/test", TenantRequired(), func(c *gin.Context) {
		capturedTenant, _ = c.Get("tenant")
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	if capturedTenant != "corp" {
		t.Errorf("expected context tenant=corp, got %v", capturedTenant)
	}
}

func TestTenantRequired_WrongContextType(t *testing.T) {
	// Inject a non-*auth.User value to trigger the type assertion failure path.
	r := gin.New()
	r.Use(func(c *gin.Context) {
		c.Set("user", "not-a-user-struct")
		c.Next()
	})
	r.GET("/test", TenantRequired(), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for wrong user type, got %d", w.Code)
	}
}

// ---------------------------------------------------------------------------
// ScopeRequired
// ---------------------------------------------------------------------------

func TestScopeRequired_Matching(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme",
		Scopes: []string{"policies:read", "policies:write"}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:read"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusOK {
		t.Errorf("expected 200 for matching scope, got %d", w.Code)
	}
}

func TestScopeRequired_WildcardMatch(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"*:admin"}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:admin"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusOK {
		t.Errorf("expected 200 for wildcard scope match, got %d", w.Code)
	}
}

func TestScopeRequired_FullWildcardMatch(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"*:*"}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:admin", "users:delete", "tenants:admin"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusOK {
		t.Errorf("expected 200 for *:* satisfying all scopes, got %d", w.Code)
	}
}

func TestScopeRequired_Insufficient(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"policies:read"}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:admin"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for insufficient scope, got %d", w.Code)
	}
}

func TestScopeRequired_MultipleRequired_AllPresent(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme",
		Scopes: []string{"policies:read", "hubs:write"}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:read", "hubs:write"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusOK {
		t.Errorf("expected 200 when all required scopes present, got %d", w.Code)
	}
}

func TestScopeRequired_MultipleRequired_OneMissing(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"policies:read"}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:read", "hubs:write"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 when one required scope missing, got %d", w.Code)
	}
}

func TestScopeRequired_NoUser(t *testing.T) {
	r := setupTestRouter(nil)
	r.GET("/test", ScopeRequired("policies:read"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 when no user in context, got %d", w.Code)
	}
}

func TestScopeRequired_WrongContextType(t *testing.T) {
	r := gin.New()
	r.Use(func(c *gin.Context) {
		c.Set("user", "not-a-user-struct")
		c.Next()
	})
	r.GET("/test", ScopeRequired("policies:read"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for wrong user type, got %d", w.Code)
	}
}

func TestScopeRequired_EmptyUserScopes(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:read"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for empty scopes, got %d", w.Code)
	}
}

func TestScopeRequired_ResponseBodyContainsRequiredScope(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"policies:read"}}
	r := setupTestRouter(user)
	r.GET("/test", ScopeRequired("policies:admin"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", w.Code)
	}
	body := bodyJSON(t, w)
	if body["required_scope"] != "policies:admin" {
		t.Errorf("expected required_scope=policies:admin in error body, got %v", body["required_scope"])
	}
}

// ---------------------------------------------------------------------------
// Combined: TenantRequired + ScopeRequired chain
// ---------------------------------------------------------------------------

func TestTenantAndScopeRequired_BothPass(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"*:read"}}
	r := setupTestRouter(user)
	r.GET("/test", TenantRequired(), ScopeRequired("policies:read"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusOK {
		t.Errorf("expected 200 for combined tenant+scope pass, got %d: %s", w.Code, w.Body.String())
	}
}

func TestTenantAndScopeRequired_TenantFails(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "", Scopes: []string{"*:read"}}
	r := setupTestRouter(user)
	r.GET("/test", TenantRequired(), ScopeRequired("policies:read"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 when tenant missing (chain), got %d", w.Code)
	}
}

func TestTenantAndScopeRequired_ScopeFails(t *testing.T) {
	user := &auth.User{ID: "u1", Tenant: "acme", Scopes: []string{"policies:read"}}
	r := setupTestRouter(user)
	r.GET("/test", TenantRequired(), ScopeRequired("policies:admin"), func(c *gin.Context) {
		c.JSON(200, gin.H{"ok": true})
	})

	w := doRequest(r, "/test")
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 when scope insufficient (chain), got %d", w.Code)
	}
}
