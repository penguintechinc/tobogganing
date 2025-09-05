// Policy manager implements the core policy engine for network policy
// management and enforcement in the Tobogganing Kubernetes CNI.

package policy

import (
	"context"
	"fmt"
	"net"
	"sort"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/labels"
)

// Manager provides comprehensive network policy management
type Manager struct {
	logger *logrus.Entry
	config *PolicyConfiguration

	// Policy storage
	mu               sync.RWMutex
	networkPolicies  map[string]*NetworkPolicy           // key: namespace/name
	compiledRules    map[uint32]*PolicyRule              // key: rule ID
	rulesByPriority  []*PolicyRule                       // sorted by priority
	namespaceCache   map[string]*NamespaceInfo           // namespace metadata
	podCache         map[string]*PodInfo                 // pod metadata
	serviceCache     map[string]*ServiceInfo             // service metadata

	// Statistics and monitoring
	stats           *PolicyStatistics
	ruleIDCounter   uint32
	evaluationCache map[string]*PolicyEvaluationResult
	cacheExpiry     map[string]time.Time

	// Integration components
	ebpfManager     EBPFManager
	managerClient   ManagerClient
	eventEmitter    EventEmitter

	// Background tasks
	ctx     context.Context
	cancel  context.CancelFunc
	wg      sync.WaitGroup
}

// EBPFManager interface for eBPF integration
type EBPFManager interface {
	UpdateFirewallRule(rule *FirewallRule) error
	RemoveFirewallRule(ruleID uint32) error
	UpdatePodInfo(podIP net.IP, info *PodInfo) error
	RemovePodInfo(podIP net.IP) error
}

// ManagerClient interface for Manager service integration
type ManagerClient interface {
	SyncPolicies(ctx context.Context) ([]*NetworkPolicy, error)
	ReportStatistics(ctx context.Context, stats *PolicyStatistics) error
	GetPodInventory(ctx context.Context) ([]*PodInfo, error)
}

// EventEmitter interface for event processing
type EventEmitter interface {
	EmitPolicyEvent(event *PolicyEvent) error
	EmitViolationEvent(violation *PolicyViolationEvent) error
}

// PodInfo represents cached pod information
type PodInfo struct {
	Name          string
	Namespace     string
	IP            net.IP
	Labels        map[string]string
	ServiceAccount string
	NodeName      string
	CreatedAt     time.Time
	LastSeen      time.Time
}

// NamespaceInfo represents cached namespace information
type NamespaceInfo struct {
	Name      string
	Labels    map[string]string
	CreatedAt time.Time
	LastSeen  time.Time
}

// ServiceInfo represents cached service information
type ServiceInfo struct {
	Name        string
	Namespace   string
	Labels      map[string]string
	Ports       []ServicePort
	ClusterIP   net.IP
	ExternalIPs []net.IP
	Type        string
	CreatedAt   time.Time
}

// ServicePort represents a service port
type ServicePort struct {
	Name       string
	Protocol   string
	Port       int32
	TargetPort int32
}

// FirewallRule represents an eBPF firewall rule
type FirewallRule struct {
	RuleID        uint32
	Priority      uint32
	SrcNamespace  uint32
	DstNamespace  uint32
	SrcIP         net.IP
	SrcMask       net.IPMask
	DstIP         net.IP
	DstMask       net.IPMask
	SrcPortStart  uint16
	SrcPortEnd    uint16
	DstPortStart  uint16
	DstPortEnd    uint16
	Protocol      uint8
	Direction     uint8
	Action        uint8
	Enabled       bool
	CreatedTime   uint64
}

// PolicyViolationEvent represents a policy violation
type PolicyViolationEvent struct {
	Timestamp     time.Time
	SrcIP         net.IP
	DstIP         net.IP
	SrcPort       uint16
	DstPort       uint16
	Protocol      uint8
	Direction     uint8
	RuleID        uint32
	SrcNamespace  string
	DstNamespace  string
	Action        string
	Message       string
	FlowContext   *FlowContext
}

