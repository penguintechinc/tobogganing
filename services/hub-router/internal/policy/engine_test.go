package policy

import (
	"errors"
	"net"
	"testing"
	"time"
)

// ── helpers ──────────────────────────────────────────────────────────────────

func parseCIDR(t *testing.T, s string) *net.IPNet {
	t.Helper()
	_, n, err := net.ParseCIDR(s)
	if err != nil {
		t.Fatalf("parseCIDR(%q): %v", s, err)
	}
	return n
}

// engineWith builds a fresh engine and loads the given raw policies.
func engineWith(t *testing.T, policies []RawPolicy) *PolicyEngine {
	t.Helper()
	pe := NewPolicyEngine()
	if err := pe.OnPolicyUpdate(policies); err != nil {
		t.Fatalf("OnPolicyUpdate: %v", err)
	}
	return pe
}

// ── PolicyDecision.String ─────────────────────────────────────────────────────

func TestPolicyDecisionString(t *testing.T) {
	cases := []struct {
		d    PolicyDecision
		want string
	}{
		{DecisionAllow, "allow"},
		{DecisionDeny, "deny"},
		{DecisionLog, "log"},
		{PolicyDecision(99), "unknown"},
	}
	for _, tc := range cases {
		if got := tc.d.String(); got != tc.want {
			t.Errorf("PolicyDecision(%d).String() = %q, want %q", tc.d, got, tc.want)
		}
	}
}

// ── NewPolicyEngine defaults ──────────────────────────────────────────────────

func TestNewPolicyEngineDefaults(t *testing.T) {
	pe := NewPolicyEngine()
	if pe.RuleCount() != 0 {
		t.Fatalf("expected 0 rules, got %d", pe.RuleCount())
	}
	if !pe.LastUpdate().IsZero() {
		t.Fatal("expected zero LastUpdate on fresh engine")
	}
}

// ── Default deny (empty rules) ────────────────────────────────────────────────

func TestEvaluateNoPoliciesDefaultDeny(t *testing.T) {
	pe := NewPolicyEngine()
	d := pe.Evaluate(&PacketInfo{
		DstIP:    net.ParseIP("10.0.0.1"),
		Protocol: "tcp",
		DstPort:  80,
	})
	if d != DecisionDeny {
		t.Fatalf("expected deny with no policies, got %v", d)
	}
}

func TestEvaluateNoMatchDefaultDeny(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Domains: []string{"example.com"}, Enabled: true},
	})
	d := pe.Evaluate(&PacketInfo{Domain: "other.com"})
	if d != DecisionDeny {
		t.Fatalf("expected deny for non-matching domain, got %v", d)
	}
}

// ── Disabled policies are skipped ────────────────────────────────────────────

func TestDisabledPoliciesSkipped(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Enabled: false},
	})
	if pe.RuleCount() != 0 {
		t.Fatalf("expected 0 rules (disabled), got %d", pe.RuleCount())
	}
}

// ── Domain matching ───────────────────────────────────────────────────────────

func TestDomainExactMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Domains: []string{"example.com"}, Enabled: true},
	})
	d := pe.Evaluate(&PacketInfo{Domain: "example.com"})
	if d != DecisionAllow {
		t.Fatalf("expected allow for exact domain match, got %v", d)
	}
}

func TestDomainExactMatchCaseInsensitive(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Domains: []string{"Example.COM"}, Enabled: true},
	})
	d := pe.Evaluate(&PacketInfo{Domain: "example.com"})
	if d != DecisionAllow {
		t.Fatalf("expected allow for case-insensitive domain match, got %v", d)
	}
}

func TestDomainWildcardMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Domains: []string{"*.example.com"}, Enabled: true},
	})
	cases := []struct {
		domain string
		want   PolicyDecision
	}{
		{"foo.example.com", DecisionAllow},
		{"bar.example.com", DecisionAllow},
		{"example.com", DecisionDeny},      // wildcard doesn't match bare apex
		{"notexample.com", DecisionDeny},
		{"foo.bar.example.com", DecisionAllow}, // multi-level suffix still matches
	}
	for _, tc := range cases {
		d := pe.Evaluate(&PacketInfo{Domain: tc.domain})
		if d != tc.want {
			t.Errorf("domain %q: expected %v, got %v", tc.domain, tc.want, d)
		}
	}
}

