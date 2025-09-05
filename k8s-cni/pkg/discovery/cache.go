// Package discovery provides high-performance in-memory caching for Kubernetes resources
package discovery

import (
	"fmt"
	"net"
	"sync"
	"time"
	"runtime"
	"unsafe"

	"github.com/sirupsen/logrus"
)

// MemoryCache provides high-performance in-memory caching for Kubernetes resources
type MemoryCache struct {
	logger *logrus.Entry

	// Resource storage with optimized data structures
	mu           sync.RWMutex
	pods         map[string]*PodInfo           // key: namespace/name
	podsByIP     map[string]*PodInfo           // key: IP address
	namespaces   map[string]*NamespaceInfo     // key: name
	services     map[string]*ServiceInfo       // key: namespace/name
	nodes        map[string]*NodeInfo          // key: name
	endpoints    map[string][]*EndpointInfo    // key: namespace/name

	// Index structures for fast lookups
	podsByNamespace map[string]map[string]*PodInfo // namespace -> pods
	podsByLabel     map[string]map[string]*PodInfo // label_key=label_value -> pods
	servicesByNamespace map[string]map[string]*ServiceInfo // namespace -> services
	nodesByLabel    map[string]map[string]*NodeInfo // label_key=label_value -> nodes

	// Statistics and performance tracking
	stats *CacheStats

	// Configuration
	config *CacheConfiguration
}

// CacheConfiguration represents cache configuration
type CacheConfiguration struct {
	MaxEntries          int           `json:"maxEntries"`
	TTL                 time.Duration `json:"ttl"`
	GCInterval          time.Duration `json:"gcInterval"`
	IndexUpdateBatch    int           `json:"indexUpdateBatch"`
	MemoryThreshold     uint64        `json:"memoryThreshold"`
	EnableMetrics       bool          `json:"enableMetrics"`
	EnableCompression   bool          `json:"enableCompression"`
}

// NewMemoryCache creates a new high-performance memory cache
func NewMemoryCache(config *CacheConfiguration) (*MemoryCache, error) {
	if config == nil {
		config = &CacheConfiguration{
			MaxEntries:          10000,
			TTL:                 30 * time.Minute,
			GCInterval:          5 * time.Minute,
			IndexUpdateBatch:    100,
			MemoryThreshold:     500 * 1024 * 1024, // 500MB
			EnableMetrics:       true,
			EnableCompression:   false,
		}
	}

	logger := logrus.WithField("component", "discovery-cache")

	cache := &MemoryCache{
		logger: logger,
		config: config,

		// Initialize storage maps
		pods:         make(map[string]*PodInfo),
		podsByIP:     make(map[string]*PodInfo),
		namespaces:   make(map[string]*NamespaceInfo),
		services:     make(map[string]*ServiceInfo),
		nodes:        make(map[string]*NodeInfo),
		endpoints:    make(map[string][]*EndpointInfo),

		// Initialize index maps
		podsByNamespace:     make(map[string]map[string]*PodInfo),
		podsByLabel:         make(map[string]map[string]*PodInfo),
		servicesByNamespace: make(map[string]map[string]*ServiceInfo),
		nodesByLabel:        make(map[string]map[string]*NodeInfo),

		// Initialize statistics
		stats: &CacheStats{
			LastSyncTime: time.Now(),
		},
	}

	logger.Info("memory cache initialized")
	return cache, nil
}

// Pod operations