// NewManager creates a new policy manager
func NewManager(config *PolicyConfiguration, ebpfMgr EBPFManager, managerClient ManagerClient, eventEmitter EventEmitter) (*Manager, error) {
	if config == nil {
		config = &PolicyConfiguration{
			DefaultPolicy:           DefaultPolicyDeny,
			GlobalAuditMode:         false,
			EnableMetrics:           true,
			EnableViolationLogging:  true,
			LogLevel:                "info",
			MaxRulesPerPolicy:       1000,
			CacheSize:               10000,
			CacheTTL:                "5m",
			EvaluationRateLimit:     10000,
		}
	}

	logger := logrus.WithField("component", "policy-manager")
	
	// Set log level
	if level, err := logrus.ParseLevel(config.LogLevel); err == nil {
		logger.Logger.SetLevel(level)
	}

	ctx, cancel := context.WithCancel(context.Background())

	manager := &Manager{
		logger:          logger,
		config:          config,
		ctx:             ctx,
		cancel:          cancel,
		networkPolicies: make(map[string]*NetworkPolicy),
		compiledRules:   make(map[uint32]*PolicyRule),
		rulesByPriority: make([]*PolicyRule, 0),
		namespaceCache:  make(map[string]*NamespaceInfo),
		podCache:        make(map[string]*PodInfo),
		serviceCache:    make(map[string]*ServiceInfo),
		evaluationCache: make(map[string]*PolicyEvaluationResult),
		cacheExpiry:     make(map[string]time.Time),
		ebpfManager:     ebpfMgr,
		managerClient:   managerClient,
		eventEmitter:    eventEmitter,
		stats: &PolicyStatistics{
			RuleStats: make(map[uint32]*RuleStatistics),
		},
	}

	return manager, nil
}

// Start initializes the policy manager and starts background tasks
func (pm *Manager) Start() error {
	pm.logger.Info("starting policy manager")

	// Initialize statistics
	pm.stats.LastUpdated = time.Now()
	pm.stats.MinProcessingTime = time.Hour // Set high initial value

	// Load initial policies if Manager integration is enabled
	if pm.config.ManagerIntegration != nil && pm.config.ManagerIntegration.EnablePolicySync {
		if err := pm.syncPoliciesFromManager(); err != nil {
			pm.logger.WithError(err).Warn("failed to sync initial policies from Manager")
		}
	}

	// Start background tasks
	pm.startBackgroundTasks()

	pm.logger.Info("policy manager started successfully")
	return nil
}

// AddNetworkPolicy adds or updates a network policy
func (pm *Manager) AddNetworkPolicy(policy *NetworkPolicy) error {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	key := pm.getPolicyKey(policy)
	
	pm.logger.WithFields(logrus.Fields{
		"policy":    policy.Name,
		"namespace": policy.Namespace,
		"key":       key,
	}).Info("adding network policy")

	// Validate policy
	if err := pm.validateNetworkPolicy(policy); err != nil {
		return fmt.Errorf("policy validation failed: %w", err)
	}

	// Store policy
	pm.networkPolicies[key] = policy

	// Compile policy rules
	if err := pm.compileNetworkPolicy(policy); err != nil {
		delete(pm.networkPolicies, key)
		return fmt.Errorf("failed to compile policy: %w", err)
	}

	// Update policy status
	pm.updatePolicyStatus(policy, PolicyConditionReady, "Policy compiled and ready")

	// Rebuild rule priorities
	pm.rebuildRulePriorities()

	// Sync with eBPF
	if pm.ebpfManager != nil {
		if err := pm.syncRulesToEBPF(); err != nil {
			pm.logger.WithError(err).Warn("failed to sync rules to eBPF")
		}
	}

	pm.logger.WithField("policy", policy.Name).Info("network policy added successfully")
	return nil
}

// RemoveNetworkPolicy removes a network policy
func (pm *Manager) RemoveNetworkPolicy(namespace, name string) error {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	key := fmt.Sprintf("%s/%s", namespace, name)
	
	policy, exists := pm.networkPolicies[key]
	if !exists {
		return fmt.Errorf("policy not found: %s", key)
	}

	pm.logger.WithFields(logrus.Fields{
		"policy":    name,
		"namespace": namespace,
	}).Info("removing network policy")

	// Remove compiled rules
	pm.removeCompiledRules(policy)

	// Remove policy
	delete(pm.networkPolicies, key)

	// Rebuild rule priorities
	pm.rebuildRulePriorities()

	// Sync with eBPF
	if pm.ebpfManager != nil {
		if err := pm.syncRulesToEBPF(); err != nil {
			pm.logger.WithError(err).Warn("failed to sync rules to eBPF")
		}
	}

	pm.logger.WithField("policy", name).Info("network policy removed successfully")
	return nil
}