func TestDomainEmptyPacketDomainSkipsDimensionCheck(t *testing.T) {
	// Rule has domain list, but packet has no domain → dimension is skipped → rule matches
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Domains: []string{"example.com"}, Enabled: true},
	})
	d := pe.Evaluate(&PacketInfo{Domain: ""})
	if d != DecisionAllow {
		t.Fatalf("expected allow when packet domain is empty, got %v", d)
	}
}

// ── Port matching ─────────────────────────────────────────────────────────────

func TestPortExactMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Ports: []string{"80"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{DstPort: 80}); d != DecisionAllow {
		t.Fatalf("expected allow for port 80, got %v", d)
	}
	if d := pe.Evaluate(&PacketInfo{DstPort: 81}); d != DecisionDeny {
		t.Fatalf("expected deny for port 81, got %v", d)
	}
}

func TestPortRangeMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Ports: []string{"8000-9000"}, Enabled: true},
	})
	for _, port := range []uint16{8000, 8500, 9000} {
		if d := pe.Evaluate(&PacketInfo{DstPort: port}); d != DecisionAllow {
			t.Errorf("port %d: expected allow, got %v", port, d)
		}
	}
	for _, port := range []uint16{7999, 9001} {
		if d := pe.Evaluate(&PacketInfo{DstPort: port}); d != DecisionDeny {
			t.Errorf("port %d: expected deny, got %v", port, d)
		}
	}
}

func TestPortRangeReversedIsNormalized(t *testing.T) {
	// "9000-8000" should be auto-swapped to 8000-9000
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Ports: []string{"9000-8000"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{DstPort: 8500}); d != DecisionAllow {
		t.Fatalf("expected allow for port in reversed range, got %v", d)
	}
}

func TestPortZeroPacketSkipsDimensionCheck(t *testing.T) {
	// Rule has port list, packet DstPort == 0 → dimension skipped → rule matches
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Ports: []string{"443"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{DstPort: 0}); d != DecisionAllow {
		t.Fatalf("expected allow when DstPort is 0, got %v", d)
	}
}

func TestMultiplePorts(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Ports: []string{"80", "443"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{DstPort: 443}); d != DecisionAllow {
		t.Fatalf("expected allow for port 443, got %v", d)
	}
}

// ── Protocol matching ─────────────────────────────────────────────────────────

func TestProtocolMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp"}); d != DecisionAllow {
		t.Fatalf("expected allow for tcp, got %v", d)
	}
	if d := pe.Evaluate(&PacketInfo{Protocol: "udp"}); d != DecisionDeny {
		t.Fatalf("expected deny for udp, got %v", d)
	}
}

func TestProtocolMatchCaseInsensitive(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"TCP"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp"}); d != DecisionAllow {
		t.Fatalf("expected allow for tcp (case insensitive), got %v", d)
	}
}

func TestProtocolIcmp(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"icmp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "icmp"}); d != DecisionAllow {
		t.Fatalf("expected allow for icmp, got %v", d)
	}
}

func TestProtocolEmptyPacketSkipsDimension(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: ""}); d != DecisionAllow {
		t.Fatalf("expected allow when Protocol is empty, got %v", d)
	}
}

// ── CIDR matching ─────────────────────────────────────────────────────────────

func TestCIDRMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", CIDRs: []string{"10.0.0.0/8"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{DstIP: net.ParseIP("10.1.2.3")}); d != DecisionAllow {
		t.Fatalf("expected allow for IP in CIDR, got %v", d)
	}
	if d := pe.Evaluate(&PacketInfo{DstIP: net.ParseIP("192.168.1.1")}); d != DecisionDeny {
		t.Fatalf("expected deny for IP outside CIDR, got %v", d)
	}
}

func TestCIDRHost32(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", CIDRs: []string{"10.0.0.1/32"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{DstIP: net.ParseIP("10.0.0.1")}); d != DecisionAllow {
		t.Fatalf("expected allow for /32 match, got %v", d)
	}
	if d := pe.Evaluate(&PacketInfo{DstIP: net.ParseIP("10.0.0.2")}); d != DecisionDeny {
		t.Fatalf("expected deny for non-/32 IP, got %v", d)
	}
}

func TestCIDRNilIPSkipsDimension(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", CIDRs: []string{"10.0.0.0/8"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{DstIP: nil}); d != DecisionAllow {
		t.Fatalf("expected allow when DstIP is nil, got %v", d)
	}
}

