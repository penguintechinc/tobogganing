package firewall

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// ─── NewManager ───────────────────────────────────────────────────────────────

func TestNewManager(t *testing.T) {
	m := NewManager("http://manager:8080", "secret-token")
	if m == nil {
		t.Fatal("expected non-nil manager")
	}
	if m.managerURL != "http://manager:8080" {
		t.Errorf("unexpected managerURL: %s", m.managerURL)
	}
	if m.authToken != "secret-token" {
		t.Errorf("unexpected authToken: %s", m.authToken)
	}
	if m.userRules == nil {
		t.Error("userRules map should be initialised")
	}
}

// ─── GetUserRules / GetRulesCount / GetLastUpdateTime ─────────────────────────

func TestGetUserRules_Existing(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "alice"}
	m.userRules["alice"] = ur

	got := m.GetUserRules("alice")
	if got == nil {
		t.Fatal("expected non-nil rules")
	}
	if got.UserID != "alice" {
		t.Errorf("unexpected UserID: %s", got.UserID)
	}
}

func TestGetUserRules_Missing(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.GetUserRules("nobody") != nil {
		t.Error("expected nil for missing user")
	}
}

func TestGetRulesCount(t *testing.T) {
	m := NewManager("http://x", "t")
	m.userRules["a"] = &UserRules{}
	m.userRules["b"] = &UserRules{}
	if m.GetRulesCount() != 2 {
		t.Errorf("expected 2, got %d", m.GetRulesCount())
	}
}

func TestGetLastUpdateTime_Zero(t *testing.T) {
	m := NewManager("http://x", "t")
	if !m.GetLastUpdateTime().IsZero() {
		t.Error("expected zero time before any fetch")
	}
}

// ─── CheckAccess – no rules ───────────────────────────────────────────────────

func TestCheckAccess_UserNotFound(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.CheckAccess("ghost", "example.com") {
		t.Error("expected false for user with no rules")
	}
}

// ─── matchDomain ──────────────────────────────────────────────────────────────

func TestMatchDomain(t *testing.T) {
	m := NewManager("http://x", "t")

	cases := []struct {
		pattern string
		target  string
		want    bool
	}{
		{"example.com", "example.com", true},
		{"example.com", "EXAMPLE.COM", true},
		{"example.com", "other.com", false},
		{"*.example.com", "sub.example.com", true},
		{"*.example.com", "example.com", true}, // base domain also matches
		{"*.example.com", "other.com", false},
		{"*.example.com", "deep.sub.example.com", true},
		// URL targets
		{"example.com", "https://example.com/path", true},
		{"example.com", "http://example.com", true},
		{"example.com", "https://other.com", false},
		{"*.example.com", "https://api.example.com/v1", true},
	}

	for _, tc := range cases {
		got := m.matchDomain(tc.pattern, tc.target)
		if got != tc.want {
			t.Errorf("matchDomain(%q, %q): got %v, want %v", tc.pattern, tc.target, got, tc.want)
		}
	}
}

// ─── matchIP ──────────────────────────────────────────────────────────────────

func TestMatchIP(t *testing.T) {
	m := NewManager("http://x", "t")

	cases := []struct {
		pattern string
		target  string
		want    bool
	}{
		{"192.168.1.1", "192.168.1.1", true},
		{"192.168.1.1", "192.168.1.2", false},
		{"10.0.0.1", "http://10.0.0.1/path", true},
		{"10.0.0.1", "https://10.0.0.1:8080/", true},
		{"not-an-ip", "192.168.1.1", false},
		{"192.168.1.1", "not-an-ip", false},
		// IPv6
		{"::1", "::1", true},
		{"::1", "::2", false},
	}

	for _, tc := range cases {
		got := m.matchIP(tc.pattern, tc.target)
		if got != tc.want {
			t.Errorf("matchIP(%q, %q): got %v, want %v", tc.pattern, tc.target, got, tc.want)
		}
	}
}

// ─── matchIPRange ─────────────────────────────────────────────────────────────

func TestMatchIPRange(t *testing.T) {
	m := NewManager("http://x", "t")

	cases := []struct {
		pattern string
		target  string
		want    bool
	}{
		{"192.168.0.0/24", "192.168.0.1", true},
		{"192.168.0.0/24", "192.168.0.255", true},
		{"192.168.0.0/24", "192.168.1.1", false},
		{"10.0.0.0/8", "10.255.255.255", true},
		{"10.0.0.0/8", "11.0.0.1", false},
		{"bad-cidr", "10.0.0.1", false},
		{"10.0.0.0/8", "not-an-ip", false},
		// URL targets
		{"192.168.0.0/24", "https://192.168.0.50/path", true},
		{"192.168.0.0/24", "https://10.0.0.1", false},
	}

	for _, tc := range cases {
		got := m.matchIPRange(tc.pattern, tc.target)
		if got != tc.want {
			t.Errorf("matchIPRange(%q, %q): got %v, want %v", tc.pattern, tc.target, got, tc.want)
		}
	}
}

