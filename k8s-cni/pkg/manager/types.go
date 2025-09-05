// Package manager provides enhanced integration with the Tobogganing Manager service
// for centralized policy management, pod registration, and traffic reporting.
//
// This package implements:
// - WebSocket-based real-time communication
// - Pod lifecycle reporting and registration
// - Network policy synchronization
// - Traffic statistics and metrics reporting
// - Health status monitoring and reporting
// - Secure authentication and API key management
//
// The manager client maintains persistent connections and handles
// automatic reconnection, backoff strategies, and error recovery.
package manager

import (
	"net"
	"time"

	"github.com/tobogganing/k8s-cni/pkg/discovery"
	"github.com/tobogganing/k8s-cni/pkg/policy"
)

// ClientConfiguration represents manager client configuration
type ClientConfiguration struct {
	// Connection settings
	ManagerURL          string        `json:"managerURL"`
	APIKey              string        `json:"apiKey"`
	ClusterID           string        `json:"clusterID"`
	NodeName            string        `json:"nodeName"`
	ConnectionTimeout   time.Duration `json:"connectionTimeout"`
	RequestTimeout      time.Duration `json:"requestTimeout"`
	
	// WebSocket settings
	EnableWebSocket     bool          `json:"enableWebSocket"`
	WSReconnectInterval time.Duration `json:"wsReconnectInterval"`
	WSMaxReconnects     int           `json:"wsMaxReconnects"`
	WSPingInterval      time.Duration `json:"wsPingInterval"`
	WSWriteTimeout      time.Duration `json:"wsWriteTimeout"`
	WSReadTimeout       time.Duration `json:"wsReadTimeout"`
	
	// Reporting settings
	EnablePodReporting     bool          `json:"enablePodReporting"`
	EnableTrafficReporting bool          `json:"enableTrafficReporting"`
	EnableHealthReporting  bool          `json:"enableHealthReporting"`
	ReportingInterval      time.Duration `json:"reportingInterval"`
	BatchSize              int           `json:"batchSize"`
	
	// Policy synchronization
	EnablePolicySync    bool          `json:"enablePolicySync"`
	PolicySyncInterval  time.Duration `json:"policySyncInterval"`
	
	// Authentication and security
	TLSEnabled          bool   `json:"tlsEnabled"`
	TLSSkipVerify       bool   `json:"tlsSkipVerify"`
	CertFile            string `json:"certFile,omitempty"`
	KeyFile             string `json:"keyFile,omitempty"`
	CAFile              string `json:"caFile,omitempty"`
	
	// Retry and backoff
	MaxRetries          int           `json:"maxRetries"`
	InitialBackoff      time.Duration `json:"initialBackoff"`
	MaxBackoff          time.Duration `json:"maxBackoff"`
	BackoffMultiplier   float64       `json:"backoffMultiplier"`
	
	// Buffer and queue settings
	EventBufferSize     int `json:"eventBufferSize"`
	MetricBufferSize    int `json:"metricBufferSize"`
	MaxQueueSize        int `json:"maxQueueSize"`
}

// PodRegistrationRequest represents a pod registration request
type PodRegistrationRequest struct {
	// Pod identification
	PodName     string `json:"podName"`
	PodUID      string `json:"podUID"`
	Namespace   string `json:"namespace"`
	NodeName    string `json:"nodeName"`
	ClusterID   string `json:"clusterID"`
	
	// Network information
	PodIP       string   `json:"podIP"`
	PodIPs      []string `json:"podIPs,omitempty"`
	HostIP      string   `json:"hostIP"`
	HostNetwork bool     `json:"hostNetwork"`
	
	// CNI specific information
	CNIVersion      string `json:"cniVersion"`
	InterfaceName   string `json:"interfaceName"`
	WireguardConfig *WireguardConfig `json:"wireguardConfig,omitempty"`
	
	// Pod metadata
	Labels            map[string]string  `json:"labels"`
	Annotations       map[string]string  `json:"annotations"`
	ServiceAccount    string             `json:"serviceAccount"`
	SecurityContext   *PodSecurityContext `json:"securityContext,omitempty"`
	
	// Container information
	Containers      []ContainerInfo `json:"containers"`
	InitContainers  []ContainerInfo `json:"initContainers,omitempty"`
	
	// Timestamps
	CreatedAt time.Time `json:"createdAt"`
	StartedAt time.Time `json:"startedAt"`
}

