// Package firewall implements a comprehensive firewall system for the SASEWaddle headend proxy.
//
// The firewall manager provides:
// - Domain-based access control with wildcard support (*.example.com)
// - IPv4 and IPv6 address filtering with CIDR support
// - Protocol-level filtering (TCP, UDP, ICMP, etc.)
// - Source and destination port range filtering
// - Directional traffic control (inbound, outbound, bidirectional)
// - Priority-based rule processing and conflict resolution
// - Real-time rule updates from the Manager service
// - Redis caching with randomized refresh intervals to prevent thundering herd
//
// The firewall integrates with the proxy's request processing pipeline to
// enforce access controls before traffic is forwarded to destinations.
package firewall

import (
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	log "github.com/sirupsen/logrus"
)

type RuleType string

const (
	RuleTypeDomain      RuleType = "domain"
	RuleTypeIP          RuleType = "ip"
	RuleTypeIPRange     RuleType = "ip_range"
	RuleTypeURLPattern  RuleType = "url_pattern"
	RuleTypeProtocolRule RuleType = "protocol_rule"
)

type AccessType string

const (
	AccessTypeAllow AccessType = "allow"
	AccessTypeDeny  AccessType = "deny"
)

type FirewallRule struct {
	Pattern     string                 `json:"pattern"`
	Priority    int                    `json:"priority"`
	Description string                 `json:"description"`
	SrcIP       string                 `json:"src_ip,omitempty"`
	DstIP       string                 `json:"dst_ip,omitempty"`
	Protocol    string                 `json:"protocol,omitempty"`
	SrcPort     string                 `json:"src_port,omitempty"`
	DstPort     string                 `json:"dst_port,omitempty"`
	Direction   string                 `json:"direction,omitempty"`
}

type UserRules struct {
	UserID    string `json:"user_id"`
	Timestamp string `json:"timestamp"`
	Rules     struct {
		AllowDomains       []FirewallRule `json:"allow_domains"`
		DenyDomains        []FirewallRule `json:"deny_domains"`
		AllowIPs           []FirewallRule `json:"allow_ips"`
		DenyIPs            []FirewallRule `json:"deny_ips"`
		AllowIPRanges      []FirewallRule `json:"allow_ip_ranges"`
		DenyIPRanges       []FirewallRule `json:"deny_ip_ranges"`
		AllowURLPatterns   []FirewallRule `json:"allow_url_patterns"`
		DenyURLPatterns    []FirewallRule `json:"deny_url_patterns"`
		AllowProtocolRules []FirewallRule `json:"allow_protocol_rules"`
		DenyProtocolRules  []FirewallRule `json:"deny_protocol_rules"`
	} `json:"rules"`
}

type AllRulesResponse struct {
	Timestamp  string               `json:"timestamp"`
	RulesCount int                  `json:"rules_count"`
	UserRules  map[string]UserRules `json:"user_rules"`
}

type Manager struct {
	managerURL    string
	authToken     string
	userRules     map[string]*UserRules
	lastUpdate    time.Time
	updateMutex   sync.RWMutex
	refreshTicker *time.Ticker
	stopChan      chan bool
}

func NewManager(managerURL, authToken string) *Manager {
	return &Manager{
		managerURL:  managerURL,
		authToken:   authToken,
		userRules:   make(map[string]*UserRules),
		stopChan:    make(chan bool),
	}
}

func (m *Manager) Start() error {
	log.Info("Starting firewall manager")
	
	// Initial fetch
	if err := m.fetchRules(); err != nil {
		log.Errorf("Failed to fetch initial rules: %v", err)
		return err
	}
	
	// Start periodic refresh with randomized interval (30-90 seconds)
	// This prevents thundering herd when multiple headends start simultaneously
	refreshInterval := time.Duration(30+rand.Intn(61)) * time.Second
	log.Infof("Setting randomized refresh interval to %v", refreshInterval)
	
	m.refreshTicker = time.NewTicker(refreshInterval)
	go m.refreshLoop()
	
	log.Info("Firewall manager started successfully")
	return nil
}

func (m *Manager) Stop() {
	log.Info("Stopping firewall manager")
	
	if m.refreshTicker != nil {
		m.refreshTicker.Stop()
	}
	
	close(m.stopChan)
}