// EvaluateFlow evaluates a network flow against all policies
func (pm *Manager) EvaluateFlow(flowCtx *FlowContext) (*PolicyEvaluationResult, error) {
	startTime := time.Now()
	
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	// Check evaluation cache first
	cacheKey := pm.buildCacheKey(flowCtx)
	if result, exists := pm.evaluationCache[cacheKey]; exists {
		if expiry, ok := pm.cacheExpiry[cacheKey]; ok && time.Now().Before(expiry) {
			pm.updateStatistics(result, time.Since(startTime))
			return result, nil
		}
		// Cache expired, remove entries
		delete(pm.evaluationCache, cacheKey)
		delete(pm.cacheExpiry, cacheKey)
	}

	pm.logger.WithFields(logrus.Fields{
		"src_ip":   flowCtx.SrcIP,
		"dst_ip":   flowCtx.DstIP,
		"protocol": flowCtx.Protocol,
		"direction": flowCtx.Direction,
	}).Debug("evaluating flow")

	// Evaluate rules in priority order
	result := &PolicyEvaluationResult{
		Action:         ActionDeny,
		Reason:         "no matching policy",
		ProcessingTime: 0,
		Metadata:       make(map[string]interface{}),
	}

	// Check each rule
	for _, rule := range pm.rulesByPriority {
		if !rule.Enabled {
			continue
		}

		if pm.ruleMatches(rule, flowCtx) {
			result.Action = rule.Action
			result.MatchedRule = rule
			result.Reason = fmt.Sprintf("matched rule: %s", rule.Name)
			result.DefaultPolicyApplied = false
			
			// Check audit mode
			if rule.Extensions != nil && rule.Extensions.AuditMode {
				result.AuditMode = true
			}

			// Update rule statistics
			pm.updateRuleStatistics(rule.ID)

			pm.logger.WithFields(logrus.Fields{
				"rule_id":    rule.ID,
				"rule_name":  rule.Name,
				"action":     result.Action,
				"audit_mode": result.AuditMode,
			}).Debug("rule matched")

			break
		}
	}

	// Apply default policy if no rules matched
	if result.MatchedRule == nil {
		result.Action = pm.config.DefaultPolicy
		result.DefaultPolicyApplied = true
		result.Reason = fmt.Sprintf("default policy: %s", pm.config.DefaultPolicy)

		if result.Action == ActionAllow {
			pm.stats.DefaultAllowCount++
		} else {
			pm.stats.DefaultDenyCount++
		}
	}

	// Apply global audit mode
	if pm.config.GlobalAuditMode {
		result.AuditMode = true
	}

	result.ProcessingTime = time.Since(startTime)

	// Cache the result
	pm.cacheResult(cacheKey, result)

	// Update statistics
	pm.updateStatistics(result, result.ProcessingTime)

	// Emit policy event if needed
	if pm.eventEmitter != nil {
		event := &PolicyEvent{
			Type:             "evaluation",
			Severity:         "info",
			Timestamp:        time.Now(),
			FlowContext:      flowCtx,
			EvaluationResult: result,
			Message:          fmt.Sprintf("Flow evaluated: %s", result.Action),
		}

		if result.Action == ActionDeny && !result.AuditMode {
			event.Type = "violation"
			event.Severity = "warning"
		}

		if err := pm.eventEmitter.EmitPolicyEvent(event); err != nil {
			pm.logger.WithError(err).Warn("failed to emit policy event")
		}
	}

	return result, nil
}