// PodRegistrationResponse represents a pod registration response
type PodRegistrationResponse struct {
	Success   bool   `json:"success"`
	PodID     string `json:"podID,omitempty"`
	Message   string `json:"message,omitempty"`
	
	// Assigned network configuration
	AssignedIP     string            `json:"assignedIP,omitempty"`
	NetworkConfig  *NetworkConfig    `json:"networkConfig,omitempty"`
	PolicyConfig   *PolicyConfig     `json:"policyConfig,omitempty"`
	WireguardKey   string            `json:"wireguardKey,omitempty"`
	
	// Additional metadata
	NodeID        string            `json:"nodeID,omitempty"`
	ClusterConfig *ClusterConfig    `json:"clusterConfig,omitempty"`
	Metadata      map[string]string `json:"metadata,omitempty"`
}

// WireguardConfig represents WireGuard configuration for a pod
type WireguardConfig struct {
	PublicKey      string   `json:"publicKey"`
	PrivateKey     string   `json:"privateKey,omitempty"`
	Endpoint       string   `json:"endpoint,omitempty"`
	AllowedIPs     []string `json:"allowedIPs"`
	ListenPort     int      `json:"listenPort,omitempty"`
	MTU            int      `json:"mtu,omitempty"`
	PersistentKeepalive int `json:"persistentKeepalive,omitempty"`
}

// PodSecurityContext represents pod security context information
type PodSecurityContext struct {
	RunAsUser           *int64  `json:"runAsUser,omitempty"`
	RunAsGroup          *int64  `json:"runAsGroup,omitempty"`
	RunAsNonRoot        *bool   `json:"runAsNonRoot,omitempty"`
	ReadOnlyRootFilesystem *bool `json:"readOnlyRootFilesystem,omitempty"`
	Privileged          *bool   `json:"privileged,omitempty"`
	AllowPrivilegeEscalation *bool `json:"allowPrivilegeEscalation,omitempty"`
	Capabilities        *SecurityCapabilities `json:"capabilities,omitempty"`
	SELinuxOptions      *SELinuxOptions `json:"seLinuxOptions,omitempty"`
}

// SecurityCapabilities represents Linux capabilities
type SecurityCapabilities struct {
	Add  []string `json:"add,omitempty"`
	Drop []string `json:"drop,omitempty"`
}

// SELinuxOptions represents SELinux options
type SELinuxOptions struct {
	User  string `json:"user,omitempty"`
	Role  string `json:"role,omitempty"`
	Type  string `json:"type,omitempty"`
	Level string `json:"level,omitempty"`
}

// ContainerInfo represents container information
type ContainerInfo struct {
	Name            string                 `json:"name"`
	Image           string                 `json:"image"`
	ImageID         string                 `json:"imageID,omitempty"`
	Command         []string               `json:"command,omitempty"`
	Args            []string               `json:"args,omitempty"`
	WorkingDir      string                 `json:"workingDir,omitempty"`
	Ports           []ContainerPort        `json:"ports,omitempty"`
	Env             []EnvVar               `json:"env,omitempty"`
	Resources       *ResourceRequirements  `json:"resources,omitempty"`
	SecurityContext *ContainerSecurityContext `json:"securityContext,omitempty"`
	State           string                 `json:"state,omitempty"`
	Ready           bool                   `json:"ready"`
	RestartCount    int32                  `json:"restartCount"`
	StartedAt       *time.Time             `json:"startedAt,omitempty"`
}

// ContainerPort represents a container port
type ContainerPort struct {
	Name          string `json:"name,omitempty"`
	ContainerPort int32  `json:"containerPort"`
	Protocol      string `json:"protocol,omitempty"`
	HostPort      int32  `json:"hostPort,omitempty"`
	HostIP        string `json:"hostIP,omitempty"`
}

// EnvVar represents an environment variable
type EnvVar struct {
	Name      string    `json:"name"`
	Value     string    `json:"value,omitempty"`
	ValueFrom *EnvVarSource `json:"valueFrom,omitempty"`
}

// EnvVarSource represents the source of an environment variable value
type EnvVarSource struct {
	FieldRef         *ObjectFieldSelector   `json:"fieldRef,omitempty"`
	ResourceFieldRef *ResourceFieldSelector `json:"resourceFieldRef,omitempty"`
	ConfigMapKeyRef  *ConfigMapKeySelector  `json:"configMapKeyRef,omitempty"`
	SecretKeyRef     *SecretKeySelector     `json:"secretKeyRef,omitempty"`
}

