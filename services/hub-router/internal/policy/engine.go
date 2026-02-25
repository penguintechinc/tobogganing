// Package policy implements the network policy evaluation engine for the hub-router.
//
// The engine compiles raw policy definitions (fetched from hub-api) into optimised
// rule structures and evaluates them against packet metadata with O(n) linear scan
// ordered by specificity then priority.
package policy

import (
	"fmt"
	"net"
	"sort"
	"sync"

	log "github.com/sirupsen/logrus"
)

// ActionAllow and ActionDeny are the two terminal actions a rule can produce.
const (
	ActionAllow = "allow"
	ActionDeny  = "deny"
)

// Packet represents the metadata extracted from an observed network packet.
// Fields may be nil/empty when the relevant header information is unavailable.
type Packet struct {
	SrcIP    net.IP
	DstIP    net.IP
	SrcPort  int
	DstPort  int
	Protocol string
	Domain   string
	UserID   string
	GroupIDs []string
}

// RawPolicy is the un-compiled policy representation received from the API layer.
// It mirrors the hub-api JSON schema and is converted to PolicyRule by compileRule.
type RawPolicy struct {
	ID        string
	Name      string
	Priority  int
	Action    string
	Domains   []string
	Ports     []string
	Protocols []string
	// CIDRs holds destination address ranges (legacy combined field).
	CIDRs    []string
	// SrcCIDRs holds source address ranges.
	SrcCIDRs []string
	Users    []string
	Groups   []string
	Enabled  bool
}

// PolicyRule is the compiled, match-ready form of a RawPolicy.
// CIDR strings are pre-parsed into net.IPNet pointers for efficient evaluation.
type PolicyRule struct {
	ID          string
	Name        string
	Priority    int
	Action      string
	Domains     map[string]struct{}
	Ports       map[string]struct{}
	Protocols   map[string]struct{}
	// CIDRNets contains compiled destination CIDR networks.
	CIDRNets    []*net.IPNet
	// SrcCIDRNets contains compiled source CIDR networks.
	SrcCIDRNets []*net.IPNet
	Users       map[string]struct{}
	Groups      map[string]struct{}
	// Specificity is used to sort rules: more-specific rules are evaluated first.
	Specificity int
}

// Engine evaluates network packets against a compiled set of PolicyRules.
// It is safe to update the rule set concurrently via LoadPolicies.
type Engine struct {
	mu    sync.RWMutex
	rules []*PolicyRule
}

// NewEngine constructs an empty policy engine.
func NewEngine() *Engine {
	return &Engine{}
}

// LoadPolicies replaces the current rule set with a freshly compiled set derived
// from the provided raw policies. Invalid policies are logged and skipped.
func (pe *Engine) LoadPolicies(raw []RawPolicy) {
	compiled := make([]*PolicyRule, 0, len(raw))

	for _, rp := range raw {
		if !rp.Enabled {
			continue
		}
		rule, err := compileRule(rp)
		if err != nil {
			log.Errorf("policy engine: failed to compile rule %q (%s): %v", rp.Name, rp.ID, err)
			continue
		}
		compiled = append(compiled, rule)
	}

	// Sort by descending specificity, then ascending priority so that the most
	// specific, highest-priority rule wins on the first match.
	sort.Slice(compiled, func(i, j int) bool {
		if compiled[i].Specificity != compiled[j].Specificity {
			return compiled[i].Specificity > compiled[j].Specificity
		}
		return compiled[i].Priority < compiled[j].Priority
	})

	pe.mu.Lock()
	pe.rules = compiled
	pe.mu.Unlock()

	log.Infof("policy engine: loaded %d rules from %d raw policies", len(compiled), len(raw))
}

// Evaluate returns the action ("allow" or "deny") that applies to pkt.
// If no rule matches, the default action is "deny".
func (pe *Engine) Evaluate(pkt *Packet) string {
	pe.mu.RLock()
	rules := pe.rules
	pe.mu.RUnlock()

	for _, rule := range rules {
		if pe.ruleMatches(rule, pkt) {
			log.Debugf("policy engine: packet matched rule %q action=%s", rule.Name, rule.Action)
			return rule.Action
		}
	}

	log.Debugf("policy engine: no rule matched, defaulting to deny")
	return ActionDeny
}

