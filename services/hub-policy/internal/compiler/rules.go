// Package compiler converts hub-api policies into MarchProxy lever instructions.
package compiler

// CompiledRuleSet is the output of policy compilation — simple lever instructions
// that MarchProxy enforces locally with no controller round-trip per request.
type CompiledRuleSet struct {
	BlockCIDRs    []string          // e.g. "1.2.3.0/24"
	AllowCIDRs    []string          // e.g. "10.0.0.0/8"
	BlockDomains  []string          // e.g. "malware.example.com"
	AllowDomains  []string          // e.g. "*.internal.example.com"
	RouteClusters []ClusterDef      // routing targets
	RateLimits    map[string]int    // src_ip → packets-per-second cap
}

// ClusterDef represents a routable cluster endpoint group.
type ClusterDef struct {
	Name      string
	Endpoints []string
	LBPolicy  string // "ROUND_ROBIN", "LEAST_REQUEST", "WEIGHTED"
}

// Policy mirrors the hub-api Policy type.
type Policy struct {
	ID        string
	Name      string
	Priority  int
	Action    string
	Domains   []string
	Ports     []string
	Protocols []string
	CIDRs     []string
	Users     []string
	Groups    []string
	Enabled   bool
}

// Compiler converts hub-api policies into MarchProxy lever instructions.
type Compiler struct{}

// New creates a new Compiler instance.
func New() *Compiler { return &Compiler{} }

// Compile takes raw Policy objects from hub-api and returns a flat CompiledRuleSet.
// All evaluation logic lives here — MarchProxy receives only the compiled output.
func (c *Compiler) Compile(policies []Policy) CompiledRuleSet {
	result := CompiledRuleSet{
		RateLimits: make(map[string]int),
	}

	// TODO: implement — iterate policies, evaluate per dimension,
	// accumulate into CompiledRuleSet
	// - Block/allow CIDRs based on policy action and destination
	// - Block/allow domains based on policy action
	// - Extract rate limit rules
	// - Build routing cluster definitions

	return result
}