// ObjectFieldSelector represents an object field selector
type ObjectFieldSelector struct {
	APIVersion string `json:"apiVersion,omitempty"`
	FieldPath  string `json:"fieldPath"`
}

// ResourceFieldSelector represents a resource field selector
type ResourceFieldSelector struct {
	ContainerName string `json:"containerName,omitempty"`
	Resource      string `json:"resource"`
}

// ConfigMapKeySelector represents a config map key selector
type ConfigMapKeySelector struct {
	LocalObjectReference `json:",inline"`
	Key                  string `json:"key"`
	Optional             *bool  `json:"optional,omitempty"`
}

// SecretKeySelector represents a secret key selector
type SecretKeySelector struct {
	LocalObjectReference `json:",inline"`
	Key                  string `json:"key"`
	Optional             *bool  `json:"optional,omitempty"`
}

// LocalObjectReference represents a local object reference
type LocalObjectReference struct {
	Name string `json:"name,omitempty"`
}

// ResourceRequirements represents resource requirements
type ResourceRequirements struct {
	Limits   ResourceList `json:"limits,omitempty"`
	Requests ResourceList `json:"requests,omitempty"`
}

// ResourceList represents a list of resources
type ResourceList map[string]string

// ContainerSecurityContext represents container security context
type ContainerSecurityContext struct {
	Capabilities             *SecurityCapabilities `json:"capabilities,omitempty"`
	Privileged               *bool                 `json:"privileged,omitempty"`
	SELinuxOptions           *SELinuxOptions       `json:"seLinuxOptions,omitempty"`
	RunAsUser                *int64                `json:"runAsUser,omitempty"`
	RunAsGroup               *int64                `json:"runAsGroup,omitempty"`
	RunAsNonRoot             *bool                 `json:"runAsNonRoot,omitempty"`
	ReadOnlyRootFilesystem   *bool                 `json:"readOnlyRootFilesystem,omitempty"`
	AllowPrivilegeEscalation *bool                 `json:"allowPrivilegeEscalation,omitempty"`
}

// NetworkConfig represents network configuration for a pod
type NetworkConfig struct {
	InterfaceName   string   `json:"interfaceName"`
	IP              string   `json:"ip"`
	Subnet          string   `json:"subnet"`
	Gateway         string   `json:"gateway"`
	DNS             []string `json:"dns,omitempty"`
	Routes          []Route  `json:"routes,omitempty"`
	MTU             int      `json:"mtu,omitempty"`
	VLAN            int      `json:"vlan,omitempty"`
	QoS             *QoSConfig `json:"qos,omitempty"`
}

// Route represents a network route
type Route struct {
	Destination string `json:"destination"`
	Gateway     string `json:"gateway,omitempty"`
	Interface   string `json:"interface,omitempty"`
	Metric      int    `json:"metric,omitempty"`
}

// QoSConfig represents Quality of Service configuration
type QoSConfig struct {
	IngressRate  uint64 `json:"ingressRate,omitempty"`
	EgressRate   uint64 `json:"egressRate,omitempty"`
	Priority     int    `json:"priority,omitempty"`
	Class        string `json:"class,omitempty"`
}

// PolicyConfig represents policy configuration for a pod
type PolicyConfig struct {
	DefaultPolicy   string        `json:"defaultPolicy"`
	IngressRules    []PolicyRule  `json:"ingressRules,omitempty"`
	EgressRules     []PolicyRule  `json:"egressRules,omitempty"`
	AuditMode       bool          `json:"auditMode,omitempty"`
	LogViolations   bool          `json:"logViolations,omitempty"`
}

// PolicyRule represents a network policy rule
type PolicyRule struct {
	ID          string     `json:"id"`
	Priority    int        `json:"priority"`
	Action      string     `json:"action"`
	Direction   string     `json:"direction"`
	Protocol    string     `json:"protocol,omitempty"`
	Ports       []PortRange `json:"ports,omitempty"`
	Sources     []Selector  `json:"sources,omitempty"`
	Destinations []Selector `json:"destinations,omitempty"`
	Labels      map[string]string `json:"labels,omitempty"`
	Enabled     bool       `json:"enabled"`
	CreatedAt   time.Time  `json:"createdAt"`
}

// PortRange represents a port range
type PortRange struct {
	StartPort int    `json:"startPort"`
	EndPort   int    `json:"endPort,omitempty"`
	Protocol  string `json:"protocol,omitempty"`
}

