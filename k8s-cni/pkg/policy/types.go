// Package policy provides network policy management and enforcement
// for the Tobogganing Kubernetes CNI.
//
// This package implements:
// - Kubernetes NetworkPolicy translation
// - Dynamic policy rule management
// - Default allow/deny behaviors
// - Namespace-aware policy enforcement
// - Integration with eBPF firewall programs
//
// The policy engine follows Kubernetes NetworkPolicy semantics with
// enhancements for Zero Trust networking and enterprise security.
package policy

import (
	"net"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
)

// Policy actions
const (
	ActionAllow = "allow"
	ActionDeny  = "deny" 
	ActionLog   = "log"
)

// Traffic directions
const (
	DirectionIngress = "ingress"
	DirectionEgress  = "egress"
	DirectionBoth    = "both"
)

// Protocol constants
const (
	ProtocolTCP  = "TCP"
	ProtocolUDP  = "UDP"
	ProtocolICMP = "ICMP"
	ProtocolAny  = ""
)

// Default policy behaviors
const (
	DefaultPolicyAllow = "allow"
	DefaultPolicyDeny  = "deny"
)

// NetworkPolicy represents a Kubernetes-style network policy
type NetworkPolicy struct {
	// Standard Kubernetes metadata
	metav1.ObjectMeta `json:",inline"`

	// Policy specification
	Spec NetworkPolicySpec `json:"spec"`

	// Policy status and enforcement info
	Status NetworkPolicyStatus `json:"status,omitempty"`
}

// NetworkPolicySpec defines the rules for network policy
type NetworkPolicySpec struct {
	// PodSelector selects the pods to which this NetworkPolicy object applies
	PodSelector metav1.LabelSelector `json:"podSelector"`

	// PolicyTypes is a list of rule types that the NetworkPolicy relates to
	PolicyTypes []PolicyType `json:"policyTypes,omitempty"`

	// Ingress rules for incoming traffic
	Ingress []NetworkPolicyIngressRule `json:"ingress,omitempty"`

	// Egress rules for outgoing traffic  
	Egress []NetworkPolicyEgressRule `json:"egress,omitempty"`

	// Priority for rule evaluation (lower = higher priority)
	Priority int32 `json:"priority,omitempty"`

	// DefaultAction when no rules match (allow/deny)
	DefaultAction string `json:"defaultAction,omitempty"`

	// Tobogganing-specific extensions
	TobogganiingExtensions *TobogganiingPolicyExtensions `json:"tobogganing,omitempty"`
}

// PolicyType defines the type of policy rule
type PolicyType string

const (
	PolicyTypeIngress PolicyType = "Ingress"
	PolicyTypeEgress  PolicyType = "Egress"
)

// NetworkPolicyIngressRule describes ingress traffic rules
type NetworkPolicyIngressRule struct {
	// Ports is a list of destination ports for incoming traffic
	Ports []NetworkPolicyPort `json:"ports,omitempty"`

	// From is a list of sources which should be able to access the pods
	From []NetworkPolicyPeer `json:"from,omitempty"`
}

// NetworkPolicyEgressRule describes egress traffic rules
type NetworkPolicyEgressRule struct {
	// Ports is a list of destination ports for outgoing traffic
	Ports []NetworkPolicyPort `json:"ports,omitempty"`

	// To is a list of destinations for outgoing traffic
	To []NetworkPolicyPeer `json:"to,omitempty"`
}

// NetworkPolicyPort describes a port to allow traffic on
type NetworkPolicyPort struct {
	// Protocol is the protocol (TCP, UDP, ICMP) which traffic must match
	Protocol *string `json:"protocol,omitempty"`

	// Port is the port or port range
	Port *intstr.IntOrString `json:"port,omitempty"`

	// EndPort indicates that the range of ports from Port to EndPort
	EndPort *int32 `json:"endPort,omitempty"`
}

// NetworkPolicyPeer describes a peer to allow traffic to/from
type NetworkPolicyPeer struct {
	// PodSelector selects pods in the same namespace
	PodSelector *metav1.LabelSelector `json:"podSelector,omitempty"`

	// NamespaceSelector selects entire namespaces
	NamespaceSelector *metav1.LabelSelector `json:"namespaceSelector,omitempty"`

	// IPBlock defines a CIDR block for IP-based rules
	IPBlock *IPBlock `json:"ipBlock,omitempty"`
}

