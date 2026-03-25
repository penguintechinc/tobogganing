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
	// Tenant is the tenant identifier attached to the connection context.
	Tenant string
	// Scopes holds the OAuth2/OIDC scopes granted to the connecting workload
	// or user (resource:action pairs, e.g. "policies:read").
	Scopes []string
	// SpiffeID is the SPIFFE Verifiable Identity Document URI presented by
	// the workload TLS certificate (e.g. "spiffe://domain/path/...").
	SpiffeID string
	// OverlayScope identifies the network overlay path that delivered this
	// packet.  Valid values mirror policy Scope: "wireguard", "openziti",
	// "k8s", "both".  An empty string skips overlay-scope filtering.
	OverlayScope string
}

// validOverlayScopes enumerates the accepted values for the Scope field on
// RawPolicy.  An empty string is treated as a wildcard (matches any overlay).
var validOverlayScopes = map[string]struct{}{
	"":          {},
	"wireguard": {},
	"openziti":  {},
	"k8s":       {},
	"both":      {},
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
	CIDRs []string
	// SrcCIDRs holds source address ranges.
	SrcCIDRs []string
	Users    []string
	Groups   []string
	Enabled  bool
	// Scope restricts rule enforcement to a specific overlay path.
	// Valid values: "" (any), "wireguard", "openziti", "k8s", "both".
	// Rules are evaluated by every overlay; the engine filters out rules
	// whose Scope does not match the packet's overlay context.
	Scope string
	// TenantID restricts the rule to connections originating within the named
	// tenant.  Empty string means the rule applies to all tenants.
	TenantID string
	// RequiredScopes lists OAuth2/OIDC scopes that the connecting workload or
	// user must hold before this rule fires.  ALL listed scopes must be
	// satisfied (logical AND).  An empty slice is a wildcard.
	RequiredScopes []string
	// SpiffeIDs lists SPIFFE ID patterns that the workload certificate must
	// match.  Matching is exact or path-segment wildcard (see spiffeIDMatches).
	// An empty slice is a wildcard.
	SpiffeIDs []string
}