// Selector represents a resource selector
type Selector struct {
	NamespaceSelector *LabelSelector `json:"namespaceSelector,omitempty"`
	PodSelector       *LabelSelector `json:"podSelector,omitempty"`
	IPBlock           *IPBlock       `json:"ipBlock,omitempty"`
}

// LabelSelector represents a label selector
type LabelSelector struct {
	MatchLabels      map[string]string `json:"matchLabels,omitempty"`
	MatchExpressions []LabelSelectorRequirement `json:"matchExpressions,omitempty"`
}

// LabelSelectorRequirement represents a label selector requirement
type LabelSelectorRequirement struct {
	Key      string   `json:"key"`
	Operator string   `json:"operator"`
	Values   []string `json:"values,omitempty"`
}

// IPBlock represents an IP block selector
type IPBlock struct {
	CIDR   string   `json:"cidr"`
	Except []string `json:"except,omitempty"`
}

// ClusterConfig represents cluster configuration
type ClusterConfig struct {
	ClusterID        string            `json:"clusterID"`
	ClusterName      string            `json:"clusterName"`
	Version          string            `json:"version"`
	Region           string            `json:"region,omitempty"`
	Zone             string            `json:"zone,omitempty"`
	NetworkCIDR      string            `json:"networkCIDR"`
	ServiceCIDR      string            `json:"serviceCIDR"`
	DNSClusterIP     string            `json:"dnsClusterIP"`
	Metadata         map[string]string `json:"metadata,omitempty"`
	Features         []string          `json:"features,omitempty"`
}

// TrafficReport represents traffic statistics report
type TrafficReport struct {
	// Report metadata
	NodeName    string    `json:"nodeName"`
	ClusterID   string    `json:"clusterID"`
	Timestamp   time.Time `json:"timestamp"`
	PeriodStart time.Time `json:"periodStart"`
	PeriodEnd   time.Time `json:"periodEnd"`
	
	// Pod-level traffic statistics
	PodTraffic []PodTrafficStats `json:"podTraffic"`
	
	// Node-level aggregated statistics
	NodeStats NodeTrafficStats `json:"nodeStats"`
	
	// Flow-level statistics
	FlowStats []FlowTrafficStats `json:"flowStats,omitempty"`
}

// PodTrafficStats represents traffic statistics for a pod
type PodTrafficStats struct {
	// Pod identification
	PodName      string `json:"podName"`
	PodUID       string `json:"podUID"`
	Namespace    string `json:"namespace"`
	PodIP        string `json:"podIP"`
	
	// Traffic counters
	BytesReceived    uint64 `json:"bytesReceived"`
	BytesSent        uint64 `json:"bytesSent"`
	PacketsReceived  uint64 `json:"packetsReceived"`
	PacketsSent      uint64 `json:"packetsSent"`
	
	// Connection statistics
	ActiveConnections uint64 `json:"activeConnections"`
	NewConnections    uint64 `json:"newConnections"`
	ClosedConnections uint64 `json:"closedConnections"`
	FailedConnections uint64 `json:"failedConnections"`
	
	// Protocol breakdown
	TCPBytes   uint64 `json:"tcpBytes"`
	UDPBytes   uint64 `json:"udpBytes"`
	ICMPBytes  uint64 `json:"icmpBytes"`
	OtherBytes uint64 `json:"otherBytes"`
	
	// Direction breakdown
	IngressBytes uint64 `json:"ingressBytes"`
	EgressBytes  uint64 `json:"egressBytes"`
	
	// Policy statistics
	AllowedBytes   uint64 `json:"allowedBytes"`
	DroppedBytes   uint64 `json:"droppedBytes"`
	LoggedBytes    uint64 `json:"loggedBytes"`
	
	// Performance metrics
	AverageLatency time.Duration `json:"averageLatency"`
	MaxLatency     time.Duration `json:"maxLatency"`
	MinLatency     time.Duration `json:"minLatency"`
	
	// Timestamps
	FirstSeen time.Time `json:"firstSeen"`
	LastSeen  time.Time `json:"lastSeen"`
}

