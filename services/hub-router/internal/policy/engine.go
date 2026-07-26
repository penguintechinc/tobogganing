// Package policy implements the policy enforcement engine for the Tobogganing
// hub-router.
//
// The policy engine evaluates network packets against a set of policies fetched
// from hub-api. Policies are evaluated in priority order (lowest number = highest
// priority), with deny rules taking precedence over allow rules at the same
// priority level (deny-overrides model).
//
// Policy dimensions:
//   - Domain: DNS name or wildcard pattern (e.g., "*.example.com")
//   - Ports: TCP/UDP port numbers or ranges (e.g., "80", "8000-9000")
//   - Protocols: Network protocol (tcp, udp, icmp)
//   - IP CIDR: Source or destination IP ranges (e.g., "10.0.0.0/8")
//   - Users: Individual user IDs
//   - Groups: User group IDs
//
// Evaluation strategy:
//   - Most-specific-first: a policy matching on more dimensions takes precedence
//   - Deny overrides allow at the same specificity/priority level
//   - Default action is deny (explicit allow required)
//
// The engine maintains a local cache of policies with TTL, and subscribes to
// real-time updates from hub-api via gRPC streaming to keep policies current.
// When policies are updated, both the Go-level policy maps and the BPF maps
// (for fast-path filtering) are refreshed.
package policy

import (
	"fmt"
	"net"
	"sort"
	"strings"
	"sync"
	"time"

	log "github.com/sirupsen/logrus"
)

// PolicyDecision represents the result of evaluating a packet against policies.
type PolicyDecision int

const (
	// DecisionAllow permits the packet.
	DecisionAllow PolicyDecision = iota
	// DecisionDeny blocks the packet.
	DecisionDeny
	// DecisionLog permits the packet but logs it for auditing.
	DecisionLog
)

// String returns a human-readable representation of the policy decision.
func (d PolicyDecision) String() string {
	switch d {
	case DecisionAllow:
		return "allow"
	case DecisionDeny:
		return "deny"
	case DecisionLog:
		return "log"
	default:
		return "unknown"
	}
}

// PolicyRule is an internal representation of a policy rule, optimized
// for fast evaluation.
type PolicyRule struct {
	// ID is the unique policy identifier.
	ID string
	// Name is the human-readable policy name.
	Name string
	// Priority determines evaluation order (lower = higher priority).
	Priority int
	// Action is the decision to apply when this rule matches.
	Action PolicyDecision
	// Domains are compiled domain patterns for matching.
	Domains []string
	// PortRanges are parsed port ranges for matching.
	PortRanges []PortRange
	// Protocols are the applicable protocols.
	Protocols []string
	// CIDRNets are parsed CIDR networks for IP matching.
	CIDRNets []*net.IPNet
	// Users are the user IDs this rule applies to (empty = all users).
	Users map[string]bool
	// Groups are the group IDs this rule applies to (empty = all groups).
	Groups map[string]bool
	// Scope limits this rule to a specific overlay (e.g., "wireguard", "openziti").
	// Empty scope means the rule applies to all overlays.
	Scope string
	// Specificity is the number of non-empty dimensions (for tie-breaking).
	Specificity int
}

// PortRange represents a range of ports (inclusive).
type PortRange struct {
	Start uint16
	End   uint16
}

// PacketInfo contains the relevant fields extracted from a packet
// for policy evaluation.
type PacketInfo struct {
	// SrcIP is the source IP address.
	SrcIP net.IP
	// DstIP is the destination IP address.
	DstIP net.IP
	// SrcPort is the source port number.
	SrcPort uint16
	// DstPort is the destination port number.
	DstPort uint16
	// Protocol is the transport protocol (tcp, udp, icmp).
	Protocol string
	// Domain is the destination domain name (if resolved via DNS).
	Domain string
	// UserID is the authenticated user ID.
	UserID string
	// GroupIDs are the user's group memberships.
	GroupIDs []string
	// OverlayScope identifies which overlay this packet arrived through.
	// Valid values: "wireguard", "openziti", or "" (matches any).
	OverlayScope string
}