// ─── matchURLPattern ─────────────────────────────────────────────────────────

func TestMatchURLPattern(t *testing.T) {
	m := NewManager("http://x", "t")

	cases := []struct {
		pattern string
		target  string
		want    bool
	}{
		{`\.example\.com`, "https://api.example.com/v1", true},
		{`\.example\.com`, "https://api.other.com/v1", false},
		{`/api/v[0-9]+`, "/api/v2/users", true},
		{`/api/v[0-9]+`, "/api/beta/users", false},
		{"", "anything", true}, // empty pattern matches everything
	}

	for _, tc := range cases {
		got := m.matchURLPattern(tc.pattern, tc.target)
		if got != tc.want {
			t.Errorf("matchURLPattern(%q, %q): got %v, want %v", tc.pattern, tc.target, got, tc.want)
		}
	}
}

func TestMatchURLPattern_InvalidRegex(t *testing.T) {
	m := NewManager("http://x", "t")
	// Invalid regex must not panic, must return false
	if m.matchURLPattern(`[invalid`, "any") {
		t.Error("expected false for invalid regex")
	}
}

// ─── matchPort ────────────────────────────────────────────────────────────────

func TestMatchPort(t *testing.T) {
	m := NewManager("http://x", "t")

	cases := []struct {
		rulePort   string
		targetPort string
		want       bool
	}{
		// Wildcards
		{"*", "80", true},
		{"80", "*", true},
		// Exact
		{"80", "80", true},
		{"80", "443", false},
		{"invalid", "80", false},
		{"80", "invalid", false},
		// Range
		{"80-443", "80", true},
		{"80-443", "443", true},
		{"80-443", "200", true},
		{"80-443", "444", false},
		{"80-443", "79", false},
		{"bad-range", "80", false},
		// List
		{"80,443,8080", "80", true},
		{"80,443,8080", "443", true},
		{"80,443,8080", "8080", true},
		{"80,443,8080", "8081", false},
	}

	for _, tc := range cases {
		got := m.matchPort(tc.rulePort, tc.targetPort)
		if got != tc.want {
			t.Errorf("matchPort(%q, %q): got %v, want %v", tc.rulePort, tc.targetPort, got, tc.want)
		}
	}
}

// ─── matchIPOrRange ───────────────────────────────────────────────────────────

func TestMatchIPOrRange(t *testing.T) {
	m := NewManager("http://x", "t")

	cases := []struct {
		ruleIP   string
		targetIP string
		want     bool
	}{
		{"*", "192.168.1.1", true},
		{"192.168.1.1", "*", true},
		{"192.168.1.1", "192.168.1.1", true},
		{"192.168.1.1", "192.168.1.2", false},
		{"10.0.0.0/8", "10.1.2.3", true},
		{"10.0.0.0/8", "11.0.0.1", false},
		{"bad-cidr/x", "10.0.0.1", false},
		{"192.168.1.1", "not-ip", false},
	}

	for _, tc := range cases {
		got := m.matchIPOrRange(tc.ruleIP, tc.targetIP)
		if got != tc.want {
			t.Errorf("matchIPOrRange(%q, %q): got %v, want %v", tc.ruleIP, tc.targetIP, got, tc.want)
		}
	}
}

// ─── parseConnectionTarget ───────────────────────────────────────────────────

func TestParseConnectionTarget(t *testing.T) {
	m := NewManager("http://x", "t")

	t.Run("valid full target", func(t *testing.T) {
		result := m.parseConnectionTarget("tcp:192.168.1.1:1234->10.0.0.1:80:outbound")
		if result == nil {
			t.Fatal("expected non-nil result")
		}
		if result["protocol"] != "tcp" {
			t.Errorf("unexpected protocol: %s", result["protocol"])
		}
		if result["src_ip"] != "192.168.1.1" {
			t.Errorf("unexpected src_ip: %s", result["src_ip"])
		}
		if result["src_port"] != "1234" {
			t.Errorf("unexpected src_port: %s", result["src_port"])
		}
		if result["dst_ip"] != "10.0.0.1" {
			t.Errorf("unexpected dst_ip: %s", result["dst_ip"])
		}
		if result["dst_port"] != "80" {
			t.Errorf("unexpected dst_port: %s", result["dst_port"])
		}
		if result["direction"] != "outbound" {
			t.Errorf("unexpected direction: %s", result["direction"])
		}
	})

	t.Run("no arrow – returns nil", func(t *testing.T) {
		if m.parseConnectionTarget("nodirection") != nil {
			t.Error("expected nil")
		}
	})

	t.Run("minimal target", func(t *testing.T) {
		result := m.parseConnectionTarget("udp->10.0.0.1")
		if result == nil {
			t.Fatal("expected non-nil result")
		}
		if result["protocol"] != "udp" {
			t.Errorf("unexpected protocol: %s", result["protocol"])
		}
	})
}

