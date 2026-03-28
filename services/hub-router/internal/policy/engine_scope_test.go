package policy

import (
	"net"
	"testing"
)

func TestOverlayScopeFiltering(t *testing.T) {
	engine := NewPolicyEngine()

	// Policy that only applies to openziti traffic
	engine.OnPolicyUpdate([]RawPolicy{
		{
			ID:       "ziti-only",
			Name:     "Allow OpenZiti",
			Priority: 10,
			Action:   "allow",
			Domains:  []string{"*.example.com"},
			Scope:    "openziti",
			Enabled:  true,
		},
		{
			ID:       "wg-deny",
			Name:     "Deny WireGuard to example.com",
			Priority: 10,
			Action:   "deny",
			Domains:  []string{"*.example.com"},
			Scope:    "wireguard",
			Enabled:  true,
		},
	})

	// OpenZiti traffic should be allowed
	decision := engine.Evaluate(&PacketInfo{
		DstIP:        net.ParseIP("10.0.0.1"),
		Domain:       "app.example.com",
		OverlayScope: "openziti",
	})
	if decision != DecisionAllow {
		t.Fatalf("expected allow for openziti, got %v", decision)
	}

	// WireGuard traffic should be denied
	decision = engine.Evaluate(&PacketInfo{
		DstIP:        net.ParseIP("10.0.0.1"),
		Domain:       "app.example.com",
		OverlayScope: "wireguard",
	})
	if decision != DecisionDeny {
		t.Fatalf("expected deny for wireguard, got %v", decision)
	}
}

func TestEmptyScopeMatchesAll(t *testing.T) {
	engine := NewPolicyEngine()

	engine.OnPolicyUpdate([]RawPolicy{
		{
			ID:       "any-scope",
			Name:     "Allow All Overlays",
			Priority: 10,
			Action:   "allow",
			Domains:  []string{"*.example.com"},
			Scope:    "", // empty = matches all
			Enabled:  true,
		},
	})

	// Both scopes should match
	for _, scope := range []string{"openziti", "wireguard"} {
		decision := engine.Evaluate(&PacketInfo{
			DstIP:        net.ParseIP("10.0.0.1"),
			Domain:       "app.example.com",
			OverlayScope: scope,
		})
		if decision != DecisionAllow {
			t.Fatalf("expected allow for scope %q, got %v", scope, decision)
		}
	}
}