func (m *Manager) refreshLoop() {
	for {
		select {
		case <-m.refreshTicker.C:
			if err := m.fetchRules(); err != nil {
				log.Errorf("Failed to refresh rules: %v", err)
			} else {
				// Randomize next refresh interval to prevent synchronization
				nextInterval := time.Duration(30+rand.Intn(61)) * time.Second
				m.refreshTicker.Reset(nextInterval)
				log.Debugf("Next refresh scheduled in %v", nextInterval)
			}
		case <-m.stopChan:
			return
		}
	}
}

func (m *Manager) fetchRules() error {
	client := &http.Client{
		Timeout: 10 * time.Second,
	}
	
	req, err := http.NewRequest("GET", m.managerURL+"/api/v1/firewall/rules", nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	
	req.Header.Set("Authorization", "Bearer "+m.authToken)
	req.Header.Set("User-Agent", "SASEWaddle-Headend/1.0")
	
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to fetch rules: %w", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to fetch rules: status %d, body: %s", resp.StatusCode, string(body))
	}
	
	var rulesResponse AllRulesResponse
	if err := json.NewDecoder(resp.Body).Decode(&rulesResponse); err != nil {
		return fmt.Errorf("failed to decode rules response: %w", err)
	}
	
	// Update local cache
	m.updateMutex.Lock()
	m.userRules = make(map[string]*UserRules)
	for userID, rules := range rulesResponse.UserRules {
		userRulesCopy := rules
		m.userRules[userID] = &userRulesCopy
	}
	m.lastUpdate = time.Now()
	m.updateMutex.Unlock()
	
	log.Infof("Updated firewall rules for %d users", len(rulesResponse.UserRules))
	return nil
}

func (m *Manager) CheckAccess(userID, target string) bool {
	m.updateMutex.RLock()
	defer m.updateMutex.RUnlock()
	
	rules, exists := m.userRules[userID]
	if !exists {
		log.Warnf("No firewall rules found for user %s, denying access", userID)
		return false
	}
	
	// Collect all rules with priorities
	type priorityRule struct {
		rule       FirewallRule
		ruleType   RuleType
		accessType AccessType
	}
	
	var allRules []priorityRule
	
	// Add all rule types to a single list for priority-based processing
	for _, rule := range rules.Rules.DenyDomains {
		allRules = append(allRules, priorityRule{rule, RuleTypeDomain, AccessTypeDeny})
	}
	for _, rule := range rules.Rules.AllowDomains {
		allRules = append(allRules, priorityRule{rule, RuleTypeDomain, AccessTypeAllow})
	}
	for _, rule := range rules.Rules.DenyIPs {
		allRules = append(allRules, priorityRule{rule, RuleTypeIP, AccessTypeDeny})
	}
	for _, rule := range rules.Rules.AllowIPs {
		allRules = append(allRules, priorityRule{rule, RuleTypeIP, AccessTypeAllow})
	}
	for _, rule := range rules.Rules.DenyIPRanges {
		allRules = append(allRules, priorityRule{rule, RuleTypeIPRange, AccessTypeDeny})
	}
	for _, rule := range rules.Rules.AllowIPRanges {
		allRules = append(allRules, priorityRule{rule, RuleTypeIPRange, AccessTypeAllow})
	}
	for _, rule := range rules.Rules.DenyURLPatterns {
		allRules = append(allRules, priorityRule{rule, RuleTypeURLPattern, AccessTypeDeny})
	}
	for _, rule := range rules.Rules.AllowURLPatterns {
		allRules = append(allRules, priorityRule{rule, RuleTypeURLPattern, AccessTypeAllow})
	}
	for _, rule := range rules.Rules.DenyProtocolRules {
		allRules = append(allRules, priorityRule{rule, RuleTypeProtocolRule, AccessTypeDeny})
	}
	for _, rule := range rules.Rules.AllowProtocolRules {
		allRules = append(allRules, priorityRule{rule, RuleTypeProtocolRule, AccessTypeAllow})
	}
	
	// Sort by priority (lower number = higher priority)
	for i := 0; i < len(allRules)-1; i++ {
		for j := i + 1; j < len(allRules); j++ {
			if allRules[i].rule.Priority > allRules[j].rule.Priority {
				allRules[i], allRules[j] = allRules[j], allRules[i]
			}
		}
	}
	
	// Process rules in priority order
	for _, priorityRule := range allRules {
		if m.matchesRule(priorityRule.rule, priorityRule.ruleType, target) {
			allowed := priorityRule.accessType == AccessTypeAllow
			log.Debugf("User %s access to %s: %v (matched rule: %s, priority: %d)", 
				userID, target, allowed, priorityRule.rule.Pattern, priorityRule.rule.Priority)
			return allowed
		}
	}
	
	// No matching rule found - default deny
	log.Debugf("User %s access to %s: denied (no matching rules)", userID, target)
	return false
}