// PolicyEngine evaluates packets against the current policy set.
type PolicyEngine struct {
	// rules is the compiled, sorted list of policy rules.
	rules []PolicyRule

	// cacheTTL is how long policy cache entries are valid.
	cacheTTL time.Duration

	// lastUpdate is when policies were last refreshed.
	lastUpdate time.Time

	// mu protects concurrent access to the rule set.
	mu sync.RWMutex

	// onBPFMapUpdate is called when policies change and BPF maps
	// need to be refreshed. This allows the policy engine to trigger
	// updates to the XDP fast-path filter maps.
	onBPFMapUpdate func(rules []PolicyRule) error
}

// NewPolicyEngine creates a new policy engine.
func NewPolicyEngine() *PolicyEngine {
	return &PolicyEngine{
		cacheTTL: 5 * time.Minute,
	}
}

// SetBPFMapUpdateHandler registers a callback that is invoked when policies
// change and BPF maps need to be updated. This bridges the Go policy engine
// with the XDP fast-path filter.
func (pe *PolicyEngine) SetBPFMapUpdateHandler(handler func(rules []PolicyRule) error) {
	pe.mu.Lock()
	defer pe.mu.Unlock()
	pe.onBPFMapUpdate = handler
}

// Evaluate evaluates a packet against the current policy set and returns
// the policy decision.
//
// Evaluation order:
//  1. Sort matching rules by priority (ascending)
//  2. At the same priority, sort by specificity (descending)
//  3. At the same priority and specificity, deny overrides allow
//  4. Return the decision from the highest-priority matching rule
//  5. Default: deny (explicit allow required)
func (pe *PolicyEngine) Evaluate(pkt *PacketInfo) PolicyDecision {
	pe.mu.RLock()
	defer pe.mu.RUnlock()

	if len(pe.rules) == 0 {
		// No policies loaded - default deny
		log.Warn("No policies loaded, default deny")
		return DecisionDeny
	}

	// Find all matching rules
	var matches []PolicyRule
	for _, rule := range pe.rules {
		if pe.ruleMatches(&rule, pkt) {
			matches = append(matches, rule)
		}
	}

	if len(matches) == 0 {
		// No matching rules - default deny
		return DecisionDeny
	}

	// Rules are already sorted by priority (ascending).
	// Among matches with the same priority, deny overrides allow.
	bestPriority := matches[0].Priority
	for _, rule := range matches {
		if rule.Priority > bestPriority {
			break // No more rules at the best priority level
		}
		if rule.Action == DecisionDeny {
			return DecisionDeny // Deny overrides at same priority
		}
	}

	// Return the first match's action (highest priority, most specific)
	return matches[0].Action
}

// ruleMatches checks if a rule matches the given packet info.
// A rule matches if ALL non-empty dimensions match the packet.
// Empty dimensions are treated as wildcards (match everything).
func (pe *PolicyEngine) ruleMatches(rule *PolicyRule, pkt *PacketInfo) bool {
	// Check domains
	if len(rule.Domains) > 0 && pkt.Domain != "" {
		if !pe.domainMatches(rule.Domains, pkt.Domain) {
			return false
		}
	}

	// Check ports (destination port)
	if len(rule.PortRanges) > 0 && pkt.DstPort > 0 {
		if !pe.portMatches(rule.PortRanges, pkt.DstPort) {
			return false
		}
	}

	// Check protocols
	if len(rule.Protocols) > 0 && pkt.Protocol != "" {
		if !pe.protocolMatches(rule.Protocols, pkt.Protocol) {
			return false
		}
	}

	// Check CIDRs (destination IP)
	if len(rule.CIDRNets) > 0 && pkt.DstIP != nil {
		if !pe.cidrMatches(rule.CIDRNets, pkt.DstIP) {
			return false
		}
	}

	// Check users
	if len(rule.Users) > 0 && pkt.UserID != "" {
		if !rule.Users[pkt.UserID] {
			return false
		}
	}

	// Check groups
	if len(rule.Groups) > 0 && len(pkt.GroupIDs) > 0 {
		groupMatch := false
		for _, gid := range pkt.GroupIDs {
			if rule.Groups[gid] {
				groupMatch = true
				break
			}
		}
		if !groupMatch {
			return false
		}
	}

	// Check overlay scope
	if rule.Scope != "" && pkt.OverlayScope != "" {
		if rule.Scope != pkt.OverlayScope {
			return false
		}
	}

	return true
}