// IPBlock describes a particular CIDR range
type IPBlock struct {
	// CIDR is a string representing the IP Block
	CIDR string `json:"cidr"`

	// Except is a slice of CIDRs that should not be included
	Except []string `json:"except,omitempty"`
}

// NetworkPolicyStatus describes the current state of the policy
type NetworkPolicyStatus struct {
	// Conditions represent the latest available observations
	Conditions []NetworkPolicyCondition `json:"conditions,omitempty"`

	// ActiveRules is the number of rules currently enforced
	ActiveRules int32 `json:"activeRules,omitempty"`

	// LastUpdated is when the policy was last updated
	LastUpdated metav1.Time `json:"lastUpdated,omitempty"`

	// EnforcementNodes lists nodes where policy is enforced
	EnforcementNodes []string `json:"enforcementNodes,omitempty"`
}

// NetworkPolicyCondition describes the state of a policy condition
type NetworkPolicyCondition struct {
	// Type of the condition
	Type NetworkPolicyConditionType `json:"type"`

	// Status of the condition
	Status string `json:"status"`

	// LastTransitionTime is the last time the condition transitioned
	LastTransitionTime metav1.Time `json:"lastTransitionTime,omitempty"`

	// Reason is the reason for the condition's last transition
	Reason string `json:"reason,omitempty"`

	// Message is a human-readable explanation
	Message string `json:"message,omitempty"`
}

// NetworkPolicyConditionType defines condition types
type NetworkPolicyConditionType string

const (
	PolicyConditionReady    NetworkPolicyConditionType = "Ready"
	PolicyConditionApplied  NetworkPolicyConditionType = "Applied"
	PolicyConditionError    NetworkPolicyConditionType = "Error"
)

// TobogganiingPolicyExtensions provides Tobogganing-specific extensions
type TobogganiingPolicyExtensions struct {
	// EnableAuditMode logs violations but doesn't block traffic
	EnableAuditMode bool `json:"enableAuditMode,omitempty"`

	// RequireEncryption requires all traffic to be encrypted
	RequireEncryption bool `json:"requireEncryption,omitempty"`

	// AllowedApplicationProtocols restricts application protocols
	AllowedApplicationProtocols []string `json:"allowedApplicationProtocols,omitempty"`

	// RateLimiting applies rate limits to matching traffic
	RateLimiting *RateLimitConfig `json:"rateLimiting,omitempty"`

	// Logging configuration for this policy
	Logging *LoggingConfig `json:"logging,omitempty"`

	// Metrics collection configuration
	Metrics *MetricsConfig `json:"metrics,omitempty"`
}

// RateLimitConfig defines rate limiting parameters
type RateLimitConfig struct {
	// RequestsPerSecond is the maximum requests per second
	RequestsPerSecond int32 `json:"requestsPerSecond,omitempty"`

	// BurstSize is the maximum burst size
	BurstSize int32 `json:"burstSize,omitempty"`

	// WindowSize is the time window for rate limiting
	WindowSize string `json:"windowSize,omitempty"`
}

// LoggingConfig defines logging parameters for policies
type LoggingConfig struct {
	// EnableViolationLogs logs policy violations
	EnableViolationLogs bool `json:"enableViolationLogs,omitempty"`

	// EnableFlowLogs logs all matching flows
	EnableFlowLogs bool `json:"enableFlowLogs,omitempty"`

	// LogLevel defines the logging level
	LogLevel string `json:"logLevel,omitempty"`

	// SyslogEndpoint for centralized logging
	SyslogEndpoint string `json:"syslogEndpoint,omitempty"`
}

// MetricsConfig defines metrics collection parameters
type MetricsConfig struct {
	// EnableMetrics enables metrics collection for this policy
	EnableMetrics bool `json:"enableMetrics,omitempty"`

	// MetricLabels are additional labels for metrics
	MetricLabels map[string]string `json:"metricLabels,omitempty"`

	// SampleRate is the sampling rate for metrics (0.0-1.0)
	SampleRate float64 `json:"sampleRate,omitempty"`
}