// UpdatePodInfo updates cached pod information
func (pm *Manager) UpdatePodInfo(podInfo *PodInfo) error {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	key := fmt.Sprintf("%s/%s", podInfo.Namespace, podInfo.Name)
	pm.podCache[key] = podInfo

	// Update eBPF maps
	if pm.ebpfManager != nil {
		ebpfPodInfo := &PodInfo{
			Name:      podInfo.Name,
			Namespace: podInfo.Namespace,
			IP:        podInfo.IP,
			Labels:    podInfo.Labels,
		}
		
		if err := pm.ebpfManager.UpdatePodInfo(podInfo.IP, ebpfPodInfo); err != nil {
			return fmt.Errorf("failed to update eBPF pod info: %w", err)
		}
	}

	pm.logger.WithFields(logrus.Fields{
		"pod":       podInfo.Name,
		"namespace": podInfo.Namespace,
		"ip":        podInfo.IP,
	}).Debug("updated pod info")

	return nil
}

// RemovePodInfo removes cached pod information
func (pm *Manager) RemovePodInfo(namespace, name string) error {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	key := fmt.Sprintf("%s/%s", namespace, name)
	
	if podInfo, exists := pm.podCache[key]; exists {
		// Remove from eBPF maps
		if pm.ebpfManager != nil {
			if err := pm.ebpfManager.RemovePodInfo(podInfo.IP); err != nil {
				pm.logger.WithError(err).Warn("failed to remove pod from eBPF")
			}
		}
		
		delete(pm.podCache, key)
		
		pm.logger.WithFields(logrus.Fields{
			"pod":       name,
			"namespace": namespace,
		}).Debug("removed pod info")
	}

	return nil
}

// GetStatistics returns current policy statistics
func (pm *Manager) GetStatistics() *PolicyStatistics {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	// Create a copy to avoid race conditions
	stats := &PolicyStatistics{
		TotalEvaluations:    pm.stats.TotalEvaluations,
		AllowedCount:        pm.stats.AllowedCount,
		DeniedCount:         pm.stats.DeniedCount,
		LoggedCount:         pm.stats.LoggedCount,
		DefaultAllowCount:   pm.stats.DefaultAllowCount,
		DefaultDenyCount:    pm.stats.DefaultDenyCount,
		AvgProcessingTime:   pm.stats.AvgProcessingTime,
		MaxProcessingTime:   pm.stats.MaxProcessingTime,
		MinProcessingTime:   pm.stats.MinProcessingTime,
		ErrorCount:          pm.stats.ErrorCount,
		LastUpdated:         time.Now(),
		RuleStats:           make(map[uint32]*RuleStatistics),
	}

	// Copy rule statistics
	for ruleID, ruleStat := range pm.stats.RuleStats {
		stats.RuleStats[ruleID] = &RuleStatistics{
			RuleID:       ruleStat.RuleID,
			MatchCount:   ruleStat.MatchCount,
			ByteCount:    ruleStat.ByteCount,
			LastMatch:    ruleStat.LastMatch,
			AvgMatchTime: ruleStat.AvgMatchTime,
			ErrorCount:   ruleStat.ErrorCount,
		}
	}

	return stats
}

// GetPolicies returns all network policies
func (pm *Manager) GetPolicies() []*NetworkPolicy {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	policies := make([]*NetworkPolicy, 0, len(pm.networkPolicies))
	for _, policy := range pm.networkPolicies {
		policies = append(policies, policy)
	}

	return policies
}

// GetCompiledRules returns all compiled policy rules
func (pm *Manager) GetCompiledRules() []*PolicyRule {
	pm.mu.RLock()
	defer pm.mu.RUnlock()

	rules := make([]*PolicyRule, len(pm.rulesByPriority))
	copy(rules, pm.rulesByPriority)
	return rules
}

// Close shuts down the policy manager
func (pm *Manager) Close() error {
	pm.logger.Info("shutting down policy manager")
	
	pm.cancel()
	pm.wg.Wait()

	pm.logger.Info("policy manager shutdown complete")
	return nil
}

// Helper methods

func (pm *Manager) getPolicyKey(policy *NetworkPolicy) string {
	return fmt.Sprintf("%s/%s", policy.Namespace, policy.Name)
}

func (pm *Manager) validateNetworkPolicy(policy *NetworkPolicy) error {
	if policy.Name == "" {
		return fmt.Errorf("policy name cannot be empty")
	}
	
	if policy.Namespace == "" {
		return fmt.Errorf("policy namespace cannot be empty")
	}

	// Validate selectors
	if _, err := metav1.LabelSelectorAsSelector(&policy.Spec.PodSelector); err != nil {
		return fmt.Errorf("invalid pod selector: %w", err)
	}

	return nil
}