func (c *MemoryCache) GetPod(namespace, name string) (*PodInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	key := c.makePodKey(namespace, name)
	pod, exists := c.pods[key]
	if !exists {
		c.stats.CacheMisses++
		return nil, fmt.Errorf("pod not found: %s/%s", namespace, name)
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	// Return a copy to prevent external modifications
	return c.copyPod(pod), nil
}

func (c *MemoryCache) GetPodByIP(ip net.IP) (*PodInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	pod, exists := c.podsByIP[ip.String()]
	if !exists {
		c.stats.CacheMisses++
		return nil, fmt.Errorf("pod not found for IP: %s", ip.String())
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return c.copyPod(pod), nil
}

func (c *MemoryCache) GetPodsByNamespace(namespace string) ([]*PodInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	namespacePods, exists := c.podsByNamespace[namespace]
	if !exists {
		return []*PodInfo{}, nil
	}

	pods := make([]*PodInfo, 0, len(namespacePods))
	for _, pod := range namespacePods {
		pods = append(pods, c.copyPod(pod))
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return pods, nil
}

func (c *MemoryCache) GetPodsByLabel(labelSelector map[string]string) ([]*PodInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var matchingPods []*PodInfo

	// For each label selector, find matching pods
	for key, value := range labelSelector {
		labelKey := fmt.Sprintf("%s=%s", key, value)
		if labelPods, exists := c.podsByLabel[labelKey]; exists {
			for _, pod := range labelPods {
				// Check if pod matches all labels in selector
				if c.podMatchesLabels(pod, labelSelector) {
					matchingPods = append(matchingPods, c.copyPod(pod))
				}
			}
			break // Use first label for performance
		}
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return matchingPods, nil
}

func (c *MemoryCache) StorePod(pod *PodInfo) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	key := c.makePodKey(pod.Namespace, pod.Name)
	
	// Update timestamps
	pod.LastSeen = time.Now()
	if _, exists := c.pods[key]; !exists {
		pod.UpdatedAt = time.Now()
	}

	// Store in primary map
	c.pods[key] = pod

	// Update IP index
	if pod.IP != nil {
		c.podsByIP[pod.IP.String()] = pod
	}
	for _, ip := range pod.IPs {
		c.podsByIP[ip.String()] = pod
	}

	// Update namespace index
	if c.podsByNamespace[pod.Namespace] == nil {
		c.podsByNamespace[pod.Namespace] = make(map[string]*PodInfo)
	}
	c.podsByNamespace[pod.Namespace][pod.Name] = pod

	// Update label indexes
	for labelKey, labelValue := range pod.Labels {
		indexKey := fmt.Sprintf("%s=%s", labelKey, labelValue)
		if c.podsByLabel[indexKey] == nil {
			c.podsByLabel[indexKey] = make(map[string]*PodInfo)
		}
		c.podsByLabel[indexKey][key] = pod
	}

	c.stats.PodCount = len(c.pods)
	c.logger.WithField("pod", key).Debug("stored pod in cache")

	return nil
}

func (c *MemoryCache) DeletePod(namespace, name string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	key := c.makePodKey(namespace, name)
	
	pod, exists := c.pods[key]
	if !exists {
		return fmt.Errorf("pod not found: %s/%s", namespace, name)
	}

	// Remove from primary map
	delete(c.pods, key)

	// Remove from IP index
	if pod.IP != nil {
		delete(c.podsByIP, pod.IP.String())
	}
	for _, ip := range pod.IPs {
		delete(c.podsByIP, ip.String())
	}

	// Remove from namespace index
	if namespacePods, exists := c.podsByNamespace[namespace]; exists {
		delete(namespacePods, name)
		if len(namespacePods) == 0 {
			delete(c.podsByNamespace, namespace)
		}
	}

	// Remove from label indexes
	for labelKey, labelValue := range pod.Labels {
		indexKey := fmt.Sprintf("%s=%s", labelKey, labelValue)
		if labelPods, exists := c.podsByLabel[indexKey]; exists {
			delete(labelPods, key)
			if len(labelPods) == 0 {
				delete(c.podsByLabel, indexKey)
			}
		}
	}

	c.stats.PodCount = len(c.pods)
	c.logger.WithField("pod", key).Debug("deleted pod from cache")

	return nil
}

// Namespace operations

func (c *MemoryCache) GetNamespace(name string) (*NamespaceInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	namespace, exists := c.namespaces[name]
	if !exists {
		c.stats.CacheMisses++
		return nil, fmt.Errorf("namespace not found: %s", name)
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return c.copyNamespace(namespace), nil
}

func (c *MemoryCache) GetNamespaces() ([]*NamespaceInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	namespaces := make([]*NamespaceInfo, 0, len(c.namespaces))
	for _, namespace := range c.namespaces {
		namespaces = append(namespaces, c.copyNamespace(namespace))
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return namespaces, nil
}

func (c *MemoryCache) GetNamespacesByLabel(labelSelector map[string]string) ([]*NamespaceInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var matchingNamespaces []*NamespaceInfo

	for _, namespace := range c.namespaces {
		if c.namespaceMatchesLabels(namespace, labelSelector) {
			matchingNamespaces = append(matchingNamespaces, c.copyNamespace(namespace))
		}
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return matchingNamespaces, nil
}

func (c *MemoryCache) StoreNamespace(namespace *NamespaceInfo) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Update timestamps
	namespace.LastSeen = time.Now()
	if _, exists := c.namespaces[namespace.Name]; !exists {
		namespace.UpdatedAt = time.Now()
	}

	c.namespaces[namespace.Name] = namespace
	c.stats.NamespaceCount = len(c.namespaces)

	c.logger.WithField("namespace", namespace.Name).Debug("stored namespace in cache")
	return nil
}

func (c *MemoryCache) DeleteNamespace(name string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if _, exists := c.namespaces[name]; !exists {
		return fmt.Errorf("namespace not found: %s", name)
	}

	delete(c.namespaces, name)
	c.stats.NamespaceCount = len(c.namespaces)

	c.logger.WithField("namespace", name).Debug("deleted namespace from cache")
	return nil
}

// Service operations

func (c *MemoryCache) GetService(namespace, name string) (*ServiceInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	key := c.makeServiceKey(namespace, name)
	service, exists := c.services[key]
	if !exists {
		c.stats.CacheMisses++
		return nil, fmt.Errorf("service not found: %s/%s", namespace, name)
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return c.copyService(service), nil
}

func (c *MemoryCache) GetServicesByNamespace(namespace string) ([]*ServiceInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	namespaceServices, exists := c.servicesByNamespace[namespace]
	if !exists {
		return []*ServiceInfo{}, nil
	}

	services := make([]*ServiceInfo, 0, len(namespaceServices))
	for _, service := range namespaceServices {
		services = append(services, c.copyService(service))
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return services, nil
}

func (c *MemoryCache) GetServicesByLabel(labelSelector map[string]string) ([]*ServiceInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var matchingServices []*ServiceInfo

	for _, service := range c.services {
		if c.serviceMatchesLabels(service, labelSelector) {
			matchingServices = append(matchingServices, c.copyService(service))
		}
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return matchingServices, nil
}

func (c *MemoryCache) StoreService(service *ServiceInfo) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	key := c.makeServiceKey(service.Namespace, service.Name)
	
	// Update timestamps
	service.LastSeen = time.Now()
	if _, exists := c.services[key]; !exists {
		service.UpdatedAt = time.Now()
	}

	// Store in primary map
	c.services[key] = service

	// Update namespace index
	if c.servicesByNamespace[service.Namespace] == nil {
		c.servicesByNamespace[service.Namespace] = make(map[string]*ServiceInfo)
	}
	c.servicesByNamespace[service.Namespace][service.Name] = service

	c.stats.ServiceCount = len(c.services)
	c.logger.WithField("service", key).Debug("stored service in cache")

	return nil
}

func (c *MemoryCache) DeleteService(namespace, name string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	key := c.makeServiceKey(namespace, name)
	
	if _, exists := c.services[key]; !exists {
		return fmt.Errorf("service not found: %s/%s", namespace, name)
	}

	// Remove from primary map
	delete(c.services, key)

	// Remove from namespace index
	if namespaceServices, exists := c.servicesByNamespace[namespace]; exists {
		delete(namespaceServices, name)
		if len(namespaceServices) == 0 {
			delete(c.servicesByNamespace, namespace)
		}
	}

	c.stats.ServiceCount = len(c.services)
	c.logger.WithField("service", key).Debug("deleted service from cache")

	return nil
}

// Node operations

func (c *MemoryCache) GetNode(name string) (*NodeInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	node, exists := c.nodes[name]
	if !exists {
		c.stats.CacheMisses++
		return nil, fmt.Errorf("node not found: %s", name)
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return c.copyNode(node), nil
}

func (c *MemoryCache) GetNodes() ([]*NodeInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	nodes := make([]*NodeInfo, 0, len(c.nodes))
	for _, node := range c.nodes {
		nodes = append(nodes, c.copyNode(node))
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return nodes, nil
}

func (c *MemoryCache) GetNodesByLabel(labelSelector map[string]string) ([]*NodeInfo, error) {
	c.mu.RLock()
	defer c.mu.RUnlock()

	var matchingNodes []*NodeInfo

	// For each label selector, find matching nodes
	for key, value := range labelSelector {
		labelKey := fmt.Sprintf("%s=%s", key, value)
		if labelNodes, exists := c.nodesByLabel[labelKey]; exists {
			for _, node := range labelNodes {
				// Check if node matches all labels in selector
				if c.nodeMatchesLabels(node, labelSelector) {
					matchingNodes = append(matchingNodes, c.copyNode(node))
				}
			}
			break // Use first label for performance
		}
	}

	c.stats.CacheHits++
	c.updateCacheHitRatio()

	return matchingNodes, nil
}

func (c *MemoryCache) StoreNode(node *NodeInfo) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Update timestamps
	node.LastSeen = time.Now()
	if _, exists := c.nodes[node.Name]; !exists {
		node.UpdatedAt = time.Now()
	}

	// Store in primary map
	c.nodes[node.Name] = node

	// Update label indexes
	for labelKey, labelValue := range node.Labels {
		indexKey := fmt.Sprintf("%s=%s", labelKey, labelValue)
		if c.nodesByLabel[indexKey] == nil {
			c.nodesByLabel[indexKey] = make(map[string]*NodeInfo)
		}
		c.nodesByLabel[indexKey][node.Name] = node
	}

	c.stats.NodeCount = len(c.nodes)
	c.logger.WithField("node", node.Name).Debug("stored node in cache")

	return nil
}

func (c *MemoryCache) DeleteNode(name string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	node, exists := c.nodes[name]
	if !exists {
		return fmt.Errorf("node not found: %s", name)
	}

	// Remove from primary map
	delete(c.nodes, name)

	// Remove from label indexes
	for labelKey, labelValue := range node.Labels {
		indexKey := fmt.Sprintf("%s=%s", labelKey, labelValue)
		if labelNodes, exists := c.nodesByLabel[indexKey]; exists {
			delete(labelNodes, name)
			if len(labelNodes) == 0 {
				delete(c.nodesByLabel, indexKey)
			}
		}
	}

	c.stats.NodeCount = len(c.nodes)
	c.logger.WithField("node", name).Debug("deleted node from cache")

	return nil
}

// Cache management operations

func (c *MemoryCache) Clear() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Clear all storage maps
	c.pods = make(map[string]*PodInfo)
	c.podsByIP = make(map[string]*PodInfo)
	c.namespaces = make(map[string]*NamespaceInfo)
	c.services = make(map[string]*ServiceInfo)
	c.nodes = make(map[string]*NodeInfo)
	c.endpoints = make(map[string][]*EndpointInfo)

	// Clear all index maps
	c.podsByNamespace = make(map[string]map[string]*PodInfo)
	c.podsByLabel = make(map[string]map[string]*PodInfo)
	c.servicesByNamespace = make(map[string]map[string]*ServiceInfo)
	c.nodesByLabel = make(map[string]map[string]*NodeInfo)

	// Reset statistics
	c.stats = &CacheStats{
		LastSyncTime: time.Now(),
	}

	c.logger.Info("cleared all cache entries")
	return nil
}

func (c *MemoryCache) Stats() *CacheStats {
	c.mu.RLock()
	defer c.mu.RUnlock()

	// Update memory usage
	var memStats runtime.MemStats
	runtime.ReadMemStats(&memStats)
	c.stats.MemoryUsageBytes = memStats.Alloc

	// Create a copy to avoid race conditions
	stats := *c.stats
	return &stats
}

func (c *MemoryCache) GarbageCollect() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	now := time.Now()
	cutoff := now.Add(-c.config.TTL)
	
	removedCount := 0

	// Collect expired pods
	for key, pod := range c.pods {
		if pod.LastSeen.Before(cutoff) || (pod.DeletedAt != nil && pod.DeletedAt.Before(cutoff)) {
			c.removePodUnsafe(key, pod)
			removedCount++
		}
	}

	// Collect expired namespaces
	for name, namespace := range c.namespaces {
		if namespace.LastSeen.Before(cutoff) || (namespace.DeletedAt != nil && namespace.DeletedAt.Before(cutoff)) {
			delete(c.namespaces, name)
			removedCount++
		}
	}

	// Collect expired services
	for key, service := range c.services {
		if service.LastSeen.Before(cutoff) || (service.DeletedAt != nil && service.DeletedAt.Before(cutoff)) {
			c.removeServiceUnsafe(key, service)
			removedCount++
		}
	}

	// Collect expired nodes
	for name, node := range c.nodes {
		if node.LastSeen.Before(cutoff) || (node.DeletedAt != nil && node.DeletedAt.Before(cutoff)) {
			c.removeNodeUnsafe(name, node)
			removedCount++
		}
	}

	// Update statistics
	c.stats.PodCount = len(c.pods)
	c.stats.NamespaceCount = len(c.namespaces)
	c.stats.ServiceCount = len(c.services)
	c.stats.NodeCount = len(c.nodes)
	c.stats.LastGCTime = now

	if removedCount > 0 {
		c.logger.WithField("removed_count", removedCount).Info("garbage collection completed")
	}

	return nil
}

// Helper methods

func (c *MemoryCache) makePodKey(namespace, name string) string {
	return fmt.Sprintf("%s/%s", namespace, name)
}

func (c *MemoryCache) makeServiceKey(namespace, name string) string {
	return fmt.Sprintf("%s/%s", namespace, name)
}

func (c *MemoryCache) updateCacheHitRatio() {
	total := c.stats.CacheHits + c.stats.CacheMisses
	if total > 0 {
		c.stats.CacheHitRatio = float64(c.stats.CacheHits) / float64(total)
	}
}

func (c *MemoryCache) podMatchesLabels(pod *PodInfo, labelSelector map[string]string) bool {
	for key, value := range labelSelector {
		if pod.Labels[key] != value {
			return false
		}
	}
	return true
}

func (c *MemoryCache) namespaceMatchesLabels(namespace *NamespaceInfo, labelSelector map[string]string) bool {
	for key, value := range labelSelector {
		if namespace.Labels[key] != value {
			return false
		}
	}
	return true
}

func (c *MemoryCache) serviceMatchesLabels(service *ServiceInfo, labelSelector map[string]string) bool {
	for key, value := range labelSelector {
		if service.Labels[key] != value {
			return false
		}
	}
	return true
}

func (c *MemoryCache) nodeMatchesLabels(node *NodeInfo, labelSelector map[string]string) bool {
	for key, value := range labelSelector {
		if node.Labels[key] != value {
			return false
		}
	}
	return true
}

func (c *MemoryCache) removePodUnsafe(key string, pod *PodInfo) {
	// Remove from primary map
	delete(c.pods, key)

	// Remove from IP index
	if pod.IP != nil {
		delete(c.podsByIP, pod.IP.String())
	}
	for _, ip := range pod.IPs {
		delete(c.podsByIP, ip.String())
	}

	// Remove from namespace index
	if namespacePods, exists := c.podsByNamespace[pod.Namespace]; exists {
		delete(namespacePods, pod.Name)
		if len(namespacePods) == 0 {
			delete(c.podsByNamespace, pod.Namespace)
		}
	}

	// Remove from label indexes
	for labelKey, labelValue := range pod.Labels {
		indexKey := fmt.Sprintf("%s=%s", labelKey, labelValue)
		if labelPods, exists := c.podsByLabel[indexKey]; exists {
			delete(labelPods, key)
			if len(labelPods) == 0 {
				delete(c.podsByLabel, indexKey)
			}
		}
	}
}

func (c *MemoryCache) removeServiceUnsafe(key string, service *ServiceInfo) {
	// Remove from primary map
	delete(c.services, key)

	// Remove from namespace index
	if namespaceServices, exists := c.servicesByNamespace[service.Namespace]; exists {
		delete(namespaceServices, service.Name)
		if len(namespaceServices) == 0 {
			delete(c.servicesByNamespace, service.Namespace)
		}
	}
}

func (c *MemoryCache) removeNodeUnsafe(name string, node *NodeInfo) {
	// Remove from primary map
	delete(c.nodes, name)

	// Remove from label indexes
	for labelKey, labelValue := range node.Labels {
		indexKey := fmt.Sprintf("%s=%s", labelKey, labelValue)
		if labelNodes, exists := c.nodesByLabel[indexKey]; exists {
			delete(labelNodes, name)
			if len(labelNodes) == 0 {
				delete(c.nodesByLabel, indexKey)
			}
		}
	}
}

// Deep copy methods to prevent external modifications

func (c *MemoryCache) copyPod(pod *PodInfo) *PodInfo {
	if pod == nil {
		return nil
	}

	// Create a new pod with copied fields
	copied := &PodInfo{
		Name:              pod.Name,
		Namespace:         pod.Namespace,
		UID:               pod.UID,
		Labels:            make(map[string]string),
		Annotations:       make(map[string]string),
		IPs:               make([]net.IP, len(pod.IPs)),
		HostNetwork:       pod.HostNetwork,
		DNSPolicy:         pod.DNSPolicy,
		ServiceAccount:    pod.ServiceAccount,
		NodeName:          pod.NodeName,
		NodeSelector:      make(map[string]string),
		Phase:             pod.Phase,
		QOSClass:          pod.QOSClass,
		RestartPolicy:     pod.RestartPolicy,
		CreatedAt:         pod.CreatedAt,
		UpdatedAt:         pod.UpdatedAt,
		LastSeen:          pod.LastSeen,
		CNIVersion:        pod.CNIVersion,
		CNIConfig:         pod.CNIConfig,
		InterfaceName:     pod.InterfaceName,
		WireguardKey:      pod.WireguardKey,
	}

	// Copy IP
	if pod.IP != nil {
		copied.IP = make(net.IP, len(pod.IP))
		copy(copied.IP, pod.IP)
	}

	// Copy host IP
	if pod.HostIP != nil {
		copied.HostIP = make(net.IP, len(pod.HostIP))
		copy(copied.HostIP, pod.HostIP)
	}

	// Copy IPs slice
	for i, ip := range pod.IPs {
		copied.IPs[i] = make(net.IP, len(ip))
		copy(copied.IPs[i], ip)
	}

	// Copy labels
	for k, v := range pod.Labels {
		copied.Labels[k] = v
	}

	// Copy annotations
	for k, v := range pod.Annotations {
		copied.Annotations[k] = v
	}

	// Copy node selector
	for k, v := range pod.NodeSelector {
		copied.NodeSelector[k] = v
	}

	// Copy deleted timestamp if exists
	if pod.DeletedAt != nil {
		t := *pod.DeletedAt
		copied.DeletedAt = &t
	}

	return copied
}

func (c *MemoryCache) copyNamespace(namespace *NamespaceInfo) *NamespaceInfo {
	if namespace == nil {
		return nil
	}

	copied := &NamespaceInfo{
		Name:               namespace.Name,
		UID:                namespace.UID,
		Labels:             make(map[string]string),
		Annotations:        make(map[string]string),
		Phase:              namespace.Phase,
		NetworkPolicyCount: namespace.NetworkPolicyCount,
		DefaultDeny:        namespace.DefaultDeny,
		IstioInjection:     namespace.IstioInjection,
		MeshConfig:         namespace.MeshConfig,
		CreatedAt:          namespace.CreatedAt,
		UpdatedAt:          namespace.UpdatedAt,
		LastSeen:           namespace.LastSeen,
		PodCount:           namespace.PodCount,
		ServiceCount:       namespace.ServiceCount,
	}

	// Copy labels
	for k, v := range namespace.Labels {
		copied.Labels[k] = v
	}

	// Copy annotations
	for k, v := range namespace.Annotations {
		copied.Annotations[k] = v
	}

	// Copy deleted timestamp if exists
	if namespace.DeletedAt != nil {
		t := *namespace.DeletedAt
		copied.DeletedAt = &t
	}

	return copied
}

func (c *MemoryCache) copyService(service *ServiceInfo) *ServiceInfo {
	if service == nil {
		return nil
	}

	copied := &ServiceInfo{
		Name:                     service.Name,
		Namespace:                service.Namespace,
		UID:                      service.UID,
		Labels:                   make(map[string]string),
		Annotations:              make(map[string]string),
		Type:                     service.Type,
		ClusterIP:                service.ClusterIP,
		ClusterIPs:               make([]string, len(service.ClusterIPs)),
		ExternalIPs:              make([]string, len(service.ExternalIPs)),
		LoadBalancerIP:           service.LoadBalancerIP,
		ExternalName:             service.ExternalName,
		Selector:                 make(map[string]string),
		SessionAffinity:          service.SessionAffinity,
		LoadBalancerSourceRanges: make([]string, len(service.LoadBalancerSourceRanges)),
		CreatedAt:                service.CreatedAt,
		UpdatedAt:                service.UpdatedAt,
		LastSeen:                 service.LastSeen,
		EndpointCount:            service.EndpointCount,
		ReadyCount:               service.ReadyCount,
	}

	// Copy slices
	copy(copied.ClusterIPs, service.ClusterIPs)
	copy(copied.ExternalIPs, service.ExternalIPs)
	copy(copied.LoadBalancerSourceRanges, service.LoadBalancerSourceRanges)

	// Copy labels
	for k, v := range service.Labels {
		copied.Labels[k] = v
	}

	// Copy annotations
	for k, v := range service.Annotations {
		copied.Annotations[k] = v
	}

	// Copy selector
	for k, v := range service.Selector {
		copied.Selector[k] = v
	}

	// Copy deleted timestamp if exists
	if service.DeletedAt != nil {
		t := *service.DeletedAt
		copied.DeletedAt = &t
	}

	return copied
}

func (c *MemoryCache) copyNode(node *NodeInfo) *NodeInfo {
	if node == nil {
		return nil
	}

	copied := &NodeInfo{
		Name:              node.Name,
		UID:               node.UID,
		Labels:            make(map[string]string),
		Annotations:       make(map[string]string),
		PodCIDR:           node.PodCIDR,
		PodCIDRs:          make([]string, len(node.PodCIDRs)),
		ProviderID:        node.ProviderID,
		Unschedulable:     node.Unschedulable,
		Phase:             node.Phase,
		CreatedAt:         node.CreatedAt,
		UpdatedAt:         node.UpdatedAt,
		LastSeen:          node.LastSeen,
		PodCount:          node.PodCount,
		RunningPodCount:   node.RunningPodCount,
		ScheduledPodCount: node.ScheduledPodCount,
	}

	// Copy slices
	copy(copied.PodCIDRs, node.PodCIDRs)

	// Copy labels
	for k, v := range node.Labels {
		copied.Labels[k] = v
	}

	// Copy annotations
	for k, v := range node.Annotations {
		copied.Annotations[k] = v
	}

	// Copy deleted timestamp if exists
	if node.DeletedAt != nil {
		t := *node.DeletedAt
		copied.DeletedAt = &t
	}

	return copied
}