// PolicyRule represents a compiled policy rule ready for enforcement
type PolicyRule struct {
	// Unique identifier for the rule
	ID uint32 `json:"id"`

	// Human-readable name
	Name string `json:"name"`

	// Priority for rule evaluation (lower = higher priority)
	Priority int32 `json:"priority"`

	// Source policy information
	PolicyName      string `json:"policyName"`
	PolicyNamespace string `json:"policyNamespace"`

	// Rule conditions
	SrcSelector *PodSelector `json:"srcSelector,omitempty"`
	DstSelector *PodSelector `json:"dstSelector,omitempty"`
	Protocol    string       `json:"protocol,omitempty"`
	Ports       []PortRange  `json:"ports,omitempty"`
	Direction   string       `json:"direction"`

	// Action to take when rule matches
	Action string `json:"action"`

	// Additional metadata
	Labels      map[string]string `json:"labels,omitempty"`
	Annotations map[string]string `json:"annotations,omitempty"`

	// Enforcement state
	Enabled     bool      `json:"enabled"`
	CreatedAt   time.Time `json:"createdAt"`
	UpdatedAt   time.Time `json:"updatedAt"`
	LastApplied time.Time `json:"lastApplied,omitempty"`

	// Statistics
	MatchCount uint64 `json:"matchCount,omitempty"`
	ByteCount  uint64 `json:"byteCount,omitempty"`
	LastMatch  time.Time `json:"lastMatch,omitempty"`

	// Tobogganing extensions
	Extensions *RuleExtensions `json:"extensions,omitempty"`
}

// PodSelector represents pod selection criteria
type PodSelector struct {
	// Namespace for pod selection (empty = any namespace)
	Namespace string `json:"namespace,omitempty"`

	// Label selector for pods
	LabelSelector map[string]string `json:"labelSelector,omitempty"`

	// IP addresses for external endpoints
	IPBlocks []IPBlock `json:"ipBlocks,omitempty"`

	// ServiceAccount for selection
	ServiceAccount string `json:"serviceAccount,omitempty"`
}

// PortRange represents a range of ports
type PortRange struct {
	// Protocol (TCP/UDP/ICMP)
	Protocol string `json:"protocol,omitempty"`

	// Start port (inclusive)
	StartPort int32 `json:"startPort"`

	// End port (inclusive, optional - if not set, same as StartPort)
	EndPort int32 `json:"endPort,omitempty"`
}

// RuleExtensions provides Tobogganing-specific rule extensions
type RuleExtensions struct {
	// AuditMode logs violations but doesn't enforce
	AuditMode bool `json:"auditMode,omitempty"`

	// RequireEncryption requires encrypted connections
	RequireEncryption bool `json:"requireEncryption,omitempty"`

	// AllowedProtocols restricts application protocols
	AllowedProtocols []string `json:"allowedProtocols,omitempty"`

	// RateLimit configuration
	RateLimit *RateLimitConfig `json:"rateLimit,omitempty"`

	// Logging configuration
	Logging *LoggingConfig `json:"logging,omitempty"`

	// Custom tags for external systems
	Tags map[string]string `json:"tags,omitempty"`
}

// PolicyEvaluationResult represents the result of policy evaluation
type PolicyEvaluationResult struct {
	// Action to take (allow/deny/log)
	Action string `json:"action"`

	// Rule that matched (if any)
	MatchedRule *PolicyRule `json:"matchedRule,omitempty"`

	// Reason for the decision
	Reason string `json:"reason"`

	// Default policy applied (if no rules matched)
	DefaultPolicyApplied bool `json:"defaultPolicyApplied,omitempty"`

	// Audit mode (log but don't enforce)
	AuditMode bool `json:"auditMode,omitempty"`

	// Additional metadata
	Metadata map[string]interface{} `json:"metadata,omitempty"`

	// Processing time
	ProcessingTime time.Duration `json:"processingTime,omitempty"`
}

// FlowContext provides context for policy evaluation
type FlowContext struct {
	// Source information
	SrcIP        net.IP `json:"srcIP"`
	SrcPort      int32  `json:"srcPort"`
	SrcPodName   string `json:"srcPodName,omitempty"`
	SrcNamespace string `json:"srcNamespace,omitempty"`
	SrcLabels    map[string]string `json:"srcLabels,omitempty"`

	// Destination information
	DstIP        net.IP `json:"dstIP"`
	DstPort      int32  `json:"dstPort"`
	DstPodName   string `json:"dstPodName,omitempty"`
	DstNamespace string `json:"dstNamespace,omitempty"`
	DstLabels    map[string]string `json:"dstLabels,omitempty"`

	// Protocol and connection info
	Protocol  string `json:"protocol"`
	Direction string `json:"direction"`

	// Additional context
	ServiceAccount string            `json:"serviceAccount,omitempty"`
	ConnectionID   string            `json:"connectionID,omitempty"`
	Timestamp      time.Time         `json:"timestamp"`
	Metadata       map[string]interface{} `json:"metadata,omitempty"`
}

