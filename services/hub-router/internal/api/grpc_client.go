// Package api provides the gRPC client for communication between the
// hub-router and the hub-api service.
//
// The hub-router uses this client to:
// 1. Fetch policy definitions from hub-api
// 2. Subscribe to real-time policy updates via gRPC streaming
// 3. Register itself as a client in the hub-api service registry
//
// The client supports both gRPC (primary, hub-api:50051) and REST
// (fallback, hub-api:8080/api/v1/) communication modes. If the gRPC
// connection fails or is unavailable, it automatically falls back to
// REST API calls.
package api

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"

	log "github.com/sirupsen/logrus"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const (
	// defaultGRPCAddress is the default gRPC endpoint for hub-api.
	defaultGRPCAddress = "hub-api:50051"

	// defaultRESTBaseURL is the default REST API fallback URL.
	defaultRESTBaseURL = "http://hub-api:8080/api/v1"

	// defaultCacheTTL is the default policy cache TTL.
	defaultCacheTTL = 5 * time.Minute

	// reconnectInterval is the interval between gRPC reconnection attempts.
	reconnectInterval = 10 * time.Second

)

// Policy represents a network policy fetched from hub-api.
type Policy struct {
	// ID is the unique policy identifier.
	ID string `json:"id"`
	// Name is the human-readable policy name.
	Name string `json:"name"`
	// Priority determines evaluation order (lower = higher priority).
	Priority int `json:"priority"`
	// Action is the policy action (allow, deny, log).
	Action string `json:"action"`
	// Domains is the list of domain patterns this policy applies to.
	Domains []string `json:"domains,omitempty"`
	// Ports is the list of port ranges this policy applies to.
	Ports []string `json:"ports,omitempty"`
	// Protocols is the list of protocols (tcp, udp, icmp).
	Protocols []string `json:"protocols,omitempty"`
	// CIDRs is the list of IP CIDR ranges.
	CIDRs []string `json:"cidrs,omitempty"`
	// Users is the list of user IDs this policy applies to.
	Users []string `json:"users,omitempty"`
	// Groups is the list of group IDs this policy applies to.
	Groups []string `json:"groups,omitempty"`
	// Enabled indicates whether the policy is active.
	Enabled bool `json:"enabled"`
	// UpdatedAt is the last modification timestamp.
	UpdatedAt time.Time `json:"updated_at"`
}

// ClientRegistration represents hub-router registration data sent to hub-api.
type ClientRegistration struct {
	// RouterID is the unique identifier for this hub-router instance.
	RouterID string `json:"router_id"`
	// ClusterID is the cluster this router belongs to.
	ClusterID string `json:"cluster_id"`
	// Hostname is the router's hostname.
	Hostname string `json:"hostname"`
	// PublicIP is the router's public IP address.
	PublicIP string `json:"public_ip"`
	// WireGuardPort is the WireGuard listen port.
	WireGuardPort int `json:"wireguard_port"`
	// Capabilities lists the router's supported features.
	Capabilities []string `json:"capabilities"`
}

// PolicyUpdateCallback is invoked when policies are updated.
type PolicyUpdateCallback func(policies []Policy)

// HubAPIClient provides communication with the hub-api service.
// It uses gRPC as the primary transport and falls back to REST
// when gRPC is unavailable.
type HubAPIClient struct {
	// grpcAddr is the gRPC server address.
	grpcAddr string
	// restBaseURL is the REST API base URL for fallback.
	restBaseURL string

	// grpcConn is the gRPC client connection.
	grpcConn *grpc.ClientConn
	// grpcAvailable indicates whether gRPC is currently available.
	grpcAvailable bool

	// httpClient is used for REST API fallback calls.
	httpClient *http.Client

	// policyCache stores cached policies with TTL.
	policyCache     []Policy
	policyCacheTime time.Time
	cacheTTL        time.Duration

	// onPolicyUpdate is the callback for policy update notifications.
	onPolicyUpdate PolicyUpdateCallback

	// mu protects concurrent access to the client state.
	mu sync.RWMutex

	// stopCh signals background goroutines to stop.
	stopCh chan struct{}
}

// NewHubAPIClient creates a new client for communicating with hub-api.
//
// Parameters:
//   - grpcAddr: gRPC server address (e.g., "hub-api:50051"). Empty string uses default.
//   - restBaseURL: REST API base URL (e.g., "http://hub-api:8080/api/v1"). Empty string uses default.
func NewHubAPIClient(grpcAddr, restBaseURL string) *HubAPIClient {
	if grpcAddr == "" {
		grpcAddr = defaultGRPCAddress
	}
	if restBaseURL == "" {
		restBaseURL = defaultRESTBaseURL
	}

	return &HubAPIClient{
		grpcAddr:    grpcAddr,
		restBaseURL: restBaseURL,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
		cacheTTL: defaultCacheTTL,
		stopCh:   make(chan struct{}),
	}
}

