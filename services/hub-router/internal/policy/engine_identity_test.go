package policy

import (
	"fmt"
	"net"
	"testing"
)

// ---------------------------------------------------------------------------
// Tenant dimension
// ---------------------------------------------------------------------------

func TestEvaluate_TenantMismatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "tenant-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, TenantID: "acme",
	}})

	result := pe.Evaluate(&Packet{Tenant: "other"})
	if result != ActionDeny {
		t.Errorf("expected deny for tenant mismatch, got %s", result)
	}
}

func TestEvaluate_TenantMatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "tenant-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, TenantID: "acme",
	}})

	result := pe.Evaluate(&Packet{Tenant: "acme"})
	if result != ActionAllow {
		t.Errorf("expected allow for tenant match, got %s", result)
	}
}

func TestEvaluate_TenantWildcard(t *testing.T) {
	// Empty TenantID = wildcard (matches any tenant)
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "wildcard-tenant", Priority: 1, Action: ActionAllow,
		Enabled: true, TenantID: "",
	}})

	for _, tenant := range []string{"acme", "corp", "other", ""} {
		result := pe.Evaluate(&Packet{Tenant: tenant})
		if result != ActionAllow {
			t.Errorf("expected allow for wildcard tenant with pkt.Tenant=%q, got %s", tenant, result)
		}
	}
}

func TestEvaluate_TenantDisabledRule(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "disabled", Priority: 1, Action: ActionAllow,
		Enabled: false, TenantID: "acme",
	}})

	// Disabled rules are dropped; engine defaults to deny.
	result := pe.Evaluate(&Packet{Tenant: "acme"})
	if result != ActionDeny {
		t.Errorf("expected deny because rule is disabled, got %s", result)
	}
}

// ---------------------------------------------------------------------------
// Scope dimension
// ---------------------------------------------------------------------------

func TestEvaluate_ScopeMatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "scope-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, RequiredScopes: []string{"policies:read"},
	}})

	result := pe.Evaluate(&Packet{Scopes: []string{"policies:read", "policies:write"}})
	if result != ActionAllow {
		t.Errorf("expected allow for scope match, got %s", result)
	}
}

func TestEvaluate_ScopeMissing(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "scope-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, RequiredScopes: []string{"policies:admin"},
	}})

	result := pe.Evaluate(&Packet{Scopes: []string{"policies:read"}})
	if result != ActionDeny {
		t.Errorf("expected deny for missing scope, got %s", result)
	}
}

func TestEvaluate_ScopeWildcard(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "scope-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, RequiredScopes: []string{"policies:read"},
	}})

	result := pe.Evaluate(&Packet{Scopes: []string{"*:read"}})
	if result != ActionAllow {
		t.Errorf("expected allow for wildcard scope, got %s", result)
	}
}

func TestEvaluate_ScopeFullWildcard(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "scope-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, RequiredScopes: []string{"policies:admin", "users:delete"},
	}})

	result := pe.Evaluate(&Packet{Scopes: []string{"*:*"}})
	if result != ActionAllow {
		t.Errorf("expected allow for full wildcard scope, got %s", result)
	}
}

func TestEvaluate_ScopeMultipleRequired_AllSatisfied(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "multi-scope", Priority: 1, Action: ActionAllow,
		Enabled: true, RequiredScopes: []string{"policies:read", "hubs:read"},
	}})

	result := pe.Evaluate(&Packet{Scopes: []string{"policies:read", "hubs:read", "users:read"}})
	if result != ActionAllow {
		t.Errorf("expected allow when all scopes satisfied, got %s", result)
	}
}

func TestEvaluate_ScopeMultipleRequired_OneMissing(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "multi-scope", Priority: 1, Action: ActionAllow,
		Enabled: true, RequiredScopes: []string{"policies:read", "hubs:write"},
	}})

	result := pe.Evaluate(&Packet{Scopes: []string{"policies:read"}})
	if result != ActionDeny {
		t.Errorf("expected deny when one scope missing, got %s", result)
	}
}