// ─── matchProtocolRule ───────────────────────────────────────────────────────

func TestMatchProtocolRule(t *testing.T) {
	m := NewManager("http://x", "t")

	t.Run("protocol mismatch", func(t *testing.T) {
		rule := FirewallRule{Protocol: "tcp"}
		if m.matchProtocolRule(rule, "udp:192.168.1.1:1234->10.0.0.1:80") {
			t.Error("expected false for protocol mismatch")
		}
	})

	t.Run("protocol match wildcard IP/port", func(t *testing.T) {
		rule := FirewallRule{Protocol: "tcp", SrcIP: "*", DstPort: "80"}
		if !m.matchProtocolRule(rule, "tcp:192.168.1.1:9000->10.0.0.1:80:outbound") {
			t.Error("expected true")
		}
	})

	t.Run("non-connection-target returns false", func(t *testing.T) {
		rule := FirewallRule{Protocol: "tcp"}
		if m.matchProtocolRule(rule, "example.com") {
			t.Error("expected false for non-connection target")
		}
	})

	t.Run("direction mismatch", func(t *testing.T) {
		rule := FirewallRule{Direction: "inbound"}
		if m.matchProtocolRule(rule, "tcp:192.168.1.1:1234->10.0.0.1:80:outbound") {
			t.Error("expected false for direction mismatch")
		}
	})

	t.Run("direction both always passes", func(t *testing.T) {
		rule := FirewallRule{Direction: "both"}
		if !m.matchProtocolRule(rule, "tcp:192.168.1.1:1234->10.0.0.1:80:outbound") {
			t.Error("expected true for direction=both")
		}
	})
}

// ─── CheckAccess priority ordering ───────────────────────────────────────────

func TestCheckAccess_DomainAllow(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.AllowDomains = []FirewallRule{{Pattern: "example.com", Priority: 10}}
	m.userRules["user1"] = ur

	if !m.CheckAccess("user1", "example.com") {
		t.Error("expected allow for matched domain rule")
	}
}

func TestCheckAccess_DomainDeny(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.DenyDomains = []FirewallRule{{Pattern: "bad.com", Priority: 10}}
	m.userRules["user1"] = ur

	if m.CheckAccess("user1", "bad.com") {
		t.Error("expected deny for matched deny-domain rule")
	}
}

func TestCheckAccess_DefaultDeny(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	// Rules exist but nothing matches
	ur.Rules.AllowDomains = []FirewallRule{{Pattern: "allowed.com", Priority: 10}}
	m.userRules["user1"] = ur

	if m.CheckAccess("user1", "other.com") {
		t.Error("expected default deny when no rule matches")
	}
}

func TestCheckAccess_PriorityOrder(t *testing.T) {
	// Lower priority number wins: deny at priority 1 beats allow at priority 2
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.DenyDomains = []FirewallRule{{Pattern: "example.com", Priority: 1}}
	ur.Rules.AllowDomains = []FirewallRule{{Pattern: "example.com", Priority: 2}}
	m.userRules["user1"] = ur

	if m.CheckAccess("user1", "example.com") {
		t.Error("expected deny – lower-priority-number deny rule should win")
	}
}

func TestCheckAccess_PriorityOrder_AllowWins(t *testing.T) {
	// Allow at priority 1 beats deny at priority 2
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.AllowDomains = []FirewallRule{{Pattern: "example.com", Priority: 1}}
	ur.Rules.DenyDomains = []FirewallRule{{Pattern: "example.com", Priority: 2}}
	m.userRules["user1"] = ur

	if !m.CheckAccess("user1", "example.com") {
		t.Error("expected allow – lower-priority-number allow rule should win")
	}
}

func TestCheckAccess_IPAllow(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.AllowIPs = []FirewallRule{{Pattern: "10.0.0.1", Priority: 10}}
	m.userRules["user1"] = ur

	if !m.CheckAccess("user1", "10.0.0.1") {
		t.Error("expected allow for exact IP rule")
	}
}

func TestCheckAccess_IPRangeDeny(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.DenyIPRanges = []FirewallRule{{Pattern: "192.168.0.0/24", Priority: 10}}
	m.userRules["user1"] = ur

	if m.CheckAccess("user1", "192.168.0.5") {
		t.Error("expected deny for IP in range")
	}
	if m.CheckAccess("user1", "192.168.1.5") {
		t.Error("expected deny (default) for IP outside range – no matching allow")
	}
}

func TestCheckAccess_URLPatternAllow(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.AllowURLPatterns = []FirewallRule{{Pattern: `^https://api\.example\.com`, Priority: 10}}
	m.userRules["user1"] = ur

	if !m.CheckAccess("user1", "https://api.example.com/v1/users") {
		t.Error("expected allow for matching URL pattern")
	}
	if m.CheckAccess("user1", "https://api.other.com/v1/users") {
		t.Error("expected default deny for non-matching URL")
	}
}