func (pm *Manager) compileNetworkPolicy(policy *NetworkPolicy) error {
	// Remove existing rules for this policy
	pm.removeCompiledRules(policy)

	policyKey := pm.getPolicyKey(policy)

	// Compile ingress rules
	for i, ingressRule := range policy.Spec.Ingress {
		rule := &PolicyRule{
			ID:              pm.getNextRuleID(),
			Name:            fmt.Sprintf("%s-ingress-%d", policyKey, i),
			Priority:        policy.Spec.Priority,
			PolicyName:      policy.Name,
			PolicyNamespace: policy.Namespace,
			Direction:       DirectionIngress,
			Action:          ActionAllow,
			Enabled:         true,
			CreatedAt:       time.Now(),
			UpdatedAt:       time.Now(),
		}

		// Compile destination selector (pod selector from policy)
		rule.DstSelector = pm.compilePodSelector(policy.Namespace, &policy.Spec.PodSelector)

		// Compile ports
		rule.Ports = pm.compileNetworkPolicyPorts(ingressRule.Ports)

		// Compile source selectors
		if len(ingressRule.From) == 0 {
			// Allow from anywhere if no From specified
			rule.SrcSelector = &PodSelector{}
		} else {
			// For now, use the first From selector (simplified)
			if len(ingressRule.From) > 0 {
				rule.SrcSelector = pm.compileNetworkPolicyPeer(policy.Namespace, &ingressRule.From[0])
			}
		}

		pm.compiledRules[rule.ID] = rule
	}

	// Compile egress rules
	for i, egressRule := range policy.Spec.Egress {
		rule := &PolicyRule{
			ID:              pm.getNextRuleID(),
			Name:            fmt.Sprintf("%s-egress-%d", policyKey, i),
			Priority:        policy.Spec.Priority,
			PolicyName:      policy.Name,
			PolicyNamespace: policy.Namespace,
			Direction:       DirectionEgress,
			Action:          ActionAllow,
			Enabled:         true,
			CreatedAt:       time.Now(),
			UpdatedAt:       time.Now(),
		}

		// Compile source selector (pod selector from policy)
		rule.SrcSelector = pm.compilePodSelector(policy.Namespace, &policy.Spec.PodSelector)

		// Compile ports
		rule.Ports = pm.compileNetworkPolicyPorts(egressRule.Ports)

		// Compile destination selectors
		if len(egressRule.To) == 0 {
			// Allow to anywhere if no To specified
			rule.DstSelector = &PodSelector{}
		} else {
			// For now, use the first To selector (simplified)
			if len(egressRule.To) > 0 {
				rule.DstSelector = pm.compileNetworkPolicyPeer(policy.Namespace, &egressRule.To[0])
			}
		}

		pm.compiledRules[rule.ID] = rule
	}

	return nil
}

func (pm *Manager) removeCompiledRules(policy *NetworkPolicy) {
	policyKey := pm.getPolicyKey(policy)
	
	// Find rules belonging to this policy
	rulesToRemove := make([]uint32, 0)
	for ruleID, rule := range pm.compiledRules {
		if rule.PolicyName == policy.Name && rule.PolicyNamespace == policy.Namespace {
			rulesToRemove = append(rulesToRemove, ruleID)
		}
	}

	// Remove the rules
	for _, ruleID := range rulesToRemove {
		delete(pm.compiledRules, ruleID)
		
		// Remove from eBPF
		if pm.ebpfManager != nil {
			if err := pm.ebpfManager.RemoveFirewallRule(ruleID); err != nil {
				pm.logger.WithError(err).WithField("rule_id", ruleID).Warn("failed to remove rule from eBPF")
			}
		}
		
		// Remove from statistics
		delete(pm.stats.RuleStats, ruleID)
	}

	pm.logger.WithField("policy", policyKey).Debug("removed compiled rules")
}

