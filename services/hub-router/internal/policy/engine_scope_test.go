package policy

import (
	"testing"
)

// ---------------------------------------------------------------------------
// overlayScoreMatches unit tests
// ---------------------------------------------------------------------------

func TestOverlayScoreMatches_ExactScopeMatch(t *testing.T) {
	// ruleScope == pktOverlay → true
	if !overlayScoreMatches("wireguard", "wireguard") {
		t.Error("overlayScoreMatches('wireguard','wireguard') should be true")
	}
	if !overlayScoreMatches("openziti", "openziti") {
		t.Error("overlayScoreMatches('openziti','openziti') should be true")
	}
	if !overlayScoreMatches("k8s", "k8s") {
		t.Error("overlayScoreMatches('k8s','k8s') should be true")
	}
}

func TestOverlayScoreMatches_WildcardRuleScope_EmptyString(t *testing.T) {
	// An empty ruleScope is a wildcard — always matches.
	for _, pktScope := range []string{"wireguard", "openziti", "k8s", "both", ""} {
		if !overlayScoreMatches("", pktScope) {
			t.Errorf("overlayScoreMatches('', %q) should be true (wildcard rule)", pktScope)
		}
	}
}

func TestOverlayScoreMatches_BothRuleScope_MatchesAll(t *testing.T) {
	// ruleScope == "both" is an explicit wildcard — matches any pktOverlay.
	for _, pktScope := range []string{"wireguard", "openziti", "k8s", "both", ""} {
		if !overlayScoreMatches("both", pktScope) {
			t.Errorf("overlayScoreMatches('both', %q) should be true (explicit wildcard)", pktScope)
		}
	}
}

func TestOverlayScoreMatches_EmptyPacketScope_LegacyCaller(t *testing.T) {
	// If the packet has no overlay context (empty string) the rule should still
	// match regardless of what scope the rule specifies — legacy callers may not
	// set OverlayScope.
	for _, ruleScope := range []string{"wireguard", "openziti", "k8s"} {
		if !overlayScoreMatches(ruleScope, "") {
			t.Errorf("overlayScoreMatches(%q, '') should be true (empty packet scope = legacy caller)", ruleScope)
		}
	}
}

func TestOverlayScoreMatches_MismatchedScopes(t *testing.T) {
	cases := []struct {
		rule string
		pkt  string
	}{
		{"wireguard", "openziti"},
		{"wireguard", "k8s"},
		{"openziti", "wireguard"},
		{"openziti", "k8s"},
		{"k8s", "wireguard"},
		{"k8s", "openziti"},
	}
	for _, tc := range cases {
		if overlayScoreMatches(tc.rule, tc.pkt) {
			t.Errorf("overlayScoreMatches(%q, %q) should be false (mismatched scopes)", tc.rule, tc.pkt)
		}
	}
}

// ---------------------------------------------------------------------------
// Evaluate with overlay scope on the Packet
// ---------------------------------------------------------------------------

func TestEvaluate_OpenZitiScopedRule_MatchesOpenZitiPacket(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "openziti-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, Scope: "openziti",
	}})

	result := pe.Evaluate(&Packet{OverlayScope: "openziti"})
	if result != ActionAllow {
		t.Errorf("expected allow for openziti-scoped rule with openziti packet, got %s", result)
	}
}

func TestEvaluate_WireGuardScopedRule_DeniesOpenZitiPacket(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "wireguard-only", Priority: 1, Action: ActionAllow,
		Enabled: true, Scope: "wireguard",
	}})

	// Packet arrived via OpenZiti — the wireguard-scoped rule must NOT fire.
	result := pe.Evaluate(&Packet{OverlayScope: "openziti"})
	if result != ActionDeny {
		t.Errorf("expected deny when wireguard-scoped rule sees openziti packet, got %s", result)
	}
}