func TestEvaluate_ScopeEmpty_Wildcard(t *testing.T) {
	// Empty RequiredScopes = wildcard (any caller passes).
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "scope-wildcard", Priority: 1, Action: ActionAllow,
		Enabled: true, RequiredScopes: nil,
	}})

	result := pe.Evaluate(&Packet{Scopes: []string{}})
	if result != ActionAllow {
		t.Errorf("expected allow for empty scope requirement, got %s", result)
	}
}

// ---------------------------------------------------------------------------
// SPIFFE ID dimension
// ---------------------------------------------------------------------------

func TestEvaluate_SpiffeIDExact(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "spiffe-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, SpiffeIDs: []string{"spiffe://acme.tobogganing.io/c1/ns/svc"},
	}})

	result := pe.Evaluate(&Packet{SpiffeID: "spiffe://acme.tobogganing.io/c1/ns/svc"})
	if result != ActionAllow {
		t.Errorf("expected allow for exact SPIFFE ID match, got %s", result)
	}
}

func TestEvaluate_SpiffeIDExactMismatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "spiffe-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, SpiffeIDs: []string{"spiffe://acme.tobogganing.io/c1/ns/svc"},
	}})

	result := pe.Evaluate(&Packet{SpiffeID: "spiffe://acme.tobogganing.io/c1/ns/other"})
	if result != ActionDeny {
		t.Errorf("expected deny for SPIFFE ID mismatch, got %s", result)
	}
}

func TestEvaluate_SpiffeIDWildcard(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "spiffe-wild", Priority: 1, Action: ActionAllow,
		Enabled: true, SpiffeIDs: []string{"spiffe://acme.tobogganing.io/*/backend/*"},
	}})

	result := pe.Evaluate(&Packet{SpiffeID: "spiffe://acme.tobogganing.io/cluster1/backend/api"})
	if result != ActionAllow {
		t.Errorf("expected allow for wildcard SPIFFE ID, got %s", result)
	}
}

func TestEvaluate_SpiffeIDWildcard_NoMatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "spiffe-wild", Priority: 1, Action: ActionAllow,
		Enabled: true, SpiffeIDs: []string{"spiffe://acme.tobogganing.io/*/backend/*"},
	}})

	result := pe.Evaluate(&Packet{SpiffeID: "spiffe://acme.tobogganing.io/cluster1/frontend/api"})
	if result != ActionDeny {
		t.Errorf("expected deny for wildcard SPIFFE ID non-match, got %s", result)
	}
}

func TestEvaluate_SpiffeIDEmpty_Wildcard(t *testing.T) {
	// Empty SpiffeIDs = wildcard (matches any caller including empty SpiffeID).
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "spiffe-wildcard", Priority: 1, Action: ActionAllow,
		Enabled: true, SpiffeIDs: nil,
	}})

	result := pe.Evaluate(&Packet{SpiffeID: "spiffe://any.tobogganing.io/c/ns/svc"})
	if result != ActionAllow {
		t.Errorf("expected allow for empty SpiffeIDs wildcard, got %s", result)
	}
}

func TestEvaluate_SpiffeIDMultiplePatterns_FirstMatches(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "multi-spiffe", Priority: 1, Action: ActionAllow,
		Enabled: true, SpiffeIDs: []string{
			"spiffe://acme.tobogganing.io/c1/ns1/svc1",
			"spiffe://acme.tobogganing.io/*/backend/*",
		},
	}})

	result := pe.Evaluate(&Packet{SpiffeID: "spiffe://acme.tobogganing.io/cluster2/backend/api"})
	if result != ActionAllow {
		t.Errorf("expected allow when second SPIFFE pattern matches, got %s", result)
	}
}

// ---------------------------------------------------------------------------
// Multi-dimension
// ---------------------------------------------------------------------------