func (pm *Manager) rebuildRulePriorities() {
	// Convert map to slice
	rules := make([]*PolicyRule, 0, len(pm.compiledRules))
	for _, rule := range pm.compiledRules {
		rules = append(rules, rule)
	}

	// Sort by priority (lower number = higher priority)
	sort.Slice(rules, func(i, j int) bool {
		return rules[i].Priority < rules[j].Priority
	})

	pm.rulesByPriority = rules

	pm.logger.WithField("rule_count", len(rules)).Debug("rebuilt rule priorities")
}

func (pm *Manager) syncRulesToEBPF() error {
	if pm.ebpfManager == nil {
		return nil
	}

	for _, rule := range pm.compiledRules {
		firewallRule := pm.convertToFirewallRule(rule)
		if err := pm.ebpfManager.UpdateFirewallRule(firewallRule); err != nil {
			return fmt.Errorf("failed to update eBPF rule %d: %w", rule.ID, err)
		}
	}

	pm.logger.WithField("rule_count", len(pm.compiledRules)).Debug("synced rules to eBPF")
	return nil
}

func (pm *Manager) ruleMatches(rule *PolicyRule, flowCtx *FlowContext) bool {
	// Check direction
	if rule.Direction != DirectionBoth && rule.Direction != flowCtx.Direction {
		return false
	}

	// Check source selector
	if rule.SrcSelector != nil && !pm.selectorMatches(rule.SrcSelector, flowCtx.SrcIP, flowCtx.SrcNamespace, flowCtx.SrcLabels) {
		return false
	}

	// Check destination selector
	if rule.DstSelector != nil && !pm.selectorMatches(rule.DstSelector, flowCtx.DstIP, flowCtx.DstNamespace, flowCtx.DstLabels) {
		return false
	}

	// Check ports
	if len(rule.Ports) > 0 && !pm.portMatches(rule.Ports, flowCtx.Protocol, flowCtx.DstPort) {
		return false
	}

	return true
}