func TestEvaluate_WireGuardScopedRule_MatchesWireGuardPacket(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "wireguard-only", Priority: 1, Action: ActionAllow,
		Enabled: true, Scope: "wireguard",
	}})

	result := pe.Evaluate(&Packet{OverlayScope: "wireguard"})
	if result != ActionAllow {
		t.Errorf("expected allow for wireguard-scoped rule with wireguard packet, got %s", result)
	}
}

func TestEvaluate_WildcardScopedRule_MatchesAnyOverlay(t *testing.T) {
	// Empty rule scope = wildcard — must fire regardless of overlay path.
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "all-overlays", Priority: 1, Action: ActionAllow,
		Enabled: true, Scope: "",
	}})

	for _, overlay := range []string{"wireguard", "openziti", "k8s", "both", ""} {
		result := pe.Evaluate(&Packet{OverlayScope: overlay})
		if result != ActionAllow {
			t.Errorf("expected allow for wildcard scope rule with overlay=%q, got %s", overlay, result)
		}
	}
}

func TestEvaluate_BothScopedRule_MatchesAnyOverlay(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "both-overlay", Priority: 1, Action: ActionAllow,
		Enabled: true, Scope: "both",
	}})

	for _, overlay := range []string{"wireguard", "openziti", "k8s", ""} {
		result := pe.Evaluate(&Packet{OverlayScope: overlay})
		if result != ActionAllow {
			t.Errorf("expected allow for 'both'-scoped rule with overlay=%q, got %s", overlay, result)
		}
	}
}

func TestEvaluate_LegacyCaller_NoOverlayScope_MatchesScopedRule(t *testing.T) {
	// Legacy callers that do not set OverlayScope should not be blocked by
	// scope-constrained rules (backward-compatible behaviour).
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "wg-rule", Priority: 1, Action: ActionAllow,
		Enabled: true, Scope: "wireguard",
	}})

	result := pe.Evaluate(&Packet{OverlayScope: ""})
	if result != ActionAllow {
		t.Errorf("expected allow for legacy caller (empty OverlayScope) against wireguard-scoped rule, got %s", result)
	}
}

func TestEvaluate_ScopeAndTenant_BothMustMatch(t *testing.T) {
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{{
		ID: "1", Name: "combined", Priority: 1, Action: ActionAllow,
		Enabled: true, Scope: "wireguard", TenantID: "acme",
	}})

	// Both tenant and overlay match → allow.
	result := pe.Evaluate(&Packet{Tenant: "acme", OverlayScope: "wireguard"})
	if result != ActionAllow {
		t.Errorf("expected allow when scope and tenant both match, got %s", result)
	}

	// Correct overlay but wrong tenant → deny.
	result = pe.Evaluate(&Packet{Tenant: "other", OverlayScope: "wireguard"})
	if result != ActionDeny {
		t.Errorf("expected deny when tenant mismatches despite correct overlay, got %s", result)
	}

	// Correct tenant but wrong overlay → deny.
	result = pe.Evaluate(&Packet{Tenant: "acme", OverlayScope: "openziti"})
	if result != ActionDeny {
		t.Errorf("expected deny when overlay mismatches despite correct tenant, got %s", result)
	}
}

// ---------------------------------------------------------------------------
// Specificity — scope increases rule specificity
// ---------------------------------------------------------------------------

func TestRuleSpecificity_IncreaseWithScope(t *testing.T) {
	// A rule with a scope set should have higher specificity than the same
	// rule without a scope.
	withoutScope, err := compileRule(RawPolicy{
		ID: "1", Name: "no-scope", Action: ActionAllow, Enabled: true,
	})
	if err != nil {
		t.Fatalf("compileRule without scope failed: %v", err)
	}

	withScope, err := compileRule(RawPolicy{
		ID: "2", Name: "with-scope", Action: ActionAllow, Enabled: true,
		Scope: "wireguard",
	})
	if err != nil {
		t.Fatalf("compileRule with scope failed: %v", err)
	}

	if withScope.Specificity <= withoutScope.Specificity {
		t.Errorf("expected scope to increase specificity: withScope=%d, withoutScope=%d",
			withScope.Specificity, withoutScope.Specificity)
	}
}