func TestEvaluate_MultiDimensionMatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "multi-dim", Priority: 1, Action: ActionAllow,
		Enabled: true, TenantID: "acme",
		RequiredScopes: []string{"policies:read"},
		SpiffeIDs:      []string{"spiffe://acme.tobogganing.io/*/backend/*"},
	}})

	// All dimensions match
	result := pe.Evaluate(&Packet{
		Tenant:   "acme",
		Scopes:   []string{"*:read"},
		SpiffeID: "spiffe://acme.tobogganing.io/c1/backend/api",
	})
	if result != ActionAllow {
		t.Errorf("expected allow for multi-dimension match, got %s", result)
	}
}

func TestEvaluate_MultiDimensionTenantMismatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "multi-dim", Priority: 1, Action: ActionAllow,
		Enabled: true, TenantID: "acme",
		RequiredScopes: []string{"policies:read"},
		SpiffeIDs:      []string{"spiffe://acme.tobogganing.io/*/backend/*"},
	}})

	result := pe.Evaluate(&Packet{
		Tenant:   "other",
		Scopes:   []string{"*:read"},
		SpiffeID: "spiffe://acme.tobogganing.io/c1/backend/api",
	})
	if result != ActionDeny {
		t.Errorf("expected deny for tenant mismatch in multi-dim, got %s", result)
	}
}

func TestEvaluate_MultiDimensionScopeMismatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "multi-dim", Priority: 1, Action: ActionAllow,
		Enabled: true, TenantID: "acme",
		RequiredScopes: []string{"policies:admin"},
		SpiffeIDs:      []string{"spiffe://acme.tobogganing.io/*/backend/*"},
	}})

	result := pe.Evaluate(&Packet{
		Tenant:   "acme",
		Scopes:   []string{"policies:read"},
		SpiffeID: "spiffe://acme.tobogganing.io/c1/backend/api",
	})
	if result != ActionDeny {
		t.Errorf("expected deny for scope mismatch in multi-dim, got %s", result)
	}
}

func TestEvaluate_MultiDimensionSpiffeMismatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "multi-dim", Priority: 1, Action: ActionAllow,
		Enabled: true, TenantID: "acme",
		RequiredScopes: []string{"policies:read"},
		SpiffeIDs:      []string{"spiffe://acme.tobogganing.io/*/backend/*"},
	}})

	result := pe.Evaluate(&Packet{
		Tenant:   "acme",
		Scopes:   []string{"*:read"},
		SpiffeID: "spiffe://acme.tobogganing.io/c1/frontend/api",
	})
	if result != ActionDeny {
		t.Errorf("expected deny for SPIFFE mismatch in multi-dim, got %s", result)
	}
}

func TestEvaluate_PriorityOrdering(t *testing.T) {
	// Rule with priority 0 (higher) should be evaluated first.
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{
		{ID: "high", Name: "deny-high", Priority: 0, Action: ActionDeny,
			Enabled: true, TenantID: "acme"},
		{ID: "low", Name: "allow-low", Priority: 10, Action: ActionAllow,
			Enabled: true, TenantID: "acme"},
	})

	result := pe.Evaluate(&Packet{Tenant: "acme"})
	if result != ActionDeny {
		t.Errorf("higher-priority rule should win; expected deny, got %s", result)
	}
}

func TestEvaluate_NoRules_DefaultDeny(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{})

	result := pe.Evaluate(&Packet{Tenant: "acme"})
	if result != ActionDeny {
		t.Errorf("expected default deny with no rules, got %s", result)
	}
}

// ---------------------------------------------------------------------------
// scopeMatches unit tests
// ---------------------------------------------------------------------------