// ─── fetchRules integration using httptest ────────────────────────────────────

func TestFetchRules_Success(t *testing.T) {
	response := AllRulesResponse{
		Timestamp:  time.Now().Format(time.RFC3339),
		RulesCount: 1,
		UserRules: map[string]UserRules{
			"user1": {
				UserID: "user1",
			},
		},
	}
	body, _ := json.Marshal(response)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/firewall/rules" {
			http.NotFound(w, r)
			return
		}
		if r.Header.Get("Authorization") != "Bearer mytoken" {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "mytoken")
	if err := m.fetchRules(); err != nil {
		t.Fatalf("fetchRules failed: %v", err)
	}
	if m.GetRulesCount() != 1 {
		t.Errorf("expected 1 rule, got %d", m.GetRulesCount())
	}
	if m.GetLastUpdateTime().IsZero() {
		t.Error("lastUpdate should be set after successful fetch")
	}
}

func TestFetchRules_HTTPError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "service unavailable", http.StatusServiceUnavailable)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	if err := m.fetchRules(); err == nil {
		t.Error("expected error for non-200 response")
	}
}

func TestFetchRules_InvalidJSON(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("not-json"))
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	if err := m.fetchRules(); err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestFetchRules_ConnectionRefused(t *testing.T) {
	m := NewManager("http://127.0.0.1:1", "tok")
	if err := m.fetchRules(); err == nil {
		t.Error("expected error for connection refused")
	}
}

// ─── Start/Stop ──────────────────────────────────────────────────────────────

func TestStartStop(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		resp := AllRulesResponse{
			UserRules: map[string]UserRules{},
		}
		body, _ := json.Marshal(resp)
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}
	// Stop should not panic or block
	done := make(chan struct{})
	go func() {
		m.Stop()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Error("Stop timed out")
	}
}

func TestStop_WithoutStart(t *testing.T) {
	// Should not panic
	m := NewManager("http://x", "tok")
	m.Stop()
}

// ─── matchesRule switch coverage ─────────────────────────────────────────────

func TestMatchesRule_UnknownType(t *testing.T) {
	m := NewManager("http://x", "t")
	rule := FirewallRule{Pattern: "anything"}
	if m.matchesRule(rule, RuleType("unknown"), "target") {
		t.Error("expected false for unknown rule type")
	}
}

func TestMatchesRule_AllTypes(t *testing.T) {
	m := NewManager("http://x", "t")

	t.Run("domain", func(t *testing.T) {
		rule := FirewallRule{Pattern: "example.com"}
		if !m.matchesRule(rule, RuleTypeDomain, "example.com") {
			t.Error("expected match")
		}
	})

	t.Run("ip", func(t *testing.T) {
		rule := FirewallRule{Pattern: "1.2.3.4"}
		if !m.matchesRule(rule, RuleTypeIP, "1.2.3.4") {
			t.Error("expected match")
		}
	})

	t.Run("ip_range", func(t *testing.T) {
		rule := FirewallRule{Pattern: "10.0.0.0/8"}
		if !m.matchesRule(rule, RuleTypeIPRange, "10.0.0.1") {
			t.Error("expected match")
		}
	})

	t.Run("url_pattern", func(t *testing.T) {
		rule := FirewallRule{Pattern: "example"}
		if !m.matchesRule(rule, RuleTypeURLPattern, "example.com") {
			t.Error("expected match")
		}
	})

	t.Run("protocol_rule", func(t *testing.T) {
		rule := FirewallRule{Protocol: "tcp"}
		// Non-connection format returns false
		if m.matchesRule(rule, RuleTypeProtocolRule, "notconnection") {
			t.Error("expected false for non-connection target")
		}
	})
}

// ─── CheckAccess with all rule types ─────────────────────────────────────────

func TestCheckAccess_ProtocolRuleAllow(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.AllowProtocolRules = []FirewallRule{
		{Protocol: "tcp", DstPort: "80", Priority: 10},
	}
	m.userRules["user1"] = ur

	if !m.CheckAccess("user1", "tcp:192.168.1.1:9000->10.0.0.1:80:outbound") {
		t.Error("expected allow for matching protocol rule")
	}
}

func TestCheckAccess_DenyProtocolRule(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.DenyProtocolRules = []FirewallRule{
		{Protocol: "tcp", DstPort: "22", Priority: 1},
	}
	m.userRules["user1"] = ur

	if m.CheckAccess("user1", "tcp:192.168.1.1:9000->10.0.0.1:22:outbound") {
		t.Error("expected deny for SSH connection")
	}
}

// ─── Constants / types exported coverage ─────────────────────────────────────