// PolicyEvent represents a policy-related event
type PolicyEvent struct {
	// Event type (violation, allow, deny, etc.)
	Type string `json:"type"`

	// Severity level
	Severity string `json:"severity"`

	// Timestamp
	Timestamp time.Time `json:"timestamp"`

	// Flow context
	FlowContext *FlowContext `json:"flowContext"`

	// Policy evaluation result
	EvaluationResult *PolicyEvaluationResult `json:"evaluationResult"`

	// Additional event data
	Message    string                 `json:"message,omitempty"`
	Metadata   map[string]interface{} `json:"metadata,omitempty"`
	Tags       []string               `json:"tags,omitempty"`
	Source     string                 `json:"source,omitempty"`
	Cluster    string                 `json:"cluster,omitempty"`
	Node       string                 `json:"node,omitempty"`
}

// PolicyStatistics provides statistics for policy evaluation
type PolicyStatistics struct {
	// Total evaluations performed
	TotalEvaluations uint64 `json:"totalEvaluations"`

	// Allow/deny/log counts
	AllowedCount uint64 `json:"allowedCount"`
	DeniedCount  uint64 `json:"deniedCount"`
	LoggedCount  uint64 `json:"loggedCount"`

	// Default policy applications
	DefaultAllowCount uint64 `json:"defaultAllowCount"`
	DefaultDenyCount  uint64 `json:"defaultDenyCount"`

	// Performance metrics
	AvgProcessingTime time.Duration `json:"avgProcessingTime"`
	MaxProcessingTime time.Duration `json:"maxProcessingTime"`
	MinProcessingTime time.Duration `json:"minProcessingTime"`

	// Error counts
	ErrorCount uint64 `json:"errorCount"`

	// Last update time
	LastUpdated time.Time `json:"lastUpdated"`

	// Per-rule statistics
	RuleStats map[uint32]*RuleStatistics `json:"ruleStats,omitempty"`
}

// RuleStatistics provides per-rule statistics
type RuleStatistics struct {
	RuleID        uint32        `json:"ruleID"`
	MatchCount    uint64        `json:"matchCount"`
	ByteCount     uint64        `json:"byteCount"`
	LastMatch     time.Time     `json:"lastMatch,omitempty"`
	AvgMatchTime  time.Duration `json:"avgMatchTime"`
	ErrorCount    uint64        `json:"errorCount"`
}

// PolicyConfiguration holds global policy configuration
type PolicyConfiguration struct {
	// Default policy for unmatched traffic
	DefaultPolicy string `json:"defaultPolicy"`

	// Enable audit mode globally
	GlobalAuditMode bool `json:"globalAuditMode"`

	// Enable metrics collection
	EnableMetrics bool `json:"enableMetrics"`

	// Enable violation logging
	EnableViolationLogging bool `json:"enableViolationLogging"`

	// Log level for policy engine
	LogLevel string `json:"logLevel"`

	// Performance settings
	MaxRulesPerPolicy int32 `json:"maxRulesPerPolicy"`
	CacheSize         int32 `json:"cacheSize"`
	CacheTTL          string `json:"cacheTTL"`

	// Rate limiting for policy evaluation
	EvaluationRateLimit int32 `json:"evaluationRateLimit"`

	// Integration settings
	ManagerIntegration *ManagerIntegrationConfig `json:"managerIntegration,omitempty"`
	EBPFIntegration    *EBPFIntegrationConfig    `json:"ebpfIntegration,omitempty"`
}

// ManagerIntegrationConfig defines Manager service integration
type ManagerIntegrationConfig struct {
	// Manager service URL
	URL string `json:"url"`

	// API key for authentication
	APIKey string `json:"apiKey"`

	// Sync interval for policy updates
	SyncInterval string `json:"syncInterval"`

	// Enable policy push from Manager
	EnablePolicySync bool `json:"enablePolicySync"`

	// Enable statistics reporting to Manager
	EnableStatsReporting bool `json:"enableStatsReporting"`
}

// EBPFIntegrationConfig defines eBPF integration settings
type EBPFIntegrationConfig struct {
	// Enable eBPF enforcement
	EnableEnforcement bool `json:"enableEnforcement"`

	// eBPF program paths
	ProgramPaths []string `json:"programPaths"`

	// Map update interval
	MapUpdateInterval string `json:"mapUpdateInterval"`

	// Statistics collection interval
	StatsInterval string `json:"statsInterval"`

	// Enable event processing
	EnableEventProcessing bool `json:"enableEventProcessing"`
}