// Connect establishes the gRPC connection to hub-api.
// If the connection fails, the client will fall back to REST and
// periodically retry the gRPC connection in the background.
func (c *HubAPIClient) Connect(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	conn, err := grpc.NewClient(c.grpcAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Warnf("gRPC connection to %s failed: %v (falling back to REST at %s)",
			c.grpcAddr, err, c.restBaseURL)
		c.grpcAvailable = false

		// Start background reconnection
		go c.reconnectLoop()
		return nil // Not an error - we fall back to REST
	}

	c.grpcConn = conn
	c.grpcAvailable = true
	log.Infof("Connected to hub-api via gRPC at %s", c.grpcAddr)

	return nil
}

// reconnectLoop periodically attempts to re-establish the gRPC connection.
func (c *HubAPIClient) reconnectLoop() {
	ticker := time.NewTicker(reconnectInterval)
	defer ticker.Stop()

	for {
		select {
		case <-c.stopCh:
			return
		case <-ticker.C:
			c.mu.Lock()
			if c.grpcAvailable {
				c.mu.Unlock()
				return
			}

			conn, err := grpc.NewClient(c.grpcAddr,
				grpc.WithTransportCredentials(insecure.NewCredentials()),
			)

			if err != nil {
				c.mu.Unlock()
				log.Debugf("gRPC reconnection to %s failed: %v", c.grpcAddr, err)
				continue
			}

			c.grpcConn = conn
			c.grpcAvailable = true
			c.mu.Unlock()
			log.Infof("Re-established gRPC connection to hub-api at %s", c.grpcAddr)
			return
		}
	}
}

// FetchPolicies retrieves the current policy set from hub-api.
// Uses gRPC if available, otherwise falls back to REST.
// Results are cached for cacheTTL duration.
func (c *HubAPIClient) FetchPolicies(ctx context.Context) ([]Policy, error) {
	c.mu.RLock()
	// Check cache
	if c.policyCache != nil && time.Since(c.policyCacheTime) < c.cacheTTL {
		policies := make([]Policy, len(c.policyCache))
		copy(policies, c.policyCache)
		c.mu.RUnlock()
		return policies, nil
	}
	grpcAvail := c.grpcAvailable
	c.mu.RUnlock()

	var policies []Policy
	var err error

	if grpcAvail {
		policies, err = c.fetchPoliciesGRPC(ctx)
		if err != nil {
			log.Warnf("gRPC FetchPolicies failed, falling back to REST: %v", err)
			policies, err = c.fetchPoliciesREST(ctx)
		}
	} else {
		policies, err = c.fetchPoliciesREST(ctx)
	}

	if err != nil {
		return nil, fmt.Errorf("failed to fetch policies: %w", err)
	}

	// Update cache
	c.mu.Lock()
	c.policyCache = policies
	c.policyCacheTime = time.Now()
	c.mu.Unlock()

	return policies, nil
}

// fetchPoliciesGRPC fetches policies via gRPC.
func (c *HubAPIClient) fetchPoliciesGRPC(ctx context.Context) ([]Policy, error) {
	// TODO: Implement using generated gRPC client stub:
	//
	//   client := pb.NewPolicyServiceClient(c.grpcConn)
	//   resp, err := client.ListPolicies(ctx, &pb.ListPoliciesRequest{})
	//   if err != nil { return nil, err }
	//
	//   var policies []Policy
	//   for _, p := range resp.Policies {
	//       policies = append(policies, Policy{
	//           ID:        p.Id,
	//           Name:      p.Name,
	//           Priority:  int(p.Priority),
	//           Action:    p.Action,
	//           Domains:   p.Domains,
	//           Ports:     p.Ports,
	//           Protocols: p.Protocols,
	//           CIDRs:     p.Cidrs,
	//           Users:     p.Users,
	//           Groups:    p.Groups,
	//           Enabled:   p.Enabled,
	//       })
	//   }
	//   return policies, nil

	return nil, fmt.Errorf("gRPC FetchPolicies not yet implemented")
}

// fetchPoliciesREST fetches policies via REST API as a fallback.
func (c *HubAPIClient) fetchPoliciesREST(ctx context.Context) ([]Policy, error) {
	url := fmt.Sprintf("%s/policies", c.restBaseURL)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("REST request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("REST API returned status %d: %s", resp.StatusCode, string(body))
	}

	var policies []Policy
	if err := json.NewDecoder(resp.Body).Decode(&policies); err != nil {
		return nil, fmt.Errorf("failed to decode policies: %w", err)
	}

	return policies, nil
}

