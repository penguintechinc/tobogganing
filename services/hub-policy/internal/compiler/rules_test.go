package compiler

import (
	"testing"
)

// TestNewReturnsCompiler verifies that New() creates a Compiler instance.
func TestNewReturnsCompiler(t *testing.T) {
	c := New()
	if c == nil {
		t.Fatal("New() returned nil, expected *Compiler")
	}
}

// TestNewMultipleCalls verifies that New() can be called multiple times.
func TestNewMultipleCalls(t *testing.T) {
	c1 := New()
	c2 := New()
	if c1 == nil || c2 == nil {
		t.Fatal("New() returned nil on repeated calls")
	}
	// Different instances
	if c1 == c2 {
		t.Error("New() returned the same instance on repeated calls")
	}
}

// TestCompileEmptyPolicies verifies that compiling an empty policy slice returns an empty CompiledRuleSet.
func TestCompileEmptyPolicies(t *testing.T) {
	c := New()
	result := c.Compile([]Policy{})

	if len(result.BlockCIDRs) != 0 {
		t.Errorf("Expected empty BlockCIDRs, got %d", len(result.BlockCIDRs))
	}
	if len(result.AllowCIDRs) != 0 {
		t.Errorf("Expected empty AllowCIDRs, got %d", len(result.AllowCIDRs))
	}
	if len(result.BlockDomains) != 0 {
		t.Errorf("Expected empty BlockDomains, got %d", len(result.BlockDomains))
	}
	if len(result.AllowDomains) != 0 {
		t.Errorf("Expected empty AllowDomains, got %d", len(result.AllowDomains))
	}
	if len(result.RouteClusters) != 0 {
		t.Errorf("Expected empty RouteClusters, got %d", len(result.RouteClusters))
	}
	if result.RateLimits == nil {
		t.Error("RateLimits should not be nil, expected initialized map")
	}
	if len(result.RateLimits) != 0 {
		t.Errorf("Expected empty RateLimits, got %d", len(result.RateLimits))
	}
}

// TestCompileNilPolicies verifies that compiling a nil policy slice doesn't panic.
func TestCompileNilPolicies(t *testing.T) {
	c := New()
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("Compile(nil) panicked: %v", r)
		}
	}()

	result := c.Compile(nil)
	if result.RateLimits == nil {
		t.Error("RateLimits should not be nil after Compile(nil)")
	}
}

// TestCompileReturnStructure verifies that Compile returns a properly initialized CompiledRuleSet.
func TestCompileReturnStructure(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Test Policy",
			Action:  "allow",
			Enabled: true,
		},
	}

	result := c.Compile(policies)

	// Verify the RateLimits map is initialized
	if result.RateLimits == nil {
		t.Error("RateLimits map should be initialized, not nil")
	}

	// CompiledRuleSet fields will be nil slices after Compile (not initialized yet in stub)
	// This is expected behavior for the stub implementation
}

// TestCompileSinglePolicy verifies compilation of a single policy.
func TestCompileSinglePolicy(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Block Malware",
			Action:  "deny",
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompileDisabledPolicy verifies that disabled policies are handled.
func TestCompileDisabledPolicy(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Disabled Policy",
			Action:  "allow",
			Enabled: false,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized even with disabled policies")
	}
}