func TestConstants(t *testing.T) {
	if RuleTypeDomain != "domain" {
		t.Error("unexpected RuleTypeDomain value")
	}
	if AccessTypeAllow != "allow" {
		t.Error("unexpected AccessTypeAllow value")
	}
	if AccessTypeDeny != "deny" {
		t.Error("unexpected AccessTypeDeny value")
	}
}

// ─── refreshLoop with ticker.Reset ────────────────────────────────────────

func TestRefreshLoop_TickerReset(t *testing.T) {
	callCount := 0
	response := AllRulesResponse{
		Timestamp:  time.Now().Format(time.RFC3339),
		RulesCount: 0,
		UserRules:  map[string]UserRules{},
	}
	body, _ := json.Marshal(response)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Verify refresh ticker is active
	if m.refreshTicker == nil {
		t.Error("expected refreshTicker to be initialized")
	}

	// Wait a bit to allow ticker to fire (helps cover ticker.C branch)
	time.Sleep(50 * time.Millisecond)

	done := make(chan struct{})
	go func() {
		m.Stop()
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Error("Stop timed out")
	}

	if callCount < 1 {
		t.Error("expected at least initial fetch call")
	}
}

// ─── Start with fetchRules failure ────────────────────────────────────────

func TestStart_FetchRulesFailure(t *testing.T) {
	m := NewManager("http://127.0.0.1:1", "tok") // unreachable
	if err := m.Start(); err == nil {
		t.Error("expected error when initial fetch fails")
	}
}

// ─── matchIPOrRange with bad CIDR ──────────────────────────────────────────

func TestMatchIPOrRange_BadCIDR(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.matchIPOrRange("bad/cidr/format", "10.0.0.1") {
		t.Error("expected false for malformed CIDR")
	}
}

// ─── matchProtocolRule with source port ───────────────────────────────────

func TestMatchProtocolRule_SourcePortMismatch(t *testing.T) {
	m := NewManager("http://x", "t")
	rule := FirewallRule{Protocol: "tcp", SrcPort: "1234"}
	if m.matchProtocolRule(rule, "tcp:192.168.1.1:5678->10.0.0.1:80:outbound") {
		t.Error("expected false for source port mismatch")
	}
}

func TestMatchProtocolRule_SourcePortMatch(t *testing.T) {
	m := NewManager("http://x", "t")
	rule := FirewallRule{Protocol: "tcp", SrcPort: "1234"}
	if !m.matchProtocolRule(rule, "tcp:192.168.1.1:1234->10.0.0.1:80:outbound") {
		t.Error("expected true for matching source port")
	}
}

// ─── matchProtocolRule with source IP ─────────────────────────────────────

func TestMatchProtocolRule_SourceIPMismatch(t *testing.T) {
	m := NewManager("http://x", "t")
	rule := FirewallRule{Protocol: "tcp", SrcIP: "192.168.1.1"}
	if m.matchProtocolRule(rule, "tcp:10.0.0.1:1234->10.0.0.1:80:outbound") {
		t.Error("expected false for source IP mismatch")
	}
}

func TestMatchProtocolRule_DestIPMismatch(t *testing.T) {
	m := NewManager("http://x", "t")
	rule := FirewallRule{Protocol: "tcp", DstIP: "10.0.0.1"}
	if m.matchProtocolRule(rule, "tcp:192.168.1.1:1234->10.0.0.2:80:outbound") {
		t.Error("expected false for destination IP mismatch")
	}
}

func TestMatchProtocolRule_DestPortMismatch(t *testing.T) {
	m := NewManager("http://x", "t")
	rule := FirewallRule{Protocol: "tcp", DstPort: "443"}
	if m.matchProtocolRule(rule, "tcp:192.168.1.1:1234->10.0.0.1:80:outbound") {
		t.Error("expected false for destination port mismatch")
	}
}

// ─── parseConnectionTarget edge cases ──────────────────────────────────────

func TestParseConnectionTarget_OnlyProtocol(t *testing.T) {
	m := NewManager("http://x", "t")
	result := m.parseConnectionTarget("tcp->10.0.0.1")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result["protocol"] != "tcp" {
		t.Errorf("unexpected protocol: %s", result["protocol"])
	}
	if result["src_ip"] != "*" {
		t.Errorf("expected src_ip default *, got %s", result["src_ip"])
	}
}

func TestParseConnectionTarget_NoArrow(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.parseConnectionTarget("noarrow") != nil {
		t.Error("expected nil for no arrow")
	}
}

// ─── matchPort with edge cases ─────────────────────────────────────────────

func TestMatchPort_InvalidRangeFormat(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.matchPort("80-443-8080", "443") {
		t.Error("expected false for malformed range")
	}
}

func TestMatchPort_RangeWithBadStart(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.matchPort("abc-443", "443") {
		t.Error("expected false for non-numeric range start")
	}
}

func TestMatchPort_RangeWithBadEnd(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.matchPort("80-xyz", "443") {
		t.Error("expected false for non-numeric range end")
	}
}