// SubscribePolicyUpdates subscribes to real-time policy updates via gRPC streaming.
// When policies change on hub-api, the callback is invoked with the updated policy set.
//
// This method blocks until the context is cancelled or the stop channel is closed.
// If the gRPC stream disconnects, it automatically reconnects.
func (c *HubAPIClient) SubscribePolicyUpdates(ctx context.Context, callback PolicyUpdateCallback) error {
	c.mu.Lock()
	c.onPolicyUpdate = callback
	c.mu.Unlock()

	// TODO: Implement using gRPC streaming:
	//
	//   client := pb.NewPolicyServiceClient(c.grpcConn)
	//   stream, err := client.WatchPolicies(ctx, &pb.WatchPoliciesRequest{})
	//   if err != nil { return err }
	//
	//   for {
	//       update, err := stream.Recv()
	//       if err == io.EOF { break }
	//       if err != nil {
	//           log.Warnf("Policy stream error: %v, reconnecting...", err)
	//           time.Sleep(reconnectInterval)
	//           continue
	//       }
	//
	//       policies := convertPolicies(update.Policies)
	//       callback(policies)
	//
	//       // Update cache
	//       c.mu.Lock()
	//       c.policyCache = policies
	//       c.policyCacheTime = time.Now()
	//       c.mu.Unlock()
	//   }

	log.Info("Policy update subscription started (stub - polling fallback)")

	// Fallback: poll for updates periodically
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-c.stopCh:
			return nil
		case <-ticker.C:
			policies, err := c.FetchPolicies(ctx)
			if err != nil {
				log.Warnf("Policy poll failed: %v", err)
				continue
			}
			if callback != nil {
				callback(policies)
			}
		}
	}
}

// RegisterClient registers this hub-router instance with hub-api.
// This allows hub-api to track active routers and their capabilities.
func (c *HubAPIClient) RegisterClient(ctx context.Context, reg *ClientRegistration) error {
	c.mu.RLock()
	grpcAvail := c.grpcAvailable
	c.mu.RUnlock()

	if grpcAvail {
		err := c.registerClientGRPC(ctx, reg)
		if err != nil {
			log.Warnf("gRPC RegisterClient failed, falling back to REST: %v", err)
			return c.registerClientREST(ctx, reg)
		}
		return nil
	}

	return c.registerClientREST(ctx, reg)
}

// registerClientGRPC registers via gRPC.
func (c *HubAPIClient) registerClientGRPC(ctx context.Context, reg *ClientRegistration) error {
	// TODO: Implement using generated gRPC client stub:
	//
	//   client := pb.NewRouterServiceClient(c.grpcConn)
	//   _, err := client.Register(ctx, &pb.RegisterRouterRequest{
	//       RouterId:      reg.RouterID,
	//       ClusterId:     reg.ClusterID,
	//       Hostname:      reg.Hostname,
	//       PublicIp:      reg.PublicIP,
	//       WireguardPort: int32(reg.WireGuardPort),
	//       Capabilities:  reg.Capabilities,
	//   })
	//   return err

	return fmt.Errorf("gRPC RegisterClient not yet implemented")
}

// registerClientREST registers via REST API as a fallback.
func (c *HubAPIClient) registerClientREST(ctx context.Context, reg *ClientRegistration) error {
	url := fmt.Sprintf("%s/routers/register", c.restBaseURL)

	body, err := json.Marshal(reg)
	if err != nil {
		return fmt.Errorf("failed to marshal registration: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Body = io.NopCloser(io.Reader(
		// Use the serialized body
		jsonReader(body),
	))

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("REST request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("REST API returned status %d: %s", resp.StatusCode, string(respBody))
	}

	log.Infof("Registered hub-router %s with hub-api via REST", reg.RouterID)
	return nil
}

// Close gracefully shuts down the client and releases resources.
func (c *HubAPIClient) Close() error {
	close(c.stopCh)

	c.mu.Lock()
	defer c.mu.Unlock()

	if c.grpcConn != nil {
		if err := c.grpcConn.Close(); err != nil {
			return fmt.Errorf("failed to close gRPC connection: %w", err)
		}
	}

	log.Info("HubAPIClient closed")
	return nil
}

// jsonReader wraps a byte slice to implement io.Reader.
type jsonReaderType struct {
	data []byte
	pos  int
}

func jsonReader(data []byte) io.Reader {
	return &jsonReaderType{data: data}
}

func (r *jsonReaderType) Read(p []byte) (n int, err error) {
	if r.pos >= len(r.data) {
		return 0, io.EOF
	}
	n = copy(p, r.data[r.pos:])
	r.pos += n
	return n, nil
}