// ruleMatches returns true when every non-empty criterion in rule matches pkt.
// An empty criterion is treated as a wildcard (matches anything).
func (pe *Engine) ruleMatches(rule *PolicyRule, pkt *Packet) bool {
	// Check users
	if len(rule.Users) > 0 {
		if _, ok := rule.Users[pkt.UserID]; !ok {
			matched := false
			for _, g := range pkt.GroupIDs {
				if _, ok := rule.Groups[g]; ok {
					matched = true
					break
				}
			}
			if !matched {
				return false
			}
		}
	}

	// Check groups (independent of user check when Users is empty)
	if len(rule.Groups) > 0 && len(rule.Users) == 0 {
		matched := false
		for _, g := range pkt.GroupIDs {
			if _, ok := rule.Groups[g]; ok {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	// Check domain
	if len(rule.Domains) > 0 && pkt.Domain != "" {
		if _, ok := rule.Domains[pkt.Domain]; !ok {
			return false
		}
	}

	// Check protocol
	if len(rule.Protocols) > 0 && pkt.Protocol != "" {
		if _, ok := rule.Protocols[pkt.Protocol]; !ok {
			return false
		}
	}

	// Check destination port
	if len(rule.Ports) > 0 && pkt.DstPort != 0 {
		portStr := portToString(pkt.DstPort)
		if _, ok := rule.Ports[portStr]; !ok {
			return false
		}
	}

	// Check destination CIDRs
	if len(rule.CIDRNets) > 0 && pkt.DstIP != nil {
		if !pe.cidrMatches(rule.CIDRNets, pkt.DstIP) {
			return false
		}
	}

	// Check source CIDRs
	if len(rule.SrcCIDRNets) > 0 && pkt.SrcIP != nil {
		if !pe.cidrMatches(rule.SrcCIDRNets, pkt.SrcIP) {
			return false
		}
	}

	return true
}

// cidrMatches returns true when ip is contained in at least one of nets.
func (pe *Engine) cidrMatches(nets []*net.IPNet, ip net.IP) bool {
	for _, n := range nets {
		if n.Contains(ip) {
			return true
		}
	}
	return false
}

// compileRule parses a RawPolicy into a ready-to-evaluate PolicyRule.
func compileRule(p RawPolicy) (*PolicyRule, error) {
	rule := &PolicyRule{
		ID:       p.ID,
		Name:     p.Name,
		Priority: p.Priority,
		Action:   p.Action,
	}

	// Build set-based lookups for O(1) membership tests.
	if len(p.Domains) > 0 {
		rule.Domains = toSet(p.Domains)
		rule.Specificity++
	}
	if len(p.Protocols) > 0 {
		rule.Protocols = toSet(p.Protocols)
		rule.Specificity++
	}
	if len(p.Ports) > 0 {
		rule.Ports = toSet(p.Ports)
		rule.Specificity++
	}
	if len(p.Users) > 0 {
		rule.Users = toSet(p.Users)
		rule.Specificity++
	}
	if len(p.Groups) > 0 {
		rule.Groups = toSet(p.Groups)
		rule.Specificity++
	}

	// Parse destination CIDR networks.
	for _, cidrStr := range p.CIDRs {
		_, cidrNet, err := net.ParseCIDR(cidrStr)
		if err != nil {
			return nil, err
		}
		rule.CIDRNets = append(rule.CIDRNets, cidrNet)
	}
	if len(rule.CIDRNets) > 0 {
		rule.Specificity++
	}

	// Parse source CIDR networks.
	for _, cidrStr := range p.SrcCIDRs {
		_, cidrNet, err := net.ParseCIDR(cidrStr)
		if err != nil {
			return nil, err
		}
		rule.SrcCIDRNets = append(rule.SrcCIDRNets, cidrNet)
	}
	if len(rule.SrcCIDRNets) > 0 {
		rule.Specificity++
	}

	return rule, nil
}

// toSet converts a string slice into a map for O(1) membership testing.
func toSet(items []string) map[string]struct{} {
	m := make(map[string]struct{}, len(items))
	for _, item := range items {
		m[item] = struct{}{}
	}
	return m
}

// portToString converts a port number to its string representation.
func portToString(port int) string {
	if port <= 0 {
		return ""
	}
	// Simple int-to-string without fmt to avoid unnecessary allocations.
	return fmt.Sprintf("%d", port)
}