func (pm *Manager) selectorMatches(selector *PodSelector, ip net.IP, namespace string, podLabels map[string]string) bool {
	// Check namespace
	if selector.Namespace != "" && selector.Namespace != namespace {
		return false
	}

	// Check IP blocks
	if len(selector.IPBlocks) > 0 {
		matched := false
		for _, ipBlock := range selector.IPBlocks {
			if pm.ipInBlock(ip, &ipBlock) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}

	// Check label selector
	if len(selector.LabelSelector) > 0 {
		for key, value := range selector.LabelSelector {
			if podLabels[key] != value {
				return false
			}
		}
	}

	return true
}

func (pm *Manager) portMatches(ports []PortRange, protocol string, port int32) bool {
	for _, portRange := range ports {
		if portRange.Protocol != "" && portRange.Protocol != protocol {
			continue
		}

		if port >= portRange.StartPort && (portRange.EndPort == 0 || port <= portRange.EndPort) {
			return true
		}
	}
	return false
}

func (pm *Manager) ipInBlock(ip net.IP, ipBlock *IPBlock) bool {
	_, cidr, err := net.ParseCIDR(ipBlock.CIDR)
	if err != nil {
		return false
	}

	if !cidr.Contains(ip) {
		return false
	}

	// Check exceptions
	for _, except := range ipBlock.Except {
		_, exceptCIDR, err := net.ParseCIDR(except)
		if err != nil {
			continue
		}
		if exceptCIDR.Contains(ip) {
			return false
		}
	}

	return true
}

func (pm *Manager) getNextRuleID() uint32 {
	pm.ruleIDCounter++
	return pm.ruleIDCounter
}

func (pm *Manager) buildCacheKey(flowCtx *FlowContext) string {
	return fmt.Sprintf("%s:%d->%s:%d/%s/%s",
		flowCtx.SrcIP, flowCtx.SrcPort,
		flowCtx.DstIP, flowCtx.DstPort,
		flowCtx.Protocol, flowCtx.Direction)
}

func (pm *Manager) cacheResult(key string, result *PolicyEvaluationResult) {
	if pm.config.CacheSize > 0 && len(pm.evaluationCache) < int(pm.config.CacheSize) {
		pm.evaluationCache[key] = result
		
		// Parse cache TTL
		if ttl, err := time.ParseDuration(pm.config.CacheTTL); err == nil {
			pm.cacheExpiry[key] = time.Now().Add(ttl)
		} else {
			pm.cacheExpiry[key] = time.Now().Add(5 * time.Minute) // Default TTL
		}
	}
}

func (pm *Manager) updateStatistics(result *PolicyEvaluationResult, processingTime time.Duration) {
	pm.stats.TotalEvaluations++

	switch result.Action {
	case ActionAllow:
		pm.stats.AllowedCount++
	case ActionDeny:
		pm.stats.DeniedCount++
	case ActionLog:
		pm.stats.LoggedCount++
	}

	// Update processing time statistics
	if processingTime < pm.stats.MinProcessingTime {
		pm.stats.MinProcessingTime = processingTime
	}
	if processingTime > pm.stats.MaxProcessingTime {
		pm.stats.MaxProcessingTime = processingTime
	}

	// Update average processing time (simple moving average)
	if pm.stats.TotalEvaluations == 1 {
		pm.stats.AvgProcessingTime = processingTime
	} else {
		pm.stats.AvgProcessingTime = (pm.stats.AvgProcessingTime*time.Duration(pm.stats.TotalEvaluations-1) + processingTime) / time.Duration(pm.stats.TotalEvaluations)
	}
}

func (pm *Manager) updateRuleStatistics(ruleID uint32) {
	if pm.stats.RuleStats[ruleID] == nil {
		pm.stats.RuleStats[ruleID] = &RuleStatistics{
			RuleID: ruleID,
		}
	}
	
	stats := pm.stats.RuleStats[ruleID]
	stats.MatchCount++
	stats.LastMatch = time.Now()
}

func (pm *Manager) updatePolicyStatus(policy *NetworkPolicy, conditionType NetworkPolicyConditionType, message string) {
	condition := NetworkPolicyCondition{
		Type:               conditionType,
		Status:             "True",
		LastTransitionTime: metav1.Now(),
		Message:            message,
	}

	// Update or add condition
	found := false
	for i, existingCondition := range policy.Status.Conditions {
		if existingCondition.Type == conditionType {
			policy.Status.Conditions[i] = condition
			found = true
			break
		}
	}

	if !found {
		policy.Status.Conditions = append(policy.Status.Conditions, condition)
	}

	policy.Status.LastUpdated = metav1.Now()
}

// Helper methods for policy compilation
func (pm *Manager) compilePodSelector(namespace string, selector *metav1.LabelSelector) *PodSelector {
	return &PodSelector{
		Namespace:     namespace,
		LabelSelector: selector.MatchLabels,
	}
}

func (pm *Manager) compileNetworkPolicyPorts(ports []NetworkPolicyPort) []PortRange {
	var portRanges []PortRange
	
	for _, port := range ports {
		portRange := PortRange{}
		
		if port.Protocol != nil {
			portRange.Protocol = *port.Protocol
		}
		
		if port.Port != nil {
			startPort := port.Port.IntVal
			if startPort == 0 && port.Port.StrVal != "" {
				// Handle named ports (simplified - would need service lookup)
				startPort = 80 // Default
			}
			portRange.StartPort = startPort
			
			if port.EndPort != nil {
				portRange.EndPort = *port.EndPort
			} else {
				portRange.EndPort = startPort
			}
		}
		
		portRanges = append(portRanges, portRange)
	}
	
	return portRanges
}

func (pm *Manager) compileNetworkPolicyPeer(namespace string, peer *NetworkPolicyPeer) *PodSelector {
	selector := &PodSelector{}

	if peer.PodSelector != nil {
		selector.Namespace = namespace
		selector.LabelSelector = peer.PodSelector.MatchLabels
	}

	if peer.NamespaceSelector != nil {
		// For namespace selector, we'd need to resolve namespace labels
		// Simplified for now
		selector.Namespace = ""
	}

	if peer.IPBlock != nil {
		selector.IPBlocks = []IPBlock{*peer.IPBlock}
	}

	return selector
}

func (pm *Manager) convertToFirewallRule(rule *PolicyRule) *FirewallRule {
	firewallRule := &FirewallRule{
		RuleID:      rule.ID,
		Priority:    uint32(rule.Priority),
		Enabled:     rule.Enabled,
		CreatedTime: uint64(rule.CreatedAt.UnixNano()),
	}

	// Convert action
	switch rule.Action {
	case ActionAllow:
		firewallRule.Action = 1
	case ActionDeny:
		firewallRule.Action = 0
	case ActionLog:
		firewallRule.Action = 2
	}

	// Convert direction
	switch rule.Direction {
	case DirectionIngress:
		firewallRule.Direction = 0
	case DirectionEgress:
		firewallRule.Direction = 1
	case DirectionBoth:
		firewallRule.Direction = 2
	}

	// Convert ports (simplified - use first port range)
	if len(rule.Ports) > 0 {
		portRange := rule.Ports[0]
		firewallRule.DstPortStart = uint16(portRange.StartPort)
		if portRange.EndPort > 0 {
			firewallRule.DstPortEnd = uint16(portRange.EndPort)
		} else {
			firewallRule.DstPortEnd = uint16(portRange.StartPort)
		}

		// Convert protocol
		switch portRange.Protocol {
		case "TCP":
			firewallRule.Protocol = 6
		case "UDP":
			firewallRule.Protocol = 17
		case "ICMP":
			firewallRule.Protocol = 1
		default:
			firewallRule.Protocol = 0 // Any
		}
	}

	return firewallRule
}

// Background task methods
func (pm *Manager) startBackgroundTasks() {
	// Start policy sync task
	if pm.config.ManagerIntegration != nil && pm.config.ManagerIntegration.EnablePolicySync {
		pm.wg.Add(1)
		go pm.policySync()
	}

	// Start statistics reporting task
	if pm.config.ManagerIntegration != nil && pm.config.ManagerIntegration.EnableStatsReporting {
		pm.wg.Add(1)
		go pm.statsReporting()
	}

	// Start cache cleanup task
	pm.wg.Add(1)
	go pm.cacheCleanup()
}

func (pm *Manager) policySync() {
	defer pm.wg.Done()

	interval := 5 * time.Minute
	if pm.config.ManagerIntegration.SyncInterval != "" {
		if d, err := time.ParseDuration(pm.config.ManagerIntegration.SyncInterval); err == nil {
			interval = d
		}
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-pm.ctx.Done():
			return
		case <-ticker.C:
			if err := pm.syncPoliciesFromManager(); err != nil {
				pm.logger.WithError(err).Error("failed to sync policies from Manager")
			}
		}
	}
}