func TestMultipleCIDRs(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", CIDRs: []string{"10.0.0.0/8", "192.168.0.0/16"}, Enabled: true},
	})
	for _, ip := range []string{"10.5.5.5", "192.168.1.1"} {
		if d := pe.Evaluate(&PacketInfo{DstIP: net.ParseIP(ip)}); d != DecisionAllow {
			t.Errorf("expected allow for %s, got %v", ip, d)
		}
	}
}

// ── User matching ─────────────────────────────────────────────────────────────

func TestUserMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Users: []string{"alice"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{UserID: "alice"}); d != DecisionAllow {
		t.Fatalf("expected allow for alice, got %v", d)
	}
	if d := pe.Evaluate(&PacketInfo{UserID: "bob"}); d != DecisionDeny {
		t.Fatalf("expected deny for bob, got %v", d)
	}
}

func TestUserEmptyPacketUserIDSkipsDimension(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Users: []string{"alice"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{UserID: ""}); d != DecisionAllow {
		t.Fatalf("expected allow when UserID is empty, got %v", d)
	}
}

func TestMultipleUsers(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Users: []string{"alice", "bob"}, Enabled: true},
	})
	for _, u := range []string{"alice", "bob"} {
		if d := pe.Evaluate(&PacketInfo{UserID: u}); d != DecisionAllow {
			t.Errorf("expected allow for user %q, got %v", u, d)
		}
	}
	if d := pe.Evaluate(&PacketInfo{UserID: "carol"}); d != DecisionDeny {
		t.Fatalf("expected deny for carol, got %v", d)
	}
}

// ── Group matching ────────────────────────────────────────────────────────────

func TestGroupMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Groups: []string{"admins"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{GroupIDs: []string{"admins"}}); d != DecisionAllow {
		t.Fatalf("expected allow for admins group, got %v", d)
	}
	if d := pe.Evaluate(&PacketInfo{GroupIDs: []string{"users"}}); d != DecisionDeny {
		t.Fatalf("expected deny for users group, got %v", d)
	}
}

func TestGroupMultipleGroupsAnyMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Groups: []string{"admins", "ops"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{GroupIDs: []string{"ops", "dev"}}); d != DecisionAllow {
		t.Fatalf("expected allow when one group matches, got %v", d)
	}
}

func TestGroupEmptyPacketGroupsSkipsDimension(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Groups: []string{"admins"}, Enabled: true},
	})
	// Empty GroupIDs → dimension check skipped → rule still matches
	if d := pe.Evaluate(&PacketInfo{GroupIDs: []string{}}); d != DecisionAllow {
		t.Fatalf("expected allow when GroupIDs is empty, got %v", d)
	}
}

// ── Priority ordering ─────────────────────────────────────────────────────────

func TestPriorityLowerNumberHigherPriority(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "low", Priority: 100, Action: "deny", Protocols: []string{"tcp"}, Enabled: true},
		{ID: "high", Priority: 1, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp"}); d != DecisionAllow {
		t.Fatalf("expected allow (high priority rule wins), got %v", d)
	}
}

func TestDenyOverridesAllowAtSamePriority(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "allow", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
		{ID: "deny", Priority: 10, Action: "deny", Protocols: []string{"tcp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp"}); d != DecisionDeny {
		t.Fatalf("expected deny (deny overrides allow at same priority), got %v", d)
	}
}

func TestHigherPriorityAllowBeatsLowerPriorityDeny(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "allow", Priority: 5, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
		{ID: "deny", Priority: 20, Action: "deny", Protocols: []string{"tcp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp"}); d != DecisionAllow {
		t.Fatalf("expected allow (priority 5 beats priority 20), got %v", d)
	}
}

// ── Specificity sorting ───────────────────────────────────────────────────────

func TestSpecificitySortingMoreDimensionsWins(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		// More specific: both protocol + port → allow
		{ID: "specific", Priority: 10, Action: "allow",
			Protocols: []string{"tcp"}, Ports: []string{"443"}, Enabled: true},
		// Less specific: only protocol → deny
		{ID: "generic", Priority: 10, Action: "deny",
			Protocols: []string{"tcp"}, Enabled: true},
	})
	// The specific rule has higher specificity (2 dims vs 1 dim).
	// With deny-overrides at same priority, we should still get deny because deny
	// overrides allow at same priority level regardless of specificity ranking in
	// the evaluation loop. Let's verify the actual behavior.
	d := pe.Evaluate(&PacketInfo{Protocol: "tcp", DstPort: 443})
	// deny overrides allow at same priority level
	if d != DecisionDeny {
		t.Fatalf("expected deny (deny overrides at same priority), got %v", d)
	}
}

