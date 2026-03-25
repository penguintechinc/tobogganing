package main

import (
	"github.com/tobogganing/headend/internal/api"
	"github.com/tobogganing/headend/internal/policy"
)

// convertPolicies transforms API policies into the format expected by the
// policy engine.  The API Policy struct uses separate SrcCIDRs/DstCIDRs
// while the engine's RawPolicy keeps a combined CIDRs field for destination
// matching plus separate SrcCIDRs.
func convertPolicies(apiPolicies []api.Policy) []policy.RawPolicy {
	raw := make([]policy.RawPolicy, 0, len(apiPolicies))
	for _, p := range apiPolicies {
		rp := policy.RawPolicy{
			ID:        p.ID,
			Name:      p.Name,
			Priority:  p.Priority,
			Action:    p.Action,
			Domains:   p.Domains,
			Ports:     p.Ports,
			Protocols: p.Protocols,
			CIDRs:     p.DstCIDRs,  // destination CIDRs -> engine's CIDRs field
			SrcCIDRs:  p.SrcCIDRs,
			Users:     p.Users,
			Groups:    p.Groups,
			Enabled:   p.Enabled,
		}
		// Fall back to the legacy combined CIDRs field if DstCIDRs is empty
		if len(rp.CIDRs) == 0 && len(p.CIDRs) > 0 {
			rp.CIDRs = p.CIDRs
		}
		raw = append(raw, rp)
	}
	return raw
}