// domainMatches checks if any domain pattern matches the given domain.
// Supports wildcard matching (e.g., "*.example.com" matches "foo.example.com").
func (pe *PolicyEngine) domainMatches(patterns []string, domain string) bool {
	domain = strings.ToLower(domain)
	for _, pattern := range patterns {
		pattern = strings.ToLower(pattern)
		if pattern == domain {
			return true
		}
		// Wildcard matching: *.example.com matches foo.example.com
		if strings.HasPrefix(pattern, "*.") {
			suffix := pattern[1:] // ".example.com"
			if strings.HasSuffix(domain, suffix) {
				return true
			}
		}
	}
	return false
}

// portMatches checks if the port falls within any of the port ranges.
func (pe *PolicyEngine) portMatches(ranges []PortRange, port uint16) bool {
	for _, pr := range ranges {
		if port >= pr.Start && port <= pr.End {
			return true
		}
	}
	return false
}

// protocolMatches checks if the protocol matches any in the list.
func (pe *PolicyEngine) protocolMatches(protocols []string, protocol string) bool {
	protocol = strings.ToLower(protocol)
	for _, p := range protocols {
		if strings.ToLower(p) == protocol {
			return true
		}
	}
	return false
}

// cidrMatches checks if the IP falls within any of the CIDR ranges.
func (pe *PolicyEngine) cidrMatches(cidrs []*net.IPNet, ip net.IP) bool {
	for _, cidr := range cidrs {
		if cidr.Contains(ip) {
			return true
		}
	}
	return false
}

// OnPolicyUpdate handles policy updates from hub-api.
// It compiles the new policies into optimized rules, updates the local
// cache, and triggers BPF map updates for the XDP fast-path filter.
func (pe *PolicyEngine) OnPolicyUpdate(policies []RawPolicy) error {
	pe.mu.Lock()
	defer pe.mu.Unlock()

	// Compile policies into optimized rules
	rules := make([]PolicyRule, 0, len(policies))
	for _, p := range policies {
		if !p.Enabled {
			continue
		}

		rule, err := pe.compileRule(p)
		if err != nil {
			log.Warnf("Failed to compile policy %s: %v (skipping)", p.ID, err)
			continue
		}
		rules = append(rules, *rule)
	}

	// Sort rules by priority (ascending), then by specificity (descending)
	sort.Slice(rules, func(i, j int) bool {
		if rules[i].Priority != rules[j].Priority {
			return rules[i].Priority < rules[j].Priority
		}
		return rules[i].Specificity > rules[j].Specificity
	})

	pe.rules = rules
	pe.lastUpdate = time.Now()

	log.Infof("Policy engine updated: %d active rules", len(rules))

	// Trigger BPF map update for fast-path filtering
	if pe.onBPFMapUpdate != nil {
		if err := pe.onBPFMapUpdate(rules); err != nil {
			log.Errorf("Failed to update BPF maps: %v", err)
			// Continue - Go-level policies are still active
		} else {
			log.Info("BPF maps updated with new policy rules")
		}
	}

	return nil
}

// RawPolicy represents a policy as received from hub-api before compilation.
type RawPolicy struct {
	ID        string   `json:"id"`
	Name      string   `json:"name"`
	Priority  int      `json:"priority"`
	Action    string   `json:"action"`
	Domains   []string `json:"domains,omitempty"`
	Ports     []string `json:"ports,omitempty"`
	Protocols []string `json:"protocols,omitempty"`
	CIDRs     []string `json:"cidrs,omitempty"`
	Users     []string `json:"users,omitempty"`
	Groups    []string `json:"groups,omitempty"`
	Scope     string   `json:"scope,omitempty"`
	Enabled   bool     `json:"enabled"`
}