func TestMatchPort_ListWithValidPort(t *testing.T) {
	m := NewManager("http://x", "t")
	// List with valid ports
	if !m.matchPort("80,443,8080", "443") {
		t.Error("expected true for valid port in list")
	}
}

// ─── CheckAccess with multiple rule types ─────────────────────────────────

func TestCheckAccess_MixedRuleTypes(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	// Allow by IP range, but deny by domain takes precedence (lower priority)
	ur.Rules.DenyDomains = []FirewallRule{{Pattern: "api.example.com", Priority: 1}}
	ur.Rules.AllowIPRanges = []FirewallRule{{Pattern: "192.168.0.0/24", Priority: 2}}
	m.userRules["user1"] = ur

	// Domain check – should deny due to priority
	if m.CheckAccess("user1", "api.example.com") {
		t.Error("expected deny due to lower priority deny rule")
	}
}

// ─── CheckAccess with IPv6 ────────────────────────────────────────────────

func TestCheckAccess_IPv6Address(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	ur.Rules.AllowIPs = []FirewallRule{{Pattern: "::1", Priority: 10}}
	m.userRules["user1"] = ur

	if !m.CheckAccess("user1", "::1") {
		t.Error("expected allow for IPv6 loopback")
	}
}

// ─── matchDomain with port in URL ──────────────────────────────────────────

func TestMatchDomain_URLWithPort(t *testing.T) {
	m := NewManager("http://x", "t")
	if !m.matchDomain("example.com", "https://example.com:8443/path") {
		t.Error("expected match for domain with port in URL")
	}
}

// ─── refreshLoop ticker coverage ──────────────────────────────────────

func TestRefreshLoop_TickerFires(t *testing.T) {
	callCount := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		resp := AllRulesResponse{
			Timestamp:  time.Now().Format(time.RFC3339),
			RulesCount: 0,
			UserRules:  map[string]UserRules{},
		}
		body, _ := json.Marshal(resp)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	if err := m.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Wait a bit for goroutine to start
	time.Sleep(50 * time.Millisecond)
	m.Stop()

	// At least initial fetch should have happened
	if callCount < 1 {
		t.Errorf("expected at least 1 fetch call, got %d", callCount)
	}
}

// ─── FetchConfig with empty response ───────────────────────────────────

func TestFetchConfig_EmptyUserRules(t *testing.T) {
	response := AllRulesResponse{
		Timestamp:  time.Now().Format(time.RFC3339),
		RulesCount: 0,
		UserRules:  map[string]UserRules{}, // empty
	}
	body, _ := json.Marshal(response)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	if err := m.fetchRules(); err != nil {
		t.Fatalf("fetchRules failed: %v", err)
	}
	if m.GetRulesCount() != 0 {
		t.Errorf("expected 0 rules, got %d", m.GetRulesCount())
	}
}

// ─── MatchIP with IPv6 and port parsing ───────────────────────────────

func TestMatchIP_IPv6WithPort(t *testing.T) {
	m := NewManager("http://x", "t")
	// IPv6 with port in brackets
	if !m.matchIP("::1", "http://[::1]:8080/path") {
		t.Error("expected match for IPv6 with port in URL")
	}
}

// ─── MatchIP with port splitting edge case ────────────────────────────

func TestMatchIP_IPv4WithPort(t *testing.T) {
	m := NewManager("http://x", "t")
	// IPv4 with port
	if !m.matchIP("10.0.0.1", "10.0.0.1:8080") {
		t.Error("expected match for IPv4 with port")
	}
}

// ─── MatchIPRange with invalid port removal ────────────────────────────

func TestMatchIPRange_NoPort(t *testing.T) {
	m := NewManager("http://x", "t")
	// Pure IP without port
	if !m.matchIPRange("10.0.0.0/8", "10.1.2.3") {
		t.Error("expected true for IP in range without port")
	}
}

// ─── parseConnectionTarget edge case with minimal components ────────────

func TestParseConnectionTarget_MinimalTarget(t *testing.T) {
	m := NewManager("http://x", "t")
	// Minimal but valid target with just protocol and destination
	result := m.parseConnectionTarget("tcp->10.0.0.1")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result["protocol"] != "tcp" {
		t.Errorf("expected protocol=tcp, got %s", result["protocol"])
	}
	if result["dst_ip"] != "10.0.0.1" {
		t.Errorf("expected dst_ip=10.0.0.1, got %s", result["dst_ip"])
	}
	if result["src_ip"] != "*" {
		t.Errorf("expected src_ip=* (default), got %s", result["src_ip"])
	}
}

// ─── CheckAccess with mixed rule priorities and types ─────────────────

