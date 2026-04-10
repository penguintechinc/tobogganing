// Package sync provides the gRPC client for communication between the
// hub-policy and the hub-api service.
//
// The hub-policy uses this client to:
// 1. Fetch policy definitions from hub-api
// 2. Subscribe to real-time policy updates via gRPC streaming
// 3. Register itself as a policy controller in the hub-api service registry
//
// The client supports both gRPC (primary, hub-api:50051) and REST
// (fallback, hub-api:8080/api/v1/) communication modes. If the gRPC
// connection fails or is unavailable, it automatically falls back to
// REST API calls.
package sync

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

// PolicyUpdate represents a single policy update message received from the stream.
type PolicyUpdate struct {
	// Policies is the updated set of policies.
	Policies []Policy `json:"policies"`
	// Sequence is the monotonic sequence number for ordering.
	Sequence int64 `json:"sequence"`
}

// PolicyStream is the interface for consuming a gRPC policy update stream.
// It is satisfied by the generated gRPC client stream type and by mock
// implementations used in tests.
type PolicyStream interface {
	// Recv blocks until the next PolicyUpdate arrives, or an error occurs.
	// Returns io.EOF when the stream ends normally.
	Recv() (*PolicyUpdate, error)
}

// PolicyStreamFactory creates a PolicyStream for the given context.
// The factory is called each time the client (re-)connects to the stream.
// Injecting a custom factory in tests allows full control over stream behaviour.
type PolicyStreamFactory func(ctx context.Context) (PolicyStream, error)

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

// ControllerRegistration represents hub-policy registration data sent to hub-api.
type ControllerRegistration struct {
	// ControllerID is the unique identifier for this hub-policy instance.
	ControllerID string `json:"controller_id"`
	// ClusterID is the cluster this controller belongs to.
	ClusterID string `json:"cluster_id"`
	// Hostname is the controller's hostname.
	Hostname string `json:"hostname"`
	// PublicIP is the controller's public IP address.
	PublicIP string `json:"public_ip"`
	// Capabilities lists the controller's supported features.
	Capabilities []string `json:"capabilities"`
}

// PolicyUpdateCallback is invoked when policies are updated.
type PolicyUpdateCallback func(policies []Policy)

// grpcDialFunc is the signature of the function used to create a gRPC
// connection. Replacing it in tests allows simulating dial failures.
type grpcDialFunc func(target string, opts ...grpc.DialOption) (*grpc.ClientConn, error)

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

	// dialFn is the function used to create gRPC connections. If nil,
	// grpc.NewClient is used. Overriding this in tests enables dial-failure
	// simulation without requiring a real unreachable host.
	dialFn grpcDialFunc

	// streamFactory creates a PolicyStream when the client subscribes to updates.
	// If nil, the polling fallback is used. Injecting a non-nil factory enables
	// gRPC streaming and allows tests to supply mock streams.
	streamFactory PolicyStreamFactory

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

// dial creates a new gRPC connection using the injected dialFn if set,
// otherwise falls back to grpc.NewClient.
func (c *HubAPIClient) dial() (*grpc.ClientConn, error) {
	fn := c.dialFn
	if fn == nil {
		fn = grpc.NewClient
	}
	return fn(c.grpcAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
}

// SetStreamFactory sets the factory used to create gRPC policy streams.
// Call this before SubscribePolicyUpdates to enable streaming (rather than
// polling). Tests inject a mock factory here.
func (c *HubAPIClient) SetStreamFactory(f PolicyStreamFactory) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.streamFactory = f
}