// compileRule converts a raw policy into an optimized PolicyRule.
func (pe *PolicyEngine) compileRule(p RawPolicy) (*PolicyRule, error) {
	rule := &PolicyRule{
		ID:        p.ID,
		Name:      p.Name,
		Priority:  p.Priority,
		Domains:   p.Domains,
		Protocols: p.Protocols,
	}

	// Parse action
	switch strings.ToLower(p.Action) {
	case "allow":
		rule.Action = DecisionAllow
	case "deny":
		rule.Action = DecisionDeny
	case "log":
		rule.Action = DecisionLog
	default:
		rule.Action = DecisionDeny // Default to deny for unknown actions
	}

	// Parse port ranges
	for _, portStr := range p.Ports {
		pr, err := parsePortRange(portStr)
		if err != nil {
			return nil, err
		}
		rule.PortRanges = append(rule.PortRanges, pr)
	}

	// Parse CIDR networks
	for _, cidrStr := range p.CIDRs {
		_, cidrNet, err := net.ParseCIDR(cidrStr)
		if err != nil {
			return nil, err
		}
		rule.CIDRNets = append(rule.CIDRNets, cidrNet)
	}

	// Build user map
	if len(p.Users) > 0 {
		rule.Users = make(map[string]bool, len(p.Users))
		for _, u := range p.Users {
			rule.Users[u] = true
		}
	}

	// Build group map
	if len(p.Groups) > 0 {
		rule.Groups = make(map[string]bool, len(p.Groups))
		for _, g := range p.Groups {
			rule.Groups[g] = true
		}
	}

	// Copy overlay scope
	rule.Scope = p.Scope

	// Calculate specificity (number of non-empty dimensions)
	if len(rule.Domains) > 0 {
		rule.Specificity++
	}
	if len(rule.PortRanges) > 0 {
		rule.Specificity++
	}
	if len(rule.Protocols) > 0 {
		rule.Specificity++
	}
	if len(rule.CIDRNets) > 0 {
		rule.Specificity++
	}
	if len(rule.Users) > 0 {
		rule.Specificity++
	}
	if len(rule.Groups) > 0 {
		rule.Specificity++
	}
	if rule.Scope != "" {
		rule.Specificity++
	}

	return rule, nil
}

// parsePortRange parses a port or port range string (e.g., "80", "8000-9000").
func parsePortRange(s string) (PortRange, error) {
	s = strings.TrimSpace(s)

	if idx := strings.Index(s, "-"); idx != -1 {
		// Range: "8000-9000"
		startStr := strings.TrimSpace(s[:idx])
		endStr := strings.TrimSpace(s[idx+1:])

		var start, end uint16
		if _, err := parseUint16(startStr, &start); err != nil {
			return PortRange{}, err
		}
		if _, err := parseUint16(endStr, &end); err != nil {
			return PortRange{}, err
		}

		if start > end {
			start, end = end, start
		}
		return PortRange{Start: start, End: end}, nil
	}

	// Single port: "80"
	var port uint16
	if _, err := parseUint16(s, &port); err != nil {
		return PortRange{}, err
	}
	return PortRange{Start: port, End: port}, nil
}

// parseUint16 parses a string as a uint16.
func parseUint16(s string, result *uint16) (bool, error) {
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			return false, fmt.Errorf("invalid port number: %s", s)
		}
		n = n*10 + int(c-'0')
		if n > 65535 {
			return false, fmt.Errorf("port number out of range: %s", s)
		}
	}
	*result = uint16(n)
	return true, nil
}

// RuleCount returns the number of active rules in the engine.
func (pe *PolicyEngine) RuleCount() int {
	pe.mu.RLock()
	defer pe.mu.RUnlock()
	return len(pe.rules)
}

// LastUpdate returns the time of the last policy update.
func (pe *PolicyEngine) LastUpdate() time.Time {
	pe.mu.RLock()
	defer pe.mu.RUnlock()
	return pe.lastUpdate
}