// PolicyRule is the compiled, match-ready form of a RawPolicy.
// CIDR strings are pre-parsed into net.IPNet pointers for efficient evaluation.
type PolicyRule struct {
	ID        string
	Name      string
	Priority  int
	Action    string
	Domains   map[string]struct{}
	Ports     map[string]struct{}
	Protocols map[string]struct{}
	// CIDRNets contains compiled destination CIDR networks.
	CIDRNets []*net.IPNet
	// SrcCIDRNets contains compiled source CIDR networks.
	SrcCIDRNets []*net.IPNet
	Users       map[string]struct{}
	Groups      map[string]struct{}
	// Specificity is used to sort rules: more-specific rules are evaluated first.
	Specificity int
	// Scope restricts rule evaluation to a specific overlay path.
	// Valid values: "" (wildcard), "wireguard", "openziti", "k8s", "both".
	// An empty Scope matches every overlay context.
	Scope string
	// TenantID restricts matching to a single tenant.  Empty = wildcard.
	TenantID string
	// Scopes is the compiled set of required OAuth2/OIDC scopes for O(1)
	// membership testing.  The packet must carry ALL entries in the set.
	Scopes map[string]bool
	// SpiffeIDs holds SPIFFE ID patterns verbatim from the raw policy.
	// Kept as a slice because matching requires segment-by-segment comparison
	// rather than a simple hash lookup.
	SpiffeIDs []string
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
	// -----------------------------------------------------------------------
	// Identity dimensions — checked first because string/map operations are
	// cheaper than the CIDR containment loops that follow.
	// -----------------------------------------------------------------------

	// Check tenant: if the rule is tenant-scoped, the packet must originate
	// from that same tenant.
	if rule.TenantID != "" && pkt.Tenant != rule.TenantID {
		return false
	}

	// Check overlay scope: a non-empty rule.Scope restricts the rule to
	// packets that arrived via a specific overlay path.
	//
	// Matching semantics:
	//   - rule.Scope == ""       → wildcard, matches any overlay.
	//   - rule.Scope == "both"   → matches any overlay (explicit wildcard).
	//   - rule.Scope == "wireguard" | "openziti" | "k8s"
	//                            → matches only when pkt.OverlayScope equals
	//                              the rule scope OR pkt.OverlayScope is empty
	//                              (caller did not set overlay context).
	if !overlayScoreMatches(rule.Scope, pkt.OverlayScope) {
		return false
	}

	// Check scopes: the packet must carry ALL required scopes.  Each required
	// scope may be satisfied by any scope in pkt.Scopes via wildcard rules
	// (mirrors the Python scope_matches logic in auth/scopes.py).
	if len(rule.Scopes) > 0 {
		for required := range rule.Scopes {
			satisfied := false
			for _, available := range pkt.Scopes {
				if scopeMatches(required, available) {
					satisfied = true
					break
				}
			}
			if !satisfied {
				return false
			}
		}
	}

	// Check SPIFFE ID: the workload certificate must match at least one of
	// the patterns listed in the rule.
	if len(rule.SpiffeIDs) > 0 {
		matched := false
		for _, pattern := range rule.SpiffeIDs {
			if spiffeIDMatches(pattern, pkt.SpiffeID) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	// -----------------------------------------------------------------------
	// Existing network / identity (user/group) dimensions
	// -----------------------------------------------------------------------

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

	// Overlay scope — validate and copy verbatim.  Unknown scope values are
	// rejected at compile time so that operators are alerted to misconfigured
	// policy rows rather than silently getting wildcard-matched rules.
	if p.Scope != "" {
		if _, ok := validOverlayScopes[p.Scope]; !ok {
			return nil, fmt.Errorf("policy %q has invalid overlay scope %q (valid: wireguard, openziti, k8s, both)", p.Name, p.Scope)
		}
		rule.Scope = p.Scope
		rule.Specificity++
	}

	// Identity dimensions — evaluated before network dimensions in ruleMatches
	// because string comparisons are cheaper than CIDR containment checks.
	if p.TenantID != "" {
		rule.TenantID = p.TenantID
		rule.Specificity++
	}

	if len(p.RequiredScopes) > 0 {
		rule.Scopes = make(map[string]bool, len(p.RequiredScopes))
		for _, s := range p.RequiredScopes {
			rule.Scopes[s] = true
		}
		rule.Specificity++
	}

	if len(p.SpiffeIDs) > 0 {
		rule.SpiffeIDs = make([]string, len(p.SpiffeIDs))
		copy(rule.SpiffeIDs, p.SpiffeIDs)
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

// overlayScoreMatches reports whether pktOverlay satisfies ruleScope.
//
// Matching table:
//
//	ruleScope   pktOverlay   result
//	----------  ----------   ------
//	""          any          true  (rule is a wildcard)
//	"both"      any          true  (explicit wildcard)
//	"wireguard" ""           true  (packet has no overlay context set)
//	"wireguard" "wireguard"  true
//	"wireguard" "openziti"   false
//	"openziti"  "openziti"   true
//	"openziti"  "wireguard"  false
//	"k8s"       "k8s"        true
//	"k8s"       "wireguard"  false
func overlayScoreMatches(ruleScope, pktOverlay string) bool {
	if ruleScope == "" || ruleScope == "both" {
		return true
	}
	// If the packet carries no overlay context the rule still applies — the
	// call site simply did not set OverlayScope (e.g. unit tests, legacy paths).
	if pktOverlay == "" {
		return true
	}
	return ruleScope == pktOverlay
}

// scopeMatches returns true when available satisfies the required scope.
//
// Matching rules (mirrors auth/scopes.py#scope_matches):
//   - Exact match: "policies:read" satisfies "policies:read".
//   - "*:*" satisfies any scope.
//   - "*:<action>" satisfies "<any-resource>:<action>".
//   - "<resource>:*" satisfies "<resource>:<any-action>".
func scopeMatches(required, available string) bool {
	if available == required {
		return true
	}

	availRes, _, availAction := partitionScope(available)
	reqRes, _, reqAction := partitionScope(required)

	// "*:*" matches everything.
	if availRes == "*" && availAction == "*" {
		return true
	}

	// "*:<action>" matches any resource with the same action.
	if availRes == "*" && availAction == reqAction {
		return true
	}

	// "<resource>:*" matches any action on the same resource.
	if availRes == reqRes && availAction == "*" {
		return true
	}

	return false
}

// partitionScope splits a "resource:action" scope string at the first colon.
// If there is no colon the entire string is returned as the resource with an
// empty action — callers should treat that as a malformed scope.
func partitionScope(scope string) (resource, sep, action string) {
	for i := 0; i < len(scope); i++ {
		if scope[i] == ':' {
			return scope[:i], ":", scope[i+1:]
		}
	}
	return scope, "", ""
}

// spiffeIDMatches reports whether actual matches pattern.
//
// Pattern syntax: path segments separated by "/".  A "*" in any single
// segment position matches exactly one corresponding segment in actual.
// Both pattern and actual must have the same number of segments.
//
// Examples:
//
//	spiffeIDMatches("spiffe://acme.io/*/backend/*", "spiffe://acme.io/cluster1/backend/api") → true
//	spiffeIDMatches("spiffe://acme.io/ns/svc",      "spiffe://acme.io/ns/svc")              → true
//	spiffeIDMatches("spiffe://acme.io/*/svc",        "spiffe://acme.io/ns/other/svc")        → false
func spiffeIDMatches(pattern, actual string) bool {
	// Fast-path: exact match.
	if pattern == actual {
		return true
	}

	// Split both URIs into path segments.
	patternSegs := splitPath(pattern)
	actualSegs := splitPath(actual)

	// Segment counts must match (no recursive "**" support yet).
	if len(patternSegs) != len(actualSegs) {
		return false
	}

	for i, seg := range patternSegs {
		if seg == "*" {
			// Wildcard: matches any single segment (including empty).
			continue
		}
		if seg != actualSegs[i] {
			return false
		}
	}
	return true
}

// splitPath splits a URI or path string on "/" without allocating a temporary
// slice via strings.Split — keeps the hot path allocation-lean.
func splitPath(s string) []string {
	// Pre-count slashes to allocate exactly the right capacity.
	n := 1
	for i := 0; i < len(s); i++ {
		if s[i] == '/' {
			n++
		}
	}
	out := make([]string, 0, n)
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == '/' {
			out = append(out, s[start:i])
			start = i + 1
		}
	}
	out = append(out, s[start:])
	return out
}