func (m *Manager) matchesRule(rule FirewallRule, ruleType RuleType, target string) bool {
	switch ruleType {
	case RuleTypeDomain:
		return m.matchDomain(rule.Pattern, target)
	case RuleTypeIP:
		return m.matchIP(rule.Pattern, target)
	case RuleTypeIPRange:
		return m.matchIPRange(rule.Pattern, target)
	case RuleTypeURLPattern:
		return m.matchURLPattern(rule.Pattern, target)
	case RuleTypeProtocolRule:
		return m.matchProtocolRule(rule, target)
	default:
		return false
	}
}

func (m *Manager) matchDomain(pattern, target string) bool {
	// Extract domain from URL if target is a URL
	targetDomain := target
	if strings.HasPrefix(target, "http://") || strings.HasPrefix(target, "https://") {
		if u, err := url.Parse(target); err == nil {
			targetDomain = strings.ToLower(u.Hostname())
		}
	} else {
		targetDomain = strings.ToLower(target)
	}
	
	pattern = strings.ToLower(pattern)
	
	// Exact match
	if pattern == targetDomain {
		return true
	}
	
	// Wildcard subdomain match (*.example.com matches sub.example.com)
	if strings.HasPrefix(pattern, "*.") {
		baseDomain := pattern[2:]
		if targetDomain == baseDomain || strings.HasSuffix(targetDomain, "."+baseDomain) {
			return true
		}
	}
	
	return false
}

func (m *Manager) matchIP(pattern, target string) bool {
	// Extract IP from URL if target is a URL
	targetIP := target
	if strings.HasPrefix(target, "http://") || strings.HasPrefix(target, "https://") {
		if u, err := url.Parse(target); err == nil {
			targetIP = u.Hostname()
		}
	}
	
	// Remove port if present
	if host, _, err := net.SplitHostPort(targetIP); err == nil {
		targetIP = host
	}
	
	targetAddr := net.ParseIP(targetIP)
	patternAddr := net.ParseIP(pattern)
	
	if targetAddr == nil || patternAddr == nil {
		return false
	}
	
	return targetAddr.Equal(patternAddr)
}

func (m *Manager) matchIPRange(pattern, target string) bool {
	// Extract IP from URL if target is a URL
	targetIP := target
	if strings.HasPrefix(target, "http://") || strings.HasPrefix(target, "https://") {
		if u, err := url.Parse(target); err == nil {
			targetIP = u.Hostname()
		}
	}
	
	// Remove port if present
	if host, _, err := net.SplitHostPort(targetIP); err == nil {
		targetIP = host
	}
	
	targetAddr := net.ParseIP(targetIP)
	if targetAddr == nil {
		return false
	}
	
	_, network, err := net.ParseCIDR(pattern)
	if err != nil {
		return false
	}
	
	return network.Contains(targetAddr)
}

func (m *Manager) matchURLPattern(pattern, target string) bool {
	regex, err := regexp.Compile("(?i)" + pattern)
	if err != nil {
		log.Errorf("Invalid regex pattern: %s, error: %v", pattern, err)
		return false
	}
	
	return regex.MatchString(target)
}

func (m *Manager) matchProtocolRule(rule FirewallRule, target string) bool {
	// Parse target connection string (format: protocol:src_ip:src_port->dst_ip:dst_port:direction)
	connInfo := m.parseConnectionTarget(target)
	if connInfo == nil {
		return false
	}
	
	// Check protocol
	if rule.Protocol != "" && strings.ToLower(rule.Protocol) != strings.ToLower(connInfo["protocol"]) {
		return false
	}
	
	// Check source IP
	if rule.SrcIP != "" && !m.matchIPOrRange(rule.SrcIP, connInfo["src_ip"]) {
		return false
	}
	
	// Check destination IP
	if rule.DstIP != "" && !m.matchIPOrRange(rule.DstIP, connInfo["dst_ip"]) {
		return false
	}
	
	// Check source port
	if rule.SrcPort != "" && !m.matchPort(rule.SrcPort, connInfo["src_port"]) {
		return false
	}
	
	// Check destination port
	if rule.DstPort != "" && !m.matchPort(rule.DstPort, connInfo["dst_port"]) {
		return false
	}
	
	// Check direction
	if rule.Direction != "" && rule.Direction != "both" {
		if rule.Direction != connInfo["direction"] {
			return false
		}
	}
	
	return true
}