func TestScopeMatches(t *testing.T) {
	tests := []struct {
		required  string
		available string
		want      bool
	}{
		{"policies:read", "policies:read", true},
		{"policies:read", "policies:write", false},
		{"policies:read", "*:read", true},
		{"policies:read", "*:write", false},
		{"policies:read", "policies:*", true},
		{"policies:read", "*:*", true},
		{"users:admin", "*:*", true},
		{"*:read", "policies:read", false},
		{"hubs:write", "hubs:write", true},
		{"hubs:write", "hubs:read", false},
		{"tenants:admin", "*:admin", true},
		{"tenants:admin", "*:read", false},
		{"clusters:delete", "clusters:*", true},
		{"clusters:delete", "hubs:*", false},
	}

	for _, tt := range tests {
		got := scopeMatches(tt.required, tt.available)
		if got != tt.want {
			t.Errorf("scopeMatches(%q, %q) = %v, want %v",
				tt.required, tt.available, got, tt.want)
		}
	}
}

// ---------------------------------------------------------------------------
// spiffeIDMatches unit tests
// ---------------------------------------------------------------------------

func TestSpiffeIDMatches(t *testing.T) {
	tests := []struct {
		pattern string
		actual  string
		want    bool
	}{
		{"spiffe://a/b/c/d", "spiffe://a/b/c/d", true},
		{"spiffe://a/*/c/d", "spiffe://a/b/c/d", true},
		{"spiffe://a/*/c/*", "spiffe://a/b/c/d", true},
		{"spiffe://a/b/c/d", "spiffe://a/b/c/e", false},
		{"spiffe://a/b/c", "spiffe://a/b/c/d", false},  // segment count mismatch
		{"spiffe://a/b/c/d/e", "spiffe://a/b/c/d", false},
		{"spiffe://acme.tobogganing.io/*/backend/*",
			"spiffe://acme.tobogganing.io/cluster1/backend/api", true},
		{"spiffe://acme.tobogganing.io/*/backend/*",
			"spiffe://acme.tobogganing.io/cluster1/frontend/api", false},
		{"spiffe://a/*/*/d", "spiffe://a/b/c/d", true},
		{"spiffe://a/*/*/d", "spiffe://a/b/c/e", false},
	}

	for _, tt := range tests {
		got := spiffeIDMatches(tt.pattern, tt.actual)
		if got != tt.want {
			t.Errorf("spiffeIDMatches(%q, %q) = %v, want %v",
				tt.pattern, tt.actual, got, tt.want)
		}
	}
}

// ---------------------------------------------------------------------------
// Benchmark: policy evaluation with all identity dimensions
// ---------------------------------------------------------------------------

func BenchmarkPolicyEvaluation_WithIdentity(b *testing.B) {
	pe := NewEngine()
	policies := make([]RawPolicy, 100)
	for i := 0; i < 100; i++ {
		policies[i] = RawPolicy{
			ID: fmt.Sprintf("%d", i), Name: fmt.Sprintf("rule-%d", i),
			Priority: i, Action: ActionAllow, Enabled: true,
			TenantID:       "acme",
			RequiredScopes: []string{"policies:read"},
			SpiffeIDs:      []string{"spiffe://acme.tobogganing.io/*/backend/*"},
			CIDRs:          []string{"10.0.0.0/8"},
		}
	}
	pe.LoadPolicies(policies)

	pkt := &Packet{
		Tenant:   "acme",
		Scopes:   []string{"*:read"},
		SpiffeID: "spiffe://acme.tobogganing.io/c1/backend/api",
		DstIP:    net.ParseIP("10.0.1.1"),
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		pe.Evaluate(pkt)
	}
}

func BenchmarkPolicyEvaluation_NoMatch(b *testing.B) {
	// Worst-case: all 100 rules miss → linear scan to end.
	pe := NewEngine()
	policies := make([]RawPolicy, 100)
	for i := 0; i < 100; i++ {
		policies[i] = RawPolicy{
			ID: fmt.Sprintf("%d", i), Name: fmt.Sprintf("rule-%d", i),
			Priority: i, Action: ActionAllow, Enabled: true,
			TenantID: "acme",
		}
	}
	pe.LoadPolicies(policies)

	pkt := &Packet{Tenant: "other"}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		pe.Evaluate(pkt)
	}
}