func (pm *Manager) statsReporting() {
	defer pm.wg.Done()

	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-pm.ctx.Done():
			return
		case <-ticker.C:
			if pm.managerClient != nil {
				stats := pm.GetStatistics()
				if err := pm.managerClient.ReportStatistics(pm.ctx, stats); err != nil {
					pm.logger.WithError(err).Error("failed to report statistics to Manager")
				}
			}
		}
	}
}

func (pm *Manager) cacheCleanup() {
	defer pm.wg.Done()

	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-pm.ctx.Done():
			return
		case <-ticker.C:
			pm.cleanupExpiredCacheEntries()
		}
	}
}

func (pm *Manager) syncPoliciesFromManager() error {
	if pm.managerClient == nil {
		return fmt.Errorf("manager client not configured")
	}

	policies, err := pm.managerClient.SyncPolicies(pm.ctx)
	if err != nil {
		return fmt.Errorf("failed to sync policies: %w", err)
	}

	pm.logger.WithField("policy_count", len(policies)).Info("synced policies from Manager")

	for _, policy := range policies {
		if err := pm.AddNetworkPolicy(policy); err != nil {
			pm.logger.WithError(err).WithField("policy", policy.Name).Error("failed to add synced policy")
		}
	}

	return nil
}

func (pm *Manager) cleanupExpiredCacheEntries() {
	pm.mu.Lock()
	defer pm.mu.Unlock()

	now := time.Now()
	expiredKeys := make([]string, 0)

	for key, expiry := range pm.cacheExpiry {
		if now.After(expiry) {
			expiredKeys = append(expiredKeys, key)
		}
	}

	for _, key := range expiredKeys {
		delete(pm.evaluationCache, key)
		delete(pm.cacheExpiry, key)
	}

	if len(expiredKeys) > 0 {
		pm.logger.WithField("expired_entries", len(expiredKeys)).Debug("cleaned up expired cache entries")
	}
}