func TestSpecificityOrderingVerifyRuleCount(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"},
			Ports: []string{"443"}, Domains: []string{"example.com"}, Enabled: true},
		{ID: "2", Priority: 10, Action: "deny", Protocols: []string{"tcp"}, Enabled: true},
	})
	if pe.RuleCount() != 2 {
		t.Fatalf("expected 2 rules, got %d", pe.RuleCount())
	}
}

// ── DecisionLog action ────────────────────────────────────────────────────────

func TestActionLog(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "log", Protocols: []string{"udp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "udp"}); d != DecisionLog {
		t.Fatalf("expected log decision, got %v", d)
	}
}

// ── Unknown action defaults to deny ──────────────────────────────────────────

func TestUnknownActionDefaultsDeny(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "bogus", Protocols: []string{"tcp"}, Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp"}); d != DecisionDeny {
		t.Fatalf("expected deny for unknown action, got %v", d)
	}
}

// ── compileRule / OnPolicyUpdate error paths ──────────────────────────────────

func TestInvalidPortSkipsRule(t *testing.T) {
	pe := NewPolicyEngine()
	// compileRule returns error for invalid port → rule is skipped with a warning
	_ = pe.OnPolicyUpdate([]RawPolicy{
		{ID: "bad", Priority: 10, Action: "allow", Ports: []string{"notaport"}, Enabled: true},
		{ID: "good", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})
	// Only the good rule should be loaded
	if pe.RuleCount() != 1 {
		t.Fatalf("expected 1 rule (bad port skipped), got %d", pe.RuleCount())
	}
}

func TestInvalidCIDRSkipsRule(t *testing.T) {
	pe := NewPolicyEngine()
	_ = pe.OnPolicyUpdate([]RawPolicy{
		{ID: "bad", Priority: 10, Action: "allow", CIDRs: []string{"notacidr"}, Enabled: true},
		{ID: "good", Priority: 10, Action: "deny", Protocols: []string{"tcp"}, Enabled: true},
	})
	if pe.RuleCount() != 1 {
		t.Fatalf("expected 1 rule (bad CIDR skipped), got %d", pe.RuleCount())
	}
}

func TestPortOutOfRange(t *testing.T) {
	pe := NewPolicyEngine()
	_ = pe.OnPolicyUpdate([]RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Ports: []string{"99999"}, Enabled: true},
	})
	if pe.RuleCount() != 0 {
		t.Fatalf("expected 0 rules (port out of range), got %d", pe.RuleCount())
	}
}

// ── BPF callback ──────────────────────────────────────────────────────────────

func TestBPFMapUpdateHandlerCalled(t *testing.T) {
	pe := NewPolicyEngine()
	called := false
	var capturedRules []PolicyRule
	pe.SetBPFMapUpdateHandler(func(rules []PolicyRule) error {
		called = true
		capturedRules = rules
		return nil
	})
	_ = pe.OnPolicyUpdate([]RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})
	if !called {
		t.Fatal("expected BPF map update handler to be called")
	}
	if len(capturedRules) != 1 {
		t.Fatalf("expected 1 rule in BPF callback, got %d", len(capturedRules))
	}
}

func TestBPFMapUpdateHandlerError(t *testing.T) {
	pe := NewPolicyEngine()
	pe.SetBPFMapUpdateHandler(func(rules []PolicyRule) error {
		return errors.New("BPF map write failed")
	})
	// Error from handler should NOT bubble up from OnPolicyUpdate
	err := pe.OnPolicyUpdate([]RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})
	if err != nil {
		t.Fatalf("OnPolicyUpdate should not return BPF error, got: %v", err)
	}
	// Go-level policies are still active
	if pe.RuleCount() != 1 {
		t.Fatalf("expected 1 rule despite BPF error, got %d", pe.RuleCount())
	}
}

func TestBPFMapUpdateHandlerNilIsNoOp(t *testing.T) {
	pe := NewPolicyEngine()
	// No handler registered — should not panic
	err := pe.OnPolicyUpdate([]RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

// ── RuleCount / LastUpdate ────────────────────────────────────────────────────

func TestRuleCountUpdatesOnPolicyUpdate(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
		{ID: "2", Priority: 20, Action: "deny", Protocols: []string{"udp"}, Enabled: true},
	})
	if pe.RuleCount() != 2 {
		t.Fatalf("expected 2 rules, got %d", pe.RuleCount())
	}
}