// Connect establishes the gRPC connection to hub-api.
// If the connection fails, the client will fall back to REST and
// periodically retry the gRPC connection in the background.
func (c *HubAPIClient) Connect(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	conn, err := c.dial()
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
	c.reconnectLoopFast(reconnectInterval)
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

// SubscribePolicyUpdates subscribes to real-time policy updates.
//
// When a PolicyStreamFactory has been set (via SetStreamFactory), this method
// consumes the gRPC stream: each received PolicyUpdate triggers the callback
// and updates the local cache.  The method handles io.EOF (clean server-side
// close) and transient errors (logs a warning and returns), so callers can
// restart it if needed.
//
// When no factory is set, it falls back to periodic REST polling every 30s.
//
// The method blocks until the context is cancelled, the stop channel is closed,
// the stream reaches EOF, or a non-EOF stream error occurs.
func (c *HubAPIClient) SubscribePolicyUpdates(ctx context.Context, callback PolicyUpdateCallback) error {
	c.mu.Lock()
	c.onPolicyUpdate = callback
	factory := c.streamFactory
	c.mu.Unlock()

	if factory != nil {
		return c.subscribeViaStream(ctx, factory, callback)
	}

	return c.subscribeViaPoll(ctx, callback)
}

// subscribeViaStream consumes a gRPC PolicyStream, invoking callback on each update.
func (c *HubAPIClient) subscribeViaStream(ctx context.Context, factory PolicyStreamFactory, callback PolicyUpdateCallback) error {
	stream, err := factory(ctx)
	if err != nil {
		return fmt.Errorf("failed to open policy stream: %w", err)
	}

	for {
		// Honour context cancellation between Recv calls.
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-c.stopCh:
			return nil
		default:
		}

		update, recvErr := stream.Recv()
		if recvErr == io.EOF {
			log.Info("Policy stream closed by server (EOF)")
			return nil
		}
		if recvErr != nil {
			// Check if the error is due to context cancellation.
			if ctx.Err() != nil {
				return ctx.Err()
			}
			log.Warnf("Policy stream error: %v", recvErr)
			return fmt.Errorf("policy stream error: %w", recvErr)
		}

		policies := update.Policies

		// Update cache.
		c.mu.Lock()
		c.policyCache = policies
		c.policyCacheTime = time.Now()
		c.mu.Unlock()

		if callback != nil {
			callback(policies)
		}
	}
}

// subscribeViaPoll polls REST periodically when no gRPC stream factory is available.
func (c *HubAPIClient) subscribeViaPoll(ctx context.Context, callback PolicyUpdateCallback) error {
	log.Info("Policy update subscription started (stub - polling fallback)")
	return c.subscribeViaPollFast(ctx, callback, 30*time.Second)
}

// RegisterController registers this hub-policy instance with hub-api.
// This allows hub-api to track active policy controllers and their capabilities.
func (c *HubAPIClient) RegisterController(ctx context.Context, reg *ControllerRegistration) error {
	c.mu.RLock()
	grpcAvail := c.grpcAvailable
	c.mu.RUnlock()

	if grpcAvail {
		err := c.registerControllerGRPC(ctx, reg)
		if err != nil {
			log.Warnf("gRPC RegisterController failed, falling back to REST: %v", err)
			return c.registerControllerREST(ctx, reg)
		}
		return nil
	}

	return c.registerControllerREST(ctx, reg)
}

// registerControllerGRPC registers via gRPC.
func (c *HubAPIClient) registerControllerGRPC(ctx context.Context, reg *ControllerRegistration) error {
	// TODO: Implement using generated gRPC client stub:
	//
	//   client := pb.NewControllerServiceClient(c.grpcConn)
	//   _, err := client.RegisterController(ctx, &pb.RegisterControllerRequest{
	//       ControllerId: reg.ControllerID,
	//       ClusterId:    reg.ClusterID,
	//       Hostname:     reg.Hostname,
	//       PublicIp:     reg.PublicIP,
	//       Capabilities: reg.Capabilities,
	//   })
	//   return err

	return fmt.Errorf("gRPC RegisterController not yet implemented")
}

// registerControllerREST registers via REST API as a fallback.
func (c *HubAPIClient) registerControllerREST(ctx context.Context, reg *ControllerRegistration) error {
	url := fmt.Sprintf("%s/controllers/register", c.restBaseURL)

	body, err := json.Marshal(reg)
	if err != nil {
		return fmt.Errorf("failed to marshal registration: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, io.NopCloser(
		jsonReader(body),
	))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("REST request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("REST API returned status %d: %s", resp.StatusCode, string(respBody))
	}

	log.Infof("Registered hub-policy controller %s with hub-api via REST", reg.ControllerID)
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

// subscribeViaPollFast is like subscribeViaPoll but uses the provided interval
// instead of the hard-coded 30-second interval. It exists to allow tests to
// exercise the ticker path without waiting 30 seconds.
func (c *HubAPIClient) subscribeViaPollFast(ctx context.Context, callback PolicyUpdateCallback, interval time.Duration) error {
	ticker := time.NewTicker(interval)
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

// reconnectLoopFast is like reconnectLoop but uses the provided interval so
// tests can drive it quickly without waiting reconnectInterval (10 s).
func (c *HubAPIClient) reconnectLoopFast(interval time.Duration) {
	ticker := time.NewTicker(interval)
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

			conn, err := c.dial()

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
