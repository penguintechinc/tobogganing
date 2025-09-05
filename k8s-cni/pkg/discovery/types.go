// Package discovery provides Kubernetes resource tracking and discovery
// for the Tobogganing CNI plugin.
//
// This package implements:
// - Pod lifecycle event watching and caching
// - Namespace metadata tracking and label management
// - Service discovery and endpoint monitoring
// - Real-time Kubernetes API integration
// - Event-driven resource synchronization
//
// The discovery engine integrates with the policy manager to provide
// up-to-date resource information for network policy enforcement.
package discovery

import (
	"net"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// ResourceType represents the type of Kubernetes resource
type ResourceType string

const (
	ResourceTypePod       ResourceType = "pod"
	ResourceTypeNamespace ResourceType = "namespace"
	ResourceTypeService   ResourceType = "service"
	ResourceTypeEndpoint  ResourceType = "endpoint"
	ResourceTypeNode      ResourceType = "node"
)

// EventType represents the type of resource event
type EventType string

const (
	EventTypeAdded    EventType = "added"
	EventTypeModified EventType = "modified"
	EventTypeDeleted  EventType = "deleted"
)

// PodInfo represents comprehensive pod information
type PodInfo struct {
	// Basic metadata
	Name        string            `json:"name"`
	Namespace   string            `json:"namespace"`
	UID         string            `json:"uid"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`

	// Network information
	IP             net.IP   `json:"ip"`
	IPs            []net.IP `json:"ips"`
	HostNetwork    bool     `json:"hostNetwork"`
	DNSPolicy      string   `json:"dnsPolicy"`
	DNSConfig      *corev1.PodDNSConfig `json:"dnsConfig,omitempty"`

	// Security context
	ServiceAccount    string                         `json:"serviceAccount"`
	SecurityContext   *corev1.PodSecurityContext     `json:"securityContext,omitempty"`
	ImagePullSecrets  []corev1.LocalObjectReference  `json:"imagePullSecrets,omitempty"`

	// Node information
	NodeName     string `json:"nodeName"`
	NodeSelector map[string]string `json:"nodeSelector,omitempty"`

	// Scheduling information
	Priority      *int32                      `json:"priority,omitempty"`
	PriorityClass string                      `json:"priorityClass,omitempty"`
	Tolerations   []corev1.Toleration         `json:"tolerations,omitempty"`
	Affinity      *corev1.Affinity            `json:"affinity,omitempty"`

	// Runtime status
	Phase             corev1.PodPhase       `json:"phase"`
	Conditions        []corev1.PodCondition `json:"conditions"`
	QOSClass          corev1.PodQOSClass    `json:"qosClass"`
	StartTime         *metav1.Time          `json:"startTime,omitempty"`
	RestartPolicy     corev1.RestartPolicy  `json:"restartPolicy"`

	// Container information
	Containers      []ContainerInfo `json:"containers"`
	InitContainers  []ContainerInfo `json:"initContainers"`

	// Networking
	HostIP    net.IP `json:"hostIP"`
	PodIPs    []corev1.PodIP `json:"podIPs"`

	// Lifecycle timestamps
	CreatedAt   time.Time `json:"createdAt"`
	UpdatedAt   time.Time `json:"updatedAt"`
	LastSeen    time.Time `json:"lastSeen"`
	DeletedAt   *time.Time `json:"deletedAt,omitempty"`

	// CNI specific
	CNIVersion   string `json:"cniVersion,omitempty"`
	CNIConfig    string `json:"cniConfig,omitempty"`
	InterfaceName string `json:"interfaceName,omitempty"`
	WireguardKey string `json:"wireguardKey,omitempty"`
}

// ContainerInfo represents container information within a pod
type ContainerInfo struct {
	Name            string                        `json:"name"`
	Image           string                        `json:"image"`
	ImageID         string                        `json:"imageID"`
	Command         []string                      `json:"command,omitempty"`
	Args            []string                      `json:"args,omitempty"`
	Env             []corev1.EnvVar               `json:"env,omitempty"`
	Resources       corev1.ResourceRequirements   `json:"resources,omitempty"`
	SecurityContext *corev1.SecurityContext       `json:"securityContext,omitempty"`
	Ports           []corev1.ContainerPort        `json:"ports,omitempty"`
	VolumeMounts    []corev1.VolumeMount          `json:"volumeMounts,omitempty"`
	State           corev1.ContainerState         `json:"state"`
	Ready           bool                          `json:"ready"`
	RestartCount    int32                         `json:"restartCount"`
}

// NamespaceInfo represents comprehensive namespace information
type NamespaceInfo struct {
	// Basic metadata
	Name        string            `json:"name"`
	UID         string            `json:"uid"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`

	// Status
	Phase      corev1.NamespacePhase      `json:"phase"`
	Conditions []corev1.NamespaceCondition `json:"conditions"`

	// Resource quotas and limits
	ResourceQuotas []ResourceQuotaInfo `json:"resourceQuotas,omitempty"`
	LimitRanges    []LimitRangeInfo    `json:"limitRanges,omitempty"`

	// Network policies
	NetworkPolicyCount int    `json:"networkPolicyCount"`
	DefaultDeny        bool   `json:"defaultDeny"`

	// Service mesh integration
	IstioInjection bool   `json:"istioInjection"`
	MeshConfig     string `json:"meshConfig,omitempty"`

	// Lifecycle timestamps
	CreatedAt time.Time  `json:"createdAt"`
	UpdatedAt time.Time  `json:"updatedAt"`
	LastSeen  time.Time  `json:"lastSeen"`
	DeletedAt *time.Time `json:"deletedAt,omitempty"`

	// Statistics
	PodCount     int `json:"podCount"`
	ServiceCount int `json:"serviceCount"`
}

// ResourceQuotaInfo represents resource quota information
type ResourceQuotaInfo struct {
	Name      string                       `json:"name"`
	Spec      corev1.ResourceQuotaSpec     `json:"spec"`
	Status    corev1.ResourceQuotaStatus   `json:"status"`
	CreatedAt time.Time                    `json:"createdAt"`
}

// LimitRangeInfo represents limit range information
type LimitRangeInfo struct {
	Name      string                   `json:"name"`
	Spec      corev1.LimitRangeSpec    `json:"spec"`
	CreatedAt time.Time                `json:"createdAt"`
}

// ServiceInfo represents comprehensive service information
type ServiceInfo struct {
	// Basic metadata
	Name        string            `json:"name"`
	Namespace   string            `json:"namespace"`
	UID         string            `json:"uid"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`

	// Service specification
	Type                  corev1.ServiceType         `json:"type"`
	ClusterIP             string                     `json:"clusterIP"`
	ClusterIPs            []string                   `json:"clusterIPs"`
	ExternalIPs           []string                   `json:"externalIPs"`
	LoadBalancerIP        string                     `json:"loadBalancerIP,omitempty"`
	ExternalName          string                     `json:"externalName,omitempty"`
	Selector              map[string]string          `json:"selector,omitempty"`
	Ports                 []ServicePortInfo          `json:"ports"`
	SessionAffinity       corev1.ServiceAffinity     `json:"sessionAffinity"`
	LoadBalancerSourceRanges []string                `json:"loadBalancerSourceRanges,omitempty"`

	// Service status
	LoadBalancerIngress []corev1.LoadBalancerIngress `json:"loadBalancerIngress,omitempty"`
	Conditions          []metav1.Condition           `json:"conditions,omitempty"`

	// Endpoints
	Endpoints []EndpointInfo `json:"endpoints"`

	// Lifecycle timestamps
	CreatedAt time.Time  `json:"createdAt"`
	UpdatedAt time.Time  `json:"updatedAt"`
	LastSeen  time.Time  `json:"lastSeen"`
	DeletedAt *time.Time `json:"deletedAt,omitempty"`

	// Statistics
	EndpointCount int `json:"endpointCount"`
	ReadyCount    int `json:"readyCount"`
}

// ServicePortInfo represents service port information
type ServicePortInfo struct {
	Name       string      `json:"name,omitempty"`
	Protocol   string      `json:"protocol"`
	Port       int32       `json:"port"`
	TargetPort interface{} `json:"targetPort"`
	NodePort   int32       `json:"nodePort,omitempty"`
}

// EndpointInfo represents service endpoint information
type EndpointInfo struct {
	// Network information
	IP   string   `json:"ip"`
	IPv6 string   `json:"ipv6,omitempty"`
	Hostname string   `json:"hostname,omitempty"`
	NodeName string   `json:"nodeName,omitempty"`
	Zone     string   `json:"zone,omitempty"`

	// Port information
	Ports []EndpointPortInfo `json:"ports"`

	// Readiness
	Ready       bool                    `json:"ready"`
	Serving     bool                    `json:"serving"`
	Terminating bool                    `json:"terminating"`
	Conditions  []metav1.Condition      `json:"conditions,omitempty"`

	// Target reference
	TargetRef *corev1.ObjectReference `json:"targetRef,omitempty"`

	// Timestamps
	LastTransitionTime *metav1.Time `json:"lastTransitionTime,omitempty"`
	LastSeen           time.Time    `json:"lastSeen"`
}

// EndpointPortInfo represents endpoint port information
type EndpointPortInfo struct {
	Name     string `json:"name,omitempty"`
	Port     int32  `json:"port"`
	Protocol string `json:"protocol"`
}

// NodeInfo represents comprehensive node information
type NodeInfo struct {
	// Basic metadata
	Name        string            `json:"name"`
	UID         string            `json:"uid"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`

	// Node specification
	PodCIDR      string   `json:"podCIDR,omitempty"`
	PodCIDRs     []string `json:"podCIDRs,omitempty"`
	ProviderID   string   `json:"providerID,omitempty"`
	Unschedulable bool    `json:"unschedulable"`
	Taints       []corev1.Taint `json:"taints,omitempty"`

	// Node status
	Phase      corev1.NodePhase      `json:"phase"`
	Conditions []corev1.NodeCondition `json:"conditions"`
	Addresses  []corev1.NodeAddress   `json:"addresses"`
	NodeInfo   corev1.NodeSystemInfo  `json:"nodeInfo"`

	// Resource capacity and allocation
	Capacity    corev1.ResourceList `json:"capacity"`
	Allocatable corev1.ResourceList `json:"allocatable"`

	// Runtime information
	DaemonEndpoints corev1.NodeDaemonEndpoints `json:"daemonEndpoints"`
	Images          []corev1.ContainerImage    `json:"images,omitempty"`
	Config          *corev1.NodeConfigStatus   `json:"config,omitempty"`

	// Lifecycle timestamps
	CreatedAt time.Time  `json:"createdAt"`
	UpdatedAt time.Time  `json:"updatedAt"`
	LastSeen  time.Time  `json:"lastSeen"`
	DeletedAt *time.Time `json:"deletedAt,omitempty"`

	// Statistics
	PodCount          int `json:"podCount"`
	RunningPodCount   int `json:"runningPodCount"`
	ScheduledPodCount int `json:"scheduledPodCount"`
}

// ResourceEvent represents a Kubernetes resource event
type ResourceEvent struct {
	// Event metadata
	Type      EventType    `json:"type"`
	Resource  ResourceType `json:"resource"`
	Timestamp time.Time    `json:"timestamp"`

	// Resource identification
	Name      string `json:"name"`
	Namespace string `json:"namespace,omitempty"`
	UID       string `json:"uid"`

	// Event data
	Object    interface{} `json:"object"`
	OldObject interface{} `json:"oldObject,omitempty"`

	// Additional context
	Reason  string `json:"reason,omitempty"`
	Message string `json:"message,omitempty"`
	Source  string `json:"source,omitempty"`
}

// CacheStats represents cache statistics
type CacheStats struct {
	// Resource counts
	PodCount       int `json:"podCount"`
	NamespaceCount int `json:"namespaceCount"`
	ServiceCount   int `json:"serviceCount"`
	EndpointCount  int `json:"endpointCount"`
	NodeCount      int `json:"nodeCount"`

	// Event statistics
	EventsProcessed     uint64    `json:"eventsProcessed"`
	EventsPerSecond     float64   `json:"eventsPerSecond"`
	LastEventProcessed  time.Time `json:"lastEventProcessed"`
	EventProcessingLag  time.Duration `json:"eventProcessingLag"`

	// Cache performance
	CacheHits     uint64 `json:"cacheHits"`
	CacheMisses   uint64 `json:"cacheMisses"`
	CacheHitRatio float64 `json:"cacheHitRatio"`

	// Synchronization status
	InSync          bool      `json:"inSync"`
	LastSyncTime    time.Time `json:"lastSyncTime"`
	SyncErrors      uint64    `json:"syncErrors"`
	LastSyncError   string    `json:"lastSyncError,omitempty"`
	LastSyncLatency time.Duration `json:"lastSyncLatency"`

	// API server connectivity
	APIServerConnected bool      `json:"apiServerConnected"`
	APIServerVersion   string    `json:"apiServerVersion,omitempty"`
	LastAPICall        time.Time `json:"lastAPICall"`
	APICallFailures    uint64    `json:"apiCallFailures"`

	// Memory usage
	MemoryUsageBytes uint64    `json:"memoryUsageBytes"`
	LastGCTime       time.Time `json:"lastGCTime"`
}

// WatcherConfiguration represents configuration for resource watchers
type WatcherConfiguration struct {
	// Resource selection
	Namespaces        []string          `json:"namespaces,omitempty"`
	LabelSelector     string            `json:"labelSelector,omitempty"`
	FieldSelector     string            `json:"fieldSelector,omitempty"`
	ResourceVersions  map[string]string `json:"resourceVersions,omitempty"`

	// Performance tuning
	ResyncPeriod      time.Duration `json:"resyncPeriod"`
	BufferSize        int           `json:"bufferSize"`
	WorkerCount       int           `json:"workerCount"`
	RetryBackoff      time.Duration `json:"retryBackoff"`
	MaxRetries        int           `json:"maxRetries"`

	// Filtering options
	EnablePodWatch       bool `json:"enablePodWatch"`
	EnableNamespaceWatch bool `json:"enableNamespaceWatch"`
	EnableServiceWatch   bool `json:"enableServiceWatch"`
	EnableEndpointWatch  bool `json:"enableEndpointWatch"`
	EnableNodeWatch      bool `json:"enableNodeWatch"`

	// Advanced options
	EnableOwnerReferences bool   `json:"enableOwnerReferences"`
	EnableFinalizers      bool   `json:"enableFinalizers"`
	IncludeUninitialized  bool   `json:"includeUninitialized"`
	WatchTimeoutSeconds   *int64 `json:"watchTimeoutSeconds,omitempty"`

	// Event handling
	EnableEventBuffer     bool          `json:"enableEventBuffer"`
	EventBufferSize       int           `json:"eventBufferSize"`
	EventBatchSize        int           `json:"eventBatchSize"`
	EventProcessingDelay  time.Duration `json:"eventProcessingDelay"`
}

// EventHandler represents an interface for handling resource events
type EventHandler interface {
	// Resource event handlers
	OnPodEvent(event *ResourceEvent, pod *PodInfo) error
	OnNamespaceEvent(event *ResourceEvent, namespace *NamespaceInfo) error
	OnServiceEvent(event *ResourceEvent, service *ServiceInfo) error
	OnEndpointEvent(event *ResourceEvent, endpoint *EndpointInfo) error
	OnNodeEvent(event *ResourceEvent, node *NodeInfo) error

	// Error handling
	OnError(err error, resource ResourceType) error
}

// Cache represents an interface for resource caching
type Cache interface {
	// Pod operations
	GetPod(namespace, name string) (*PodInfo, error)
	GetPodByIP(ip net.IP) (*PodInfo, error)
	GetPodsByNamespace(namespace string) ([]*PodInfo, error)
	GetPodsByLabel(labelSelector map[string]string) ([]*PodInfo, error)
	StorePod(pod *PodInfo) error
	DeletePod(namespace, name string) error

	// Namespace operations
	GetNamespace(name string) (*NamespaceInfo, error)
	GetNamespaces() ([]*NamespaceInfo, error)
	GetNamespacesByLabel(labelSelector map[string]string) ([]*NamespaceInfo, error)
	StoreNamespace(namespace *NamespaceInfo) error
	DeleteNamespace(name string) error

	// Service operations
	GetService(namespace, name string) (*ServiceInfo, error)
	GetServicesByNamespace(namespace string) ([]*ServiceInfo, error)
	GetServicesByLabel(labelSelector map[string]string) ([]*ServiceInfo, error)
	StoreService(service *ServiceInfo) error
	DeleteService(namespace, name string) error

	// Node operations
	GetNode(name string) (*NodeInfo, error)
	GetNodes() ([]*NodeInfo, error)
	GetNodesByLabel(labelSelector map[string]string) ([]*NodeInfo, error)
	StoreNode(node *NodeInfo) error
	DeleteNode(name string) error

	// Cache management
	Clear() error
	Stats() *CacheStats
	GarbageCollect() error
}