func TestLastUpdateSetOnPolicyUpdate(t *testing.T) {
	pe := NewPolicyEngine()
	before := time.Now()
	_ = pe.OnPolicyUpdate([]RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Enabled: true},
	})
	after := time.Now()
	lu := pe.LastUpdate()
	if lu.Before(before) || lu.After(after) {
		t.Fatalf("LastUpdate %v not between %v and %v", lu, before, after)
	}
}

func TestPolicyUpdateReplacesOldRules(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
		{ID: "2", Priority: 20, Action: "deny", Protocols: []string{"udp"}, Enabled: true},
	})
	// Replace with a single rule
	_ = pe.OnPolicyUpdate([]RawPolicy{
		{ID: "3", Priority: 10, Action: "allow", Protocols: []string{"icmp"}, Enabled: true},
	})
	if pe.RuleCount() != 1 {
		t.Fatalf("expected 1 rule after replacement, got %d", pe.RuleCount())
	}
}

// ── Specificity calculation ───────────────────────────────────────────────────

func TestSpecificityAllDimensions(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{
			ID:        "full",
			Priority:  10,
			Action:    "allow",
			Domains:   []string{"example.com"},
			Ports:     []string{"443"},
			Protocols: []string{"tcp"},
			CIDRs:     []string{"10.0.0.0/8"},
			Users:     []string{"alice"},
			Groups:    []string{"admins"},
			Scope:     "wireguard",
			Enabled:   true,
		},
	})
	pe.mu.RLock()
	rule := pe.rules[0]
	pe.mu.RUnlock()
	if rule.Specificity != 7 {
		t.Fatalf("expected specificity 7 (all 7 dimensions), got %d", rule.Specificity)
	}
}

func TestSpecificityZeroForEmptyRule(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Enabled: true},
	})
	pe.mu.RLock()
	rule := pe.rules[0]
	pe.mu.RUnlock()
	if rule.Specificity != 0 {
		t.Fatalf("expected specificity 0 for empty rule, got %d", rule.Specificity)
	}
}

// ── parsePortRange edge cases ─────────────────────────────────────────────────

func TestParsePortRangeSinglePort(t *testing.T) {
	pr, err := parsePortRange("443")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pr.Start != 443 || pr.End != 443 {
		t.Fatalf("expected {443,443}, got {%d,%d}", pr.Start, pr.End)
	}
}

func TestParsePortRangeRange(t *testing.T) {
	pr, err := parsePortRange("8000-9000")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pr.Start != 8000 || pr.End != 9000 {
		t.Fatalf("expected {8000,9000}, got {%d,%d}", pr.Start, pr.End)
	}
}

func TestParsePortRangeZero(t *testing.T) {
	pr, err := parsePortRange("0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pr.Start != 0 || pr.End != 0 {
		t.Fatalf("expected {0,0}, got {%d,%d}", pr.Start, pr.End)
	}
}

func TestParsePortRangeMaxPort(t *testing.T) {
	pr, err := parsePortRange("65535")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pr.Start != 65535 || pr.End != 65535 {
		t.Fatalf("expected {65535,65535}, got {%d,%d}", pr.Start, pr.End)
	}
}

func TestParsePortRangeInvalidNonNumeric(t *testing.T) {
	_, err := parsePortRange("http")
	if err == nil {
		t.Fatal("expected error for non-numeric port")
	}
}

func TestParsePortRangeInvalidOutOfRange(t *testing.T) {
	_, err := parsePortRange("70000")
	if err == nil {
		t.Fatal("expected error for port > 65535")
	}
}

func TestParsePortRangeInvalidRangeStart(t *testing.T) {
	_, err := parsePortRange("abc-443")
	if err == nil {
		t.Fatal("expected error for invalid range start")
	}
}

func TestParsePortRangeInvalidRangeEnd(t *testing.T) {
	_, err := parsePortRange("443-xyz")
	if err == nil {
		t.Fatal("expected error for invalid range end")
	}
}

func TestParsePortRangeTrimSpace(t *testing.T) {
	pr, err := parsePortRange("  80  ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pr.Start != 80 {
		t.Fatalf("expected port 80, got %d", pr.Start)
	}
}

// ── Multi-dimensional combined tests ─────────────────────────────────────────