// NodeTrafficStats represents aggregated traffic statistics for a node
type NodeTrafficStats struct {
	// Node identification
	NodeName  string `json:"nodeName"`
	
	// Aggregated counters
	TotalBytesReceived   uint64 `json:"totalBytesReceived"`
	TotalBytesSent       uint64 `json:"totalBytesSent"`
	TotalPacketsReceived uint64 `json:"totalPacketsReceived"`
	TotalPacketsSent     uint64 `json:"totalPacketsSent"`
	
	// Pod statistics
	ActivePods     int `json:"activePods"`
	RegisteredPods int `json:"registeredPods"`
	
	// Connection statistics
	TotalActiveConnections uint64 `json:"totalActiveConnections"`
	TotalNewConnections    uint64 `json:"totalNewConnections"`
	TotalClosedConnections uint64 `json:"totalClosedConnections"`
	TotalFailedConnections uint64 `json:"totalFailedConnections"`
	
	// Policy statistics
	TotalAllowedBytes uint64 `json:"totalAllowedBytes"`
	TotalDroppedBytes uint64 `json:"totalDroppedBytes"`
	TotalLoggedBytes  uint64 `json:"totalLoggedBytes"`
	
	// Resource utilization
	CPUUsagePercent    float64 `json:"cpuUsagePercent"`
	MemoryUsageBytes   uint64  `json:"memoryUsageBytes"`
	NetworkUtilization float64 `json:"networkUtilization"`
}

// FlowTrafficStats represents traffic statistics for individual flows
type FlowTrafficStats struct {
	// Flow identification
	FlowID      string `json:"flowID"`
	SrcIP       string `json:"srcIP"`
	DstIP       string `json:"dstIP"`
	SrcPort     uint16 `json:"srcPort"`
	DstPort     uint16 `json:"dstPort"`
	Protocol    string `json:"protocol"`
	
	// Flow metadata
	SrcPodName      string `json:"srcPodName,omitempty"`
	DstPodName      string `json:"dstPodName,omitempty"`
	SrcNamespace    string `json:"srcNamespace,omitempty"`
	DstNamespace    string `json:"dstNamespace,omitempty"`
	
	// Traffic counters
	Bytes          uint64 `json:"bytes"`
	Packets        uint64 `json:"packets"`
	
	// Connection details
	State          string        `json:"state"`
	Duration       time.Duration `json:"duration"`
	AverageLatency time.Duration `json:"averageLatency"`
	
	// Policy information
	PolicyAction   string `json:"policyAction"`
	RuleID         string `json:"ruleID,omitempty"`
	
	// Timestamps
	StartTime time.Time `json:"startTime"`
	EndTime   time.Time `json:"endTime"`
	LastSeen  time.Time `json:"lastSeen"`
}

// HealthReport represents node and CNI health status
type HealthReport struct {
	// Report metadata
	NodeName  string    `json:"nodeName"`
	ClusterID string    `json:"clusterID"`
	Timestamp time.Time `json:"timestamp"`
	
	// Overall health status
	OverallStatus  string `json:"overallStatus"`
	StatusMessage  string `json:"statusMessage,omitempty"`
	
	// Component health
	CNIHealth      ComponentHealth `json:"cniHealth"`
	EBPFHealth     ComponentHealth `json:"ebpfHealth"`
	PolicyHealth   ComponentHealth `json:"policyHealth"`
	WireguardHealth ComponentHealth `json:"wireguardHealth"`
	ManagerHealth  ComponentHealth `json:"managerHealth"`
	
	// Resource health
	ResourceHealth ResourceHealth `json:"resourceHealth"`
	
	// Performance metrics
	Performance PerformanceMetrics `json:"performance"`
	
	// Error tracking
	Errors []ErrorInfo `json:"errors,omitempty"`
}

// ComponentHealth represents the health status of a component
type ComponentHealth struct {
	Status         string    `json:"status"`
	Message        string    `json:"message,omitempty"`
	LastCheck      time.Time `json:"lastCheck"`
	CheckCount     uint64    `json:"checkCount"`
	FailureCount   uint64    `json:"failureCount"`
	LastFailure    time.Time `json:"lastFailure,omitempty"`
	Uptime         time.Duration `json:"uptime"`
	Version        string    `json:"version,omitempty"`
	Configuration  map[string]interface{} `json:"configuration,omitempty"`
}

// ResourceHealth represents resource utilization and health
type ResourceHealth struct {
	CPUUsage       float64 `json:"cpuUsage"`
	MemoryUsage    uint64  `json:"memoryUsage"`
	MemoryLimit    uint64  `json:"memoryLimit"`
	DiskUsage      uint64  `json:"diskUsage"`
	DiskAvailable  uint64  `json:"diskAvailable"`
	NetworkRxBytes uint64  `json:"networkRxBytes"`
	NetworkTxBytes uint64  `json:"networkTxBytes"`
	OpenFiles      int     `json:"openFiles"`
	MaxFiles       int     `json:"maxFiles"`
	Goroutines     int     `json:"goroutines"`
}