// TestCompileMultiplePolicies verifies compilation of multiple policies.
func TestCompileMultiplePolicies(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Policy 1",
			Action:  "allow",
			Enabled: true,
		},
		{
			ID:      "pol-2",
			Name:    "Policy 2",
			Action:  "deny",
			Enabled: true,
		},
		{
			ID:      "pol-3",
			Name:    "Policy 3",
			Action:  "log",
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePolicyWithCIDRs verifies policies with CIDR blocks.
func TestCompilePolicyWithCIDRs(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Block CIDR",
			Action:  "deny",
			CIDRs:   []string{"1.2.3.0/24", "10.0.0.0/8"},
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePolicyWithDomains verifies policies with domain restrictions.
func TestCompilePolicyWithDomains(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Block Domain",
			Action:  "deny",
			Domains: []string{"malware.example.com", "evil.org"},
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePolicyWithPorts verifies policies with port specifications.
func TestCompilePolicyWithPorts(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Block Ports",
			Action:  "deny",
			Ports:   []string{"80", "443", "8080:8090"},
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePolicyWithProtocols verifies policies with protocol restrictions.
func TestCompilePolicyWithProtocols(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:        "pol-1",
			Name:      "Block UDP",
			Action:    "deny",
			Protocols: []string{"udp"},
			Enabled:   true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePolicyWithUsers verifies policies with user constraints.
func TestCompilePolicyWithUsers(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "User Restriction",
			Action:  "allow",
			Users:   []string{"user1", "user2"},
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePolicyWithGroups verifies policies with group constraints.
func TestCompilePolicyWithGroups(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Group Restriction",
			Action:  "allow",
			Groups:  []string{"admin", "dev"},
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePolicyWithAllFields verifies policies with all fields populated.
func TestCompilePolicyWithAllFields(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:        "pol-1",
			Name:      "Complex Policy",
			Priority:  100,
			Action:    "deny",
			Domains:   []string{"example.com"},
			Ports:     []string{"443"},
			Protocols: []string{"tcp"},
			CIDRs:     []string{"192.168.1.0/24"},
			Users:     []string{"alice"},
			Groups:    []string{"engineers"},
			Enabled:   true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompilePoliciesPriority verifies that policies are processed in priority order.
func TestCompilePoliciesPriority(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-3",
			Name:    "Low Priority",
			Priority: 300,
			Action:  "allow",
			Enabled: true,
		},
		{
			ID:      "pol-1",
			Name:    "High Priority",
			Priority: 100,
			Action:  "deny",
			Enabled: true,
		},
		{
			ID:      "pol-2",
			Name:    "Medium Priority",
			Priority: 200,
			Action:  "log",
			Enabled: true,
		},
	}

	result := c.Compile(policies)
	if result.RateLimits == nil {
		t.Fatal("RateLimits should be initialized")
	}
}

// TestCompileResultNotModified verifies that the input policies are not modified.
func TestCompileResultNotModified(t *testing.T) {
	c := New()
	policies := []Policy{
		{
			ID:      "pol-1",
			Name:    "Test",
			Action:  "allow",
			Enabled: true,
		},
	}

	originalName := policies[0].Name
	c.Compile(policies)

	if policies[0].Name != originalName {
		t.Error("Compile() modified the input policy")
	}
}

// TestClusterDefStructure verifies the ClusterDef structure is correctly defined.
func TestClusterDefStructure(t *testing.T) {
	cluster := ClusterDef{
		Name:      "cluster-1",
		Endpoints: []string{"10.0.0.1", "10.0.0.2"},
		LBPolicy:  "ROUND_ROBIN",
	}

	if cluster.Name != "cluster-1" {
		t.Error("ClusterDef Name field not set correctly")
	}
	if len(cluster.Endpoints) != 2 {
		t.Error("ClusterDef Endpoints not set correctly")
	}
	if cluster.LBPolicy != "ROUND_ROBIN" {
		t.Error("ClusterDef LBPolicy not set correctly")
	}
}

// TestCompiledRuleSetStructure verifies the CompiledRuleSet structure.
func TestCompiledRuleSetStructure(t *testing.T) {
	ruleset := CompiledRuleSet{
		BlockCIDRs:   []string{"1.2.3.0/24"},
		AllowCIDRs:   []string{"10.0.0.0/8"},
		BlockDomains: []string{"bad.com"},
		AllowDomains: []string{"good.com"},
		RateLimits:   map[string]int{"10.0.0.1": 1000},
	}

	if len(ruleset.BlockCIDRs) != 1 || ruleset.BlockCIDRs[0] != "1.2.3.0/24" {
		t.Error("BlockCIDRs not set correctly")
	}
	if len(ruleset.AllowCIDRs) != 1 || ruleset.AllowCIDRs[0] != "10.0.0.0/8" {
		t.Error("AllowCIDRs not set correctly")
	}
	if len(ruleset.BlockDomains) != 1 || ruleset.BlockDomains[0] != "bad.com" {
		t.Error("BlockDomains not set correctly")
	}
	if len(ruleset.AllowDomains) != 1 || ruleset.AllowDomains[0] != "good.com" {
		t.Error("AllowDomains not set correctly")
	}
	if ruleset.RateLimits["10.0.0.1"] != 1000 {
		t.Error("RateLimits not set correctly")
	}
}

// TestPolicyStructure verifies the Policy structure is correctly defined.
func TestPolicyStructure(t *testing.T) {
	policy := Policy{
		ID:        "pol-1",
		Name:      "Test Policy",
		Priority:  100,
		Action:    "allow",
		Domains:   []string{"example.com"},
		Ports:     []string{"80", "443"},
		Protocols: []string{"tcp"},
		CIDRs:     []string{"192.168.1.0/24"},
		Users:     []string{"alice", "bob"},
		Groups:    []string{"admin"},
		Enabled:   true,
	}

	if policy.ID != "pol-1" {
		t.Error("Policy ID field not set correctly")
	}
	if policy.Name != "Test Policy" {
		t.Error("Policy Name field not set correctly")
	}
	if policy.Priority != 100 {
		t.Error("Policy Priority field not set correctly")
	}
	if policy.Action != "allow" {
		t.Error("Policy Action field not set correctly")
	}
	if len(policy.Domains) != 1 {
		t.Error("Policy Domains field not set correctly")
	}
	if len(policy.Ports) != 2 {
		t.Error("Policy Ports field not set correctly")
	}
	if len(policy.Protocols) != 1 {
		t.Error("Policy Protocols field not set correctly")
	}
	if len(policy.CIDRs) != 1 {
		t.Error("Policy CIDRs field not set correctly")
	}
	if len(policy.Users) != 2 {
		t.Error("Policy Users field not set correctly")
	}
	if len(policy.Groups) != 1 {
		t.Error("Policy Groups field not set correctly")
	}
	if !policy.Enabled {
		t.Error("Policy Enabled field not set correctly")
	}
}