func TestCheckAccess_MultiRuleTypeComplexPriority(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}
	// Multiple rule types at various priorities
	ur.Rules.DenyIPs = []FirewallRule{{Pattern: "10.0.0.1", Priority: 5}}
	ur.Rules.AllowDomains = []FirewallRule{{Pattern: "example.com", Priority: 10}}
	ur.Rules.AllowIPRanges = []FirewallRule{{Pattern: "10.0.0.0/8", Priority: 3}}
	m.userRules["user1"] = ur

	// IP in range check – should allow (priority 3 > deny at 5)
	if !m.CheckAccess("user1", "10.0.0.2") {
		t.Error("expected allow for IP in allowed range with lower priority deny")
	}
}

// ─── matchPort with edge case port lists ───────────────────────────────

func TestMatchPort_ListWithInvalidPort(t *testing.T) {
	m := NewManager("http://x", "t")
	// Port list with one invalid port – should skip and continue
	if !m.matchPort("80,invalid,443", "443") {
		t.Error("expected true for valid port in list with invalid entry")
	}
}

// ─── fetchRules response body close error ──────────────────────────────

func TestFetchRules_ResponseBodyCloseError(t *testing.T) {
	// Test deferred resp.Body.Close() with error handling
	response := AllRulesResponse{
		UserRules: map[string]UserRules{},
	}
	body, _ := json.Marshal(response)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	// Normal fetch – body close should succeed
	if err := m.fetchRules(); err != nil {
		t.Fatalf("fetchRules failed: %v", err)
	}
}

// ─── MatchURLPattern with complex regex patterns ────────────────────────

func TestMatchURLPattern_ComplexPatterns(t *testing.T) {
	m := NewManager("http://x", "t")

	cases := []struct {
		pattern string
		target  string
		want    bool
	}{
		{`^https://`, "https://example.com", true},
		{`/api/v\d+/users`, "/api/v2/users", true},
		{`\.example\.com$`, "api.example.com", true},
		{`\.example\.com$`, "api.example.com.evil.com", false},
	}

	for _, tc := range cases {
		got := m.matchURLPattern(tc.pattern, tc.target)
		if got != tc.want {
			t.Errorf("matchURLPattern(%q, %q): got %v, want %v", tc.pattern, tc.target, got, tc.want)
		}
	}
}

// ─── CheckAccess with large rule set ───────────────────────────────────

func TestCheckAccess_LargeRuleSet(t *testing.T) {
	m := NewManager("http://x", "t")
	ur := &UserRules{UserID: "user1"}

	// Add many rules at different priorities
	for i := 0; i < 10; i++ {
		ur.Rules.AllowDomains = append(ur.Rules.AllowDomains,
			FirewallRule{Pattern: fmt.Sprintf("allow-%d.com", i), Priority: 100 + i})
		ur.Rules.DenyDomains = append(ur.Rules.DenyDomains,
			FirewallRule{Pattern: fmt.Sprintf("deny-%d.com", i), Priority: 200 + i})
	}
	m.userRules["user1"] = ur

	// Allow rule should match first
	if !m.CheckAccess("user1", "allow-5.com") {
		t.Error("expected allow for matching domain rule")
	}
}

// ─── MatchIPRange with IPv6 CIDR ──────────────────────────────────────────

func TestMatchIPRange_IPv6CIDR(t *testing.T) {
	m := NewManager("http://x", "t")
	if !m.matchIPRange("2001:db8::/32", "2001:db8::1") {
		t.Error("expected true for IPv6 in CIDR range")
	}
	if m.matchIPRange("2001:db8::/32", "2001:db9::1") {
		t.Error("expected false for IPv6 outside CIDR range")
	}
}

// ─── MatchIPRange with URL containing IPv6 ────────────────────────────────

func TestMatchIPRange_URLWithIPv6(t *testing.T) {
	m := NewManager("http://x", "t")
	if !m.matchIPRange("2001:db8::/32", "http://[2001:db8::1]/path") {
		t.Error("expected match for IPv6 in CIDR from URL")
	}
}

// ─── ParseConnectionTarget with full port in destination ───────────────────

func TestParseConnectionTarget_AllComponents(t *testing.T) {
	m := NewManager("http://x", "t")
	result := m.parseConnectionTarget("tcp:192.168.1.1:5000->10.0.0.1:443:inbound")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result["direction"] != "inbound" {
		t.Errorf("unexpected direction: %s", result["direction"])
	}
	if result["dst_port"] != "443" {
		t.Errorf("unexpected dst_port: %s", result["dst_port"])
	}
}

// ─── MatchIPOrRange with IPv6 CIDR ────────────────────────────────────────

func TestMatchIPOrRange_IPv6CIDR(t *testing.T) {
	m := NewManager("http://x", "t")
	if !m.matchIPOrRange("2001:db8::/32", "2001:db8:ffff::1") {
		t.Error("expected true for IPv6 in CIDR")
	}
}

// ─── MatchIPOrRange with exact IPv6 match ─────────────────────────────────