func (m *Manager) parseConnectionTarget(target string) map[string]string {
	if !strings.Contains(target, "->") {
		return nil
	}
	
	parts := strings.Split(target, "->")
	if len(parts) < 2 {
		return nil
	}
	
	srcPart := parts[0]
	dstPart := parts[1]
	
	// Parse source
	srcComponents := strings.Split(srcPart, ":")
	if len(srcComponents) < 1 {
		return nil
	}
	
	protocol := srcComponents[0]
	srcIP := "*"
	srcPort := "*"
	
	if len(srcComponents) > 1 {
		srcIP = srcComponents[1]
	}
	if len(srcComponents) > 2 {
		srcPort = srcComponents[2]
	}
	
	// Parse destination
	dstComponents := strings.Split(dstPart, ":")
	dstIP := "*"
	dstPort := "*"
	direction := "outbound"
	
	if len(dstComponents) > 0 {
		dstIP = dstComponents[0]
	}
	if len(dstComponents) > 1 {
		dstPort = dstComponents[1]
	}
	if len(dstComponents) > 2 {
		direction = dstComponents[2]
	}
	
	return map[string]string{
		"protocol":  protocol,
		"src_ip":    srcIP,
		"src_port":  srcPort,
		"dst_ip":    dstIP,
		"dst_port":  dstPort,
		"direction": direction,
	}
}

func (m *Manager) matchIPOrRange(ruleIP, targetIP string) bool {
	if ruleIP == "*" || targetIP == "*" {
		return true
	}
	
	// Check if ruleIP is a CIDR range
	if strings.Contains(ruleIP, "/") {
		_, network, err := net.ParseCIDR(ruleIP)
		if err != nil {
			return false
		}
		targetAddr := net.ParseIP(targetIP)
		if targetAddr == nil {
			return false
		}
		return network.Contains(targetAddr)
	}
	
	// Exact IP match
	ruleAddr := net.ParseIP(ruleIP)
	targetAddr := net.ParseIP(targetIP)
	if ruleAddr == nil || targetAddr == nil {
		return false
	}
	
	return ruleAddr.Equal(targetAddr)
}

func (m *Manager) matchPort(rulePort, targetPort string) bool {
	if rulePort == "*" || targetPort == "*" {
		return true
	}
	
	targetPortNum, err := strconv.Atoi(targetPort)
	if err != nil {
		return false
	}
	
	// Port range (e.g., "80-443")
	if strings.Contains(rulePort, "-") {
		parts := strings.Split(rulePort, "-")
		if len(parts) != 2 {
			return false
		}
		
		start, err1 := strconv.Atoi(strings.TrimSpace(parts[0]))
		end, err2 := strconv.Atoi(strings.TrimSpace(parts[1]))
		
		if err1 != nil || err2 != nil {
			return false
		}
		
		return targetPortNum >= start && targetPortNum <= end
	}
	
	// Port list (e.g., "80,443,8080")
	if strings.Contains(rulePort, ",") {
		ports := strings.Split(rulePort, ",")
		for _, port := range ports {
			if portNum, err := strconv.Atoi(strings.TrimSpace(port)); err == nil {
				if portNum == targetPortNum {
					return true
				}
			}
		}
		return false
	}
	
	// Single port
	rulePortNum, err := strconv.Atoi(rulePort)
	if err != nil {
		return false
	}
	
	return rulePortNum == targetPortNum
}

func (m *Manager) GetUserRules(userID string) *UserRules {
	m.updateMutex.RLock()
	defer m.updateMutex.RUnlock()
	
	if rules, exists := m.userRules[userID]; exists {
		return rules
	}
	return nil
}

func (m *Manager) GetLastUpdateTime() time.Time {
	m.updateMutex.RLock()
	defer m.updateMutex.RUnlock()
	return m.lastUpdate
}

func (m *Manager) GetRulesCount() int {
	m.updateMutex.RLock()
	defer m.updateMutex.RUnlock()
	return len(m.userRules)
}