// PerformanceMetrics represents performance metrics
type PerformanceMetrics struct {
	PacketsPerSecond    float64       `json:"packetsPerSecond"`
	BytesPerSecond      float64       `json:"bytesPerSecond"`
	PolicyEvaluations   uint64        `json:"policyEvaluations"`
	AverageLatency      time.Duration `json:"averageLatency"`
	EBPFProgramLoads    uint64        `json:"ebpfProgramLoads"`
	CacheHitRatio       float64       `json:"cacheHitRatio"`
	EventsPerSecond     float64       `json:"eventsPerSecond"`
}

// ErrorInfo represents error information
type ErrorInfo struct {
	Timestamp   time.Time `json:"timestamp"`
	Component   string    `json:"component"`
	Level       string    `json:"level"`
	Message     string    `json:"message"`
	Details     string    `json:"details,omitempty"`
	Count       uint64    `json:"count"`
	FirstSeen   time.Time `json:"firstSeen"`
	LastSeen    time.Time `json:"lastSeen"`
}

// WebSocketMessage represents a WebSocket message
type WebSocketMessage struct {
	Type      string      `json:"type"`
	ID        string      `json:"id,omitempty"`
	Timestamp time.Time   `json:"timestamp"`
	Data      interface{} `json:"data"`
	Error     string      `json:"error,omitempty"`
}

// MessageType constants for WebSocket messages
const (
	MessageTypePodRegistration   = "pod_registration"
	MessageTypePodDeregistration = "pod_deregistration"
	MessageTypeTrafficReport     = "traffic_report"
	MessageTypeHealthReport      = "health_report"
	MessageTypePolicySync        = "policy_sync"
	MessageTypeConfigUpdate      = "config_update"
	MessageTypePing              = "ping"
	MessageTypePong              = "pong"
	MessageTypeError             = "error"
	MessageTypeAck               = "ack"
)

// APIResponse represents a generic API response
type APIResponse struct {
	Success   bool        `json:"success"`
	Data      interface{} `json:"data,omitempty"`
	Error     string      `json:"error,omitempty"`
	Message   string      `json:"message,omitempty"`
	Timestamp time.Time   `json:"timestamp"`
	RequestID string      `json:"requestId,omitempty"`
}

// ConnectionStatus represents the connection status to the manager
type ConnectionStatus struct {
	Connected        bool      `json:"connected"`
	LastConnected    time.Time `json:"lastConnected"`
	LastDisconnected time.Time `json:"lastDisconnected"`
	ConnectionCount  uint64    `json:"connectionCount"`
	ReconnectCount   uint64    `json:"reconnectCount"`
	LastError        string    `json:"lastError,omitempty"`
	Latency          time.Duration `json:"latency"`
	WebSocketEnabled bool      `json:"webSocketEnabled"`
}

// Statistics represents client statistics
type Statistics struct {
	// Connection statistics
	Connection ConnectionStatus `json:"connection"`
	
	// Request statistics
	RequestsSent        uint64        `json:"requestsSent"`
	ResponsesReceived   uint64        `json:"responsesReceived"`
	RequestFailures     uint64        `json:"requestFailures"`
	AverageResponseTime time.Duration `json:"averageResponseTime"`
	
	// Registration statistics
	PodsRegistered      uint64 `json:"podsRegistered"`
	PodsDeregistered    uint64 `json:"podsDeregistered"`
	RegistrationFailures uint64 `json:"registrationFailures"`
	
	// Reporting statistics
	TrafficReportsSent  uint64 `json:"trafficReportsSent"`
	HealthReportsSent   uint64 `json:"healthReportsSent"`
	PolicySyncCount     uint64 `json:"policySyncCount"`
	
	// Error statistics
	TotalErrors         uint64    `json:"totalErrors"`
	LastError           string    `json:"lastError,omitempty"`
	LastErrorTime       time.Time `json:"lastErrorTime,omitempty"`
	
	// Performance statistics
	DataSent            uint64    `json:"dataSent"`
	DataReceived        uint64    `json:"dataReceived"`
	CompressionRatio    float64   `json:"compressionRatio"`
	LastUpdate          time.Time `json:"lastUpdate"`
}