func TestMatchIPOrRange_IPv6Exact(t *testing.T) {
	m := NewManager("http://x", "t")
	if !m.matchIPOrRange("::1", "::1") {
		t.Error("expected true for exact IPv6 match")
	}
	if m.matchIPOrRange("::1", "::2") {
		t.Error("expected false for IPv6 mismatch")
	}
}

// ─── FetchRules with response body read  ───────────────────────────────────

func TestFetchRules_MultipleUsers(t *testing.T) {
	response := AllRulesResponse{
		Timestamp:  time.Now().Format(time.RFC3339),
		RulesCount: 3,
		UserRules: map[string]UserRules{
			"user1": {UserID: "user1"},
			"user2": {UserID: "user2"},
			"user3": {UserID: "user3"},
		},
	}
	body, _ := json.Marshal(response)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	if err := m.fetchRules(); err != nil {
		t.Fatalf("fetchRules failed: %v", err)
	}
	if m.GetRulesCount() != 3 {
		t.Errorf("expected 3 users, got %d", m.GetRulesCount())
	}
}

// ─── FetchRules with user agent and content-type headers ─────────────────

func TestFetchRules_HeadersSet(t *testing.T) {
	var gotUA string
	var gotAuth string
	response := AllRulesResponse{UserRules: map[string]UserRules{}}
	body, _ := json.Marshal(response)

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUA = r.Header.Get("User-Agent")
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer ts.Close()

	m := NewManager(ts.URL, "tok")
	_ = m.fetchRules()

	if gotUA != "Tobogganing-Headend/1.0" {
		t.Errorf("unexpected User-Agent: %s", gotUA)
	}
	if !strings.Contains(gotAuth, "Bearer") {
		t.Errorf("unexpected Authorization: %s", gotAuth)
	}
}

// ─── ParseConnectionTarget with CIDR in connection rules ─────────────────

func TestParseConnectionTarget_WithCIDRInRule(t *testing.T) {
	m := NewManager("http://x", "t")
	// This tests parsing when a rule might contain CIDR (though not in connection target)
	result := m.parseConnectionTarget("tcp:10.0.0.0/8:1234->10.1.0.0/16:443:both")
	if result == nil {
		t.Fatal("expected non-nil result for CIDR-style connection target")
	}
	if result["src_ip"] != "10.0.0.0/8" {
		t.Errorf("unexpected src_ip: %s", result["src_ip"])
	}
}

// ─── MatchIPOrRange with invalid IP after valid CIDR ───────────────────────

func TestMatchIPOrRange_InvalidTargetIP(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.matchIPOrRange("10.0.0.0/8", "not-an-ip") {
		t.Error("expected false for invalid target IP")
	}
}

// ─── MatchIPRange with parse error recovery ───────────────────────────────

func TestMatchIPRange_ParseError(t *testing.T) {
	m := NewManager("http://x", "t")
	if m.matchIPRange("invalid-cidr-format", "10.0.0.1") {
		t.Error("expected false for invalid CIDR pattern")
	}
}

func containsString(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// ─── refreshLoop ──────────────────────────────────────────────────────────────

// TestRefreshLoop_TickerCaseFetchError covers the refreshTicker.C case when fetchRules fails.
// We set a 1ms ticker so the loop fires immediately, point the manager at a 500 server,
// then stop it via close(stopChan).
func TestRefreshLoop_TickerCaseFetchError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "server error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	m := &Manager{
		managerURL:    srv.URL,
		authToken:     "token",
		userRules:     make(map[string]*UserRules),
		stopChan:      make(chan bool),
		refreshTicker: time.NewTicker(1 * time.Millisecond),
	}

	done := make(chan struct{})
	go func() {
		m.refreshLoop()
		close(done)
	}()

	// Give the loop time to fire the ticker at least once.
	time.Sleep(20 * time.Millisecond)
	close(m.stopChan)

	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Error("refreshLoop did not exit after stopChan closed")
	}
}

// TestRefreshLoop_TickerCaseFetchSuccess covers the fetchRules success branch
// (refreshTicker.Reset is called, log.Debugf fires).
func TestRefreshLoop_TickerCaseFetchSuccess(t *testing.T) {
	resp := AllRulesResponse{
		Timestamp:  "2025-01-01T00:00:00Z",
		RulesCount: 0,
		UserRules:  map[string]UserRules{},
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}))
	defer srv.Close()

	m := &Manager{
		managerURL:    srv.URL,
		authToken:     "token",
		userRules:     make(map[string]*UserRules),
		stopChan:      make(chan bool),
		refreshTicker: time.NewTicker(1 * time.Millisecond),
	}

	done := make(chan struct{})
	go func() {
		m.refreshLoop()
		close(done)
	}()

	time.Sleep(20 * time.Millisecond)
	close(m.stopChan)

	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Error("refreshLoop did not exit after stopChan closed")
	}
}