func TestRuleSpecificity_ScopeAddsExactlyOne(t *testing.T) {
	base, err := compileRule(RawPolicy{
		ID: "1", Name: "base", Action: ActionAllow, Enabled: true,
	})
	if err != nil {
		t.Fatalf("compileRule base failed: %v", err)
	}

	scoped, err := compileRule(RawPolicy{
		ID: "2", Name: "scoped", Action: ActionAllow, Enabled: true,
		Scope: "openziti",
	})
	if err != nil {
		t.Fatalf("compileRule scoped failed: %v", err)
	}

	if scoped.Specificity != base.Specificity+1 {
		t.Errorf("scope should add exactly 1 to specificity: base=%d scoped=%d",
			base.Specificity, scoped.Specificity)
	}
}

// ---------------------------------------------------------------------------
// compileRule — scope validation
// ---------------------------------------------------------------------------

func TestCompileRule_ValidOverlayScopes_Accepted(t *testing.T) {
	validScopes := []string{"wireguard", "openziti", "k8s", "both", ""}
	for _, scope := range validScopes {
		rule, err := compileRule(RawPolicy{
			ID: "1", Name: "test", Action: ActionAllow, Enabled: true,
			Scope: scope,
		})
		if err != nil {
			t.Errorf("compileRule with valid scope %q returned error: %v", scope, err)
		}
		if scope != "" && rule.Scope != scope {
			t.Errorf("expected rule.Scope=%q, got %q", scope, rule.Scope)
		}
	}
}

func TestCompileRule_InvalidOverlayScope_Rejected(t *testing.T) {
	invalidScopes := []string{"vxlan", "ipsec", "WIREGUARD", "WireGuard", "overlay"}
	for _, scope := range invalidScopes {
		_, err := compileRule(RawPolicy{
			ID: "1", Name: "bad-scope", Action: ActionAllow, Enabled: true,
			Scope: scope,
		})
		if err == nil {
			t.Errorf("compileRule with invalid scope %q should return an error, got nil", scope)
		}
	}
}

func TestCompileRule_EmptyScope_StoredAsEmptyString(t *testing.T) {
	rule, err := compileRule(RawPolicy{
		ID: "1", Name: "no-scope", Action: ActionAllow, Enabled: true,
		Scope: "",
	})
	if err != nil {
		t.Fatalf("compileRule with empty scope failed: %v", err)
	}
	if rule.Scope != "" {
		t.Errorf("expected empty scope stored as empty string, got %q", rule.Scope)
	}
}

// ---------------------------------------------------------------------------
// Priority ordering with scope — higher-specificity scoped rule wins
// ---------------------------------------------------------------------------

func TestEvaluate_ScopedRuleOutranksBroaderRule(t *testing.T) {
	// A wireguard-scoped deny at low priority should win over a wildcard allow
	// at high priority because it has higher specificity.
	pe := NewEngine()
	pe.LoadPolicies([]RawPolicy{
		{ID: "broad", Name: "wildcard-allow", Priority: 0, Action: ActionAllow,
			Enabled: true, Scope: ""},
		{ID: "narrow", Name: "wireguard-deny", Priority: 10, Action: ActionDeny,
			Enabled: true, Scope: "wireguard"},
	})

	// wireguard packet: the scoped deny (higher specificity) is evaluated first.
	result := pe.Evaluate(&Packet{OverlayScope: "wireguard"})
	if result != ActionDeny {
		t.Errorf("expected scoped deny to outrank wildcard allow, got %s", result)
	}

	// openziti packet: scoped deny does not match → wildcard allow fires.
	result = pe.Evaluate(&Packet{OverlayScope: "openziti"})
	if result != ActionAllow {
		t.Errorf("expected wildcard allow for non-wireguard packet, got %s", result)
	}
}