func TestAllDimensionsMustMatch(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{
			ID:        "strict",
			Priority:  10,
			Action:    "allow",
			Domains:   []string{"api.example.com"},
			Ports:     []string{"443"},
			Protocols: []string{"tcp"},
			CIDRs:     []string{"10.0.0.0/8"},
			Users:     []string{"alice"},
			Groups:    []string{"admins"},
			Enabled:   true,
		},
	})

	fullMatch := &PacketInfo{
		Domain:   "api.example.com",
		DstPort:  443,
		Protocol: "tcp",
		DstIP:    net.ParseIP("10.1.2.3"),
		UserID:   "alice",
		GroupIDs: []string{"admins"},
	}
	if d := pe.Evaluate(fullMatch); d != DecisionAllow {
		t.Fatalf("expected allow for full match, got %v", d)
	}

	// Change each dimension one at a time — should become deny
	wrong := *fullMatch
	wrong.Domain = "other.example.com"
	if d := pe.Evaluate(&wrong); d != DecisionDeny {
		t.Errorf("expected deny for wrong domain, got %v", d)
	}

	wrong = *fullMatch
	wrong.DstPort = 80
	if d := pe.Evaluate(&wrong); d != DecisionDeny {
		t.Errorf("expected deny for wrong port, got %v", d)
	}

	wrong = *fullMatch
	wrong.Protocol = "udp"
	if d := pe.Evaluate(&wrong); d != DecisionDeny {
		t.Errorf("expected deny for wrong protocol, got %v", d)
	}

	wrong = *fullMatch
	wrong.DstIP = net.ParseIP("192.168.1.1")
	if d := pe.Evaluate(&wrong); d != DecisionDeny {
		t.Errorf("expected deny for wrong CIDR, got %v", d)
	}

	wrong = *fullMatch
	wrong.UserID = "bob"
	if d := pe.Evaluate(&wrong); d != DecisionDeny {
		t.Errorf("expected deny for wrong user, got %v", d)
	}

	wrong = *fullMatch
	wrong.GroupIDs = []string{"users"}
	if d := pe.Evaluate(&wrong); d != DecisionDeny {
		t.Errorf("expected deny for wrong group, got %v", d)
	}
}

// ── Empty policy list ─────────────────────────────────────────────────────────

func TestEmptyPolicyListDefaultDeny(t *testing.T) {
	pe := engineWith(t, []RawPolicy{})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp", DstPort: 80}); d != DecisionDeny {
		t.Fatalf("expected deny with empty policy list, got %v", d)
	}
}

// ── Overlay scope edge cases (supplement existing tests) ──────────────────────

func TestScopeEmptyRuleMatchesAnyScopePacket(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Scope: "", Enabled: true},
	})
	for _, scope := range []string{"", "wireguard", "openziti", "anything"} {
		if d := pe.Evaluate(&PacketInfo{Protocol: "tcp", OverlayScope: scope}); d != DecisionAllow {
			t.Errorf("scope %q: expected allow, got %v", scope, d)
		}
	}
}

func TestScopeEmptyPacketMatchesAnyScopeRule(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Scope: "wireguard", Enabled: true},
	})
	// Packet with empty OverlayScope → scope dimension skipped → rule matches
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp", OverlayScope: ""}); d != DecisionAllow {
		t.Fatalf("expected allow when packet scope is empty, got %v", d)
	}
}

func TestScopeMismatchDenies(t *testing.T) {
	pe := engineWith(t, []RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Scope: "wireguard", Enabled: true},
	})
	if d := pe.Evaluate(&PacketInfo{Protocol: "tcp", OverlayScope: "openziti"}); d != DecisionDeny {
		t.Fatalf("expected deny for scope mismatch, got %v", d)
	}
}

// ── Concurrent access ─────────────────────────────────────────────────────────

func TestConcurrentEvaluateAndUpdate(t *testing.T) {
	pe := NewPolicyEngine()
	_ = pe.OnPolicyUpdate([]RawPolicy{
		{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
	})

	done := make(chan struct{})
	go func() {
		for i := 0; i < 100; i++ {
			_ = pe.OnPolicyUpdate([]RawPolicy{
				{ID: "1", Priority: 10, Action: "allow", Protocols: []string{"tcp"}, Enabled: true},
			})
		}
		close(done)
	}()

	for i := 0; i < 100; i++ {
		_ = pe.Evaluate(&PacketInfo{Protocol: "tcp"})
	}
	<-done
}
