// Package manager provides comprehensive integration with the Tobogganing Manager service
package manager

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
	"github.com/tobogganing/k8s-cni/pkg/discovery"
	"github.com/tobogganing/k8s-cni/pkg/policy"
)

// Client provides comprehensive integration with the Tobogganing Manager service
type Client struct {
	logger *logrus.Entry
	config *ClientConfiguration

	// HTTP client for REST API calls
	httpClient *http.Client
	baseURL    *url.URL

	// WebSocket connection for real-time communication
	wsConn     *websocket.Conn
	wsDialer   *websocket.Dialer
	wsMutex    sync.RWMutex
	wsReconnectCount uint64

	// Message handling
	messageHandlers map[string]MessageHandler
	pendingRequests map[string]chan *WebSocketMessage
	requestMutex    sync.RWMutex

	// Event queues and buffering
	eventQueue    chan interface{}
	metricQueue   chan interface{}

	// Background task management
	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup

	// Statistics and monitoring
	stats *Statistics
	statsMutex sync.RWMutex

	// Connection state
	connected        bool
	connectionMutex  sync.RWMutex
	lastHealthCheck  time.Time
}

// MessageHandler represents a WebSocket message handler function
type MessageHandler func(message *WebSocketMessage) error

// NewClient creates a new manager client
func NewClient(config *ClientConfiguration) (*Client, error) {
	if config == nil {
		return nil, fmt.Errorf("client configuration is required")
	}

	// Validate required configuration
	if config.ManagerURL == "" {
		return nil, fmt.Errorf("manager URL is required")
	}
	if config.APIKey == "" {
		return nil, fmt.Errorf("API key is required")
	}
	if config.ClusterID == "" {
		return nil, fmt.Errorf("cluster ID is required")
	}
	if config.NodeName == "" {
		return nil, fmt.Errorf("node name is required")
	}

	// Apply defaults
	if config.ConnectionTimeout == 0 {
		config.ConnectionTimeout = 30 * time.Second
	}
	if config.RequestTimeout == 0 {
		config.RequestTimeout = 10 * time.Second
	}
	if config.WSReconnectInterval == 0 {
		config.WSReconnectInterval = 5 * time.Second
	}
	if config.WSMaxReconnects == 0 {
		config.WSMaxReconnects = -1 // Infinite
	}
	if config.WSPingInterval == 0 {
		config.WSPingInterval = 30 * time.Second
	}
	if config.ReportingInterval == 0 {
		config.ReportingInterval = 60 * time.Second
	}
	if config.BatchSize == 0 {
		config.BatchSize = 100
	}
	if config.EventBufferSize == 0 {
		config.EventBufferSize = 1000
	}
	if config.MetricBufferSize == 0 {
		config.MetricBufferSize = 500
	}
	if config.MaxRetries == 0 {
		config.MaxRetries = 3
	}
	if config.InitialBackoff == 0 {
		config.InitialBackoff = 1 * time.Second
	}
	if config.MaxBackoff == 0 {
		config.MaxBackoff = 60 * time.Second
	}
	if config.BackoffMultiplier == 0 {
		config.BackoffMultiplier = 2.0
	}

	// Parse manager URL
	baseURL, err := url.Parse(config.ManagerURL)
	if err != nil {
		return nil, fmt.Errorf("invalid manager URL: %w", err)
	}

	// Create HTTP client
	transport := &http.Transport{}
	if config.TLSEnabled {
		tlsConfig := &tls.Config{
			InsecureSkipVerify: config.TLSSkipVerify,
		}

		if config.CertFile != "" && config.KeyFile != "" {
			cert, err := tls.LoadX509KeyPair(config.CertFile, config.KeyFile)
			if err != nil {
				return nil, fmt.Errorf("failed to load client certificates: %w", err)
			}
			tlsConfig.Certificates = []tls.Certificate{cert}
		}

		transport.TLSClientConfig = tlsConfig
	}

	httpClient := &http.Client{
		Timeout:   config.RequestTimeout,
		Transport: transport,
	}

	// Create WebSocket dialer
	wsDialer := &websocket.Dialer{
		HandshakeTimeout: config.ConnectionTimeout,
		TLSClientConfig:  transport.TLSClientConfig,
	}

	logger := logrus.WithFields(logrus.Fields{
		"component":  "manager-client",
		"cluster_id": config.ClusterID,
		"node_name":  config.NodeName,
	})

	ctx, cancel := context.WithCancel(context.Background())

	client := &Client{
		logger:     logger,
		config:     config,
		httpClient: httpClient,
		baseURL:    baseURL,
		wsDialer:   wsDialer,
		ctx:        ctx,
		cancel:     cancel,

		messageHandlers: make(map[string]MessageHandler),
		pendingRequests: make(map[string]chan *WebSocketMessage),
		eventQueue:      make(chan interface{}, config.EventBufferSize),
		metricQueue:     make(chan interface{}, config.MetricBufferSize),

		stats: &Statistics{
			Connection: ConnectionStatus{
				WebSocketEnabled: config.EnableWebSocket,
			},
			LastUpdate: time.Now(),
		},
	}

	// Register default message handlers
	client.registerDefaultHandlers()

	return client, nil
}

// Start initializes the client and starts background tasks
func (c *Client) Start() error {
	c.logger.Info("starting manager client")

	// Test initial connection
	if err := c.testConnection(); err != nil {
		return fmt.Errorf("initial connection test failed: %w", err)
	}

	// Start WebSocket connection if enabled
	if c.config.EnableWebSocket {
		c.wg.Add(1)
		go c.websocketManager()
	}

	// Start event processor
	c.wg.Add(1)
	go c.eventProcessor()

	// Start metric processor
	c.wg.Add(1)
	go c.metricProcessor()

	// Start health reporter
	if c.config.EnableHealthReporting {
		c.wg.Add(1)
		go c.healthReporter()
	}

	// Start policy sync
	if c.config.EnablePolicySync {
		c.wg.Add(1)
		go c.policySync()
	}

	c.logger.Info("manager client started successfully")
	return nil
}

// Stop shuts down the client and cleans up resources
func (c *Client) Stop() error {
	c.logger.Info("stopping manager client")

	// Cancel context to stop all goroutines
	c.cancel()

	// Close WebSocket connection
	c.wsMutex.Lock()
	if c.wsConn != nil {
		c.wsConn.Close()
	}
	c.wsMutex.Unlock()

	// Wait for all goroutines to finish
	c.wg.Wait()

	// Close queues
	close(c.eventQueue)
	close(c.metricQueue)

	c.logger.Info("manager client stopped")
	return nil
}

// RegisterPod registers a pod with the manager
func (c *Client) RegisterPod(ctx context.Context, req *PodRegistrationRequest) (*PodRegistrationResponse, error) {
	c.logger.WithFields(logrus.Fields{
		"pod_name":  req.PodName,
		"namespace": req.Namespace,
		"pod_ip":    req.PodIP,
	}).Debug("registering pod with manager")

	// Use WebSocket if available, otherwise fall back to HTTP
	if c.isWebSocketConnected() {
		return c.registerPodWebSocket(ctx, req)
	}

	return c.registerPodHTTP(ctx, req)
}

// DeregisterPod deregisters a pod from the manager
func (c *Client) DeregisterPod(ctx context.Context, namespace, podName, podUID string) error {
	c.logger.WithFields(logrus.Fields{
		"pod_name":  podName,
		"namespace": namespace,
		"pod_uid":   podUID,
	}).Debug("deregistering pod from manager")

	req := map[string]interface{}{
		"podName":   podName,
		"podUID":    podUID,
		"namespace": namespace,
		"clusterID": c.config.ClusterID,
		"nodeName":  c.config.NodeName,
	}

	// Use WebSocket if available, otherwise fall back to HTTP
	if c.isWebSocketConnected() {
		return c.deregisterPodWebSocket(ctx, req)
	}

	return c.deregisterPodHTTP(ctx, req)
}

// SyncPolicies synchronizes network policies from the manager
func (c *Client) SyncPolicies(ctx context.Context) ([]*policy.NetworkPolicy, error) {
	c.logger.Debug("syncing policies from manager")

	endpoint := fmt.Sprintf("/api/v1/clusters/%s/nodes/%s/policies", c.config.ClusterID, c.config.NodeName)
	
	req, err := c.createHTTPRequest(ctx, "GET", endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.statsMutex.Lock()
		c.stats.RequestFailures++
		c.statsMutex.Unlock()
		return nil, fmt.Errorf("failed to sync policies: %w", err)
	}
	defer resp.Body.Close()

	c.statsMutex.Lock()
	c.stats.RequestsSent++
	c.stats.ResponsesReceived++
	c.stats.PolicySyncCount++
	c.statsMutex.Unlock()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("policy sync failed with status %d: %s", resp.StatusCode, string(body))
	}

	var apiResp APIResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if !apiResp.Success {
		return nil, fmt.Errorf("policy sync failed: %s", apiResp.Error)
	}

	// Convert response data to network policies
	var policies []*policy.NetworkPolicy
	if policiesData, ok := apiResp.Data.([]interface{}); ok {
		for _, policyData := range policiesData {
			// Convert policy data to NetworkPolicy struct
			// This is a simplified conversion - in practice, you'd need proper type conversion
			policyBytes, _ := json.Marshal(policyData)
			var networkPolicy policy.NetworkPolicy
			if err := json.Unmarshal(policyBytes, &networkPolicy); err == nil {
				policies = append(policies, &networkPolicy)
			}
		}
	}

	c.logger.WithField("policy_count", len(policies)).Debug("synced policies from manager")
	return policies, nil
}

// ReportStatistics reports statistics to the manager
func (c *Client) ReportStatistics(ctx context.Context, stats *policy.PolicyStatistics) error {
	c.logger.Debug("reporting statistics to manager")

	// Create statistics report
	report := map[string]interface{}{
		"clusterID":  c.config.ClusterID,
		"nodeName":   c.config.NodeName,
		"timestamp":  time.Now(),
		"statistics": stats,
	}

	// Use WebSocket if available, otherwise fall back to HTTP
	if c.isWebSocketConnected() {
		return c.reportStatisticsWebSocket(ctx, report)
	}

	return c.reportStatisticsHTTP(ctx, report)
}

// ReportTraffic reports traffic statistics to the manager
func (c *Client) ReportTraffic(ctx context.Context, report *TrafficReport) error {
	c.logger.Debug("reporting traffic statistics to manager")

	// Enqueue the report for background processing
	select {
	case c.metricQueue <- report:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	default:
		c.logger.Warn("metric queue full, dropping traffic report")
		return fmt.Errorf("metric queue full")
	}
}

// ReportHealth reports health status to the manager
func (c *Client) ReportHealth(ctx context.Context, report *HealthReport) error {
	c.logger.Debug("reporting health status to manager")

	// Enqueue the report for background processing
	select {
	case c.eventQueue <- report:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	default:
		c.logger.Warn("event queue full, dropping health report")
		return fmt.Errorf("event queue full")
	}
}

// GetPodInventory retrieves pod inventory from the manager
func (c *Client) GetPodInventory(ctx context.Context) ([]*discovery.PodInfo, error) {
	c.logger.Debug("getting pod inventory from manager")

	endpoint := fmt.Sprintf("/api/v1/clusters/%s/nodes/%s/pods", c.config.ClusterID, c.config.NodeName)
	
	req, err := c.createHTTPRequest(ctx, "GET", endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.statsMutex.Lock()
		c.stats.RequestFailures++
		c.statsMutex.Unlock()
		return nil, fmt.Errorf("failed to get pod inventory: %w", err)
	}
	defer resp.Body.Close()

	c.statsMutex.Lock()
	c.stats.RequestsSent++
	c.stats.ResponsesReceived++
	c.statsMutex.Unlock()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("pod inventory request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var apiResp APIResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if !apiResp.Success {
		return nil, fmt.Errorf("pod inventory request failed: %s", apiResp.Error)
	}

	// Convert response data to pod info
	var pods []*discovery.PodInfo
	if podsData, ok := apiResp.Data.([]interface{}); ok {
		for _, podData := range podsData {
			// Convert pod data to PodInfo struct
			podBytes, _ := json.Marshal(podData)
			var podInfo discovery.PodInfo
			if err := json.Unmarshal(podBytes, &podInfo); err == nil {
				pods = append(pods, &podInfo)
			}
		}
	}

	c.logger.WithField("pod_count", len(pods)).Debug("retrieved pod inventory from manager")
	return pods, nil
}

// GetStats returns current client statistics
func (c *Client) GetStats() *Statistics {
	c.statsMutex.RLock()
	defer c.statsMutex.RUnlock()

	// Create a copy to avoid race conditions
	stats := *c.stats
	return &stats
}

// IsConnected returns whether the client is connected to the manager
func (c *Client) IsConnected() bool {
	c.connectionMutex.RLock()
	defer c.connectionMutex.RUnlock()
	return c.connected
}

// AddMessageHandler adds a WebSocket message handler
func (c *Client) AddMessageHandler(messageType string, handler MessageHandler) {
	c.requestMutex.Lock()
	defer c.requestMutex.Unlock()

	c.messageHandlers[messageType] = handler
	c.logger.WithField("message_type", messageType).Debug("added message handler")
}

// HTTP implementation methods

func (c *Client) registerPodHTTP(ctx context.Context, req *PodRegistrationRequest) (*PodRegistrationResponse, error) {
	endpoint := fmt.Sprintf("/api/v1/clusters/%s/nodes/%s/pods/register", c.config.ClusterID, c.config.NodeName)
	
	httpReq, err := c.createHTTPRequest(ctx, "POST", endpoint, req)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		c.statsMutex.Lock()
		c.stats.RequestFailures++
		c.stats.RegistrationFailures++
		c.statsMutex.Unlock()
		return nil, fmt.Errorf("failed to register pod: %w", err)
	}
	defer resp.Body.Close()

	c.statsMutex.Lock()
	c.stats.RequestsSent++
	c.stats.ResponsesReceived++
	if resp.StatusCode == http.StatusOK {
		c.stats.PodsRegistered++
	} else {
		c.stats.RegistrationFailures++
	}
	c.statsMutex.Unlock()

	var regResp PodRegistrationResponse
	if err := json.NewDecoder(resp.Body).Decode(&regResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("pod registration failed: %s", regResp.Message)
	}

	return &regResp, nil
}

func (c *Client) deregisterPodHTTP(ctx context.Context, req map[string]interface{}) error {
	endpoint := fmt.Sprintf("/api/v1/clusters/%s/nodes/%s/pods/deregister", c.config.ClusterID, c.config.NodeName)
	
	httpReq, err := c.createHTTPRequest(ctx, "POST", endpoint, req)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		c.statsMutex.Lock()
		c.stats.RequestFailures++
		c.statsMutex.Unlock()
		return fmt.Errorf("failed to deregister pod: %w", err)
	}
	defer resp.Body.Close()

	c.statsMutex.Lock()
	c.stats.RequestsSent++
	c.stats.ResponsesReceived++
	if resp.StatusCode == http.StatusOK {
		c.stats.PodsDeregistered++
	}
	c.statsMutex.Unlock()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("pod deregistration failed with status %d: %s", resp.StatusCode, string(body))
	}

	return nil
}

func (c *Client) reportStatisticsHTTP(ctx context.Context, stats map[string]interface{}) error {
	endpoint := fmt.Sprintf("/api/v1/clusters/%s/nodes/%s/statistics", c.config.ClusterID, c.config.NodeName)
	
	req, err := c.createHTTPRequest(ctx, "POST", endpoint, stats)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		c.statsMutex.Lock()
		c.stats.RequestFailures++
		c.statsMutex.Unlock()
		return fmt.Errorf("failed to report statistics: %w", err)
	}
	defer resp.Body.Close()

	c.statsMutex.Lock()
	c.stats.RequestsSent++
	c.stats.ResponsesReceived++
	c.statsMutex.Unlock()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("statistics reporting failed with status %d: %s", resp.StatusCode, string(body))
	}

	return nil
}

func (c *Client) createHTTPRequest(ctx context.Context, method, endpoint string, body interface{}) (*http.Request, error) {
	url := c.baseURL.ResolveReference(&url.URL{Path: endpoint})

	var reqBody io.Reader
	if body != nil {
		jsonBody, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		reqBody = bytes.NewReader(jsonBody)
	}

	req, err := http.NewRequestWithContext(ctx, method, url.String(), reqBody)
	if err != nil {
		return nil, err
	}

	// Add authentication header
	req.Header.Set("Authorization", "Bearer "+c.config.APIKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "tobogganing-cni/1.0")
	req.Header.Set("X-Cluster-ID", c.config.ClusterID)
	req.Header.Set("X-Node-Name", c.config.NodeName)

	return req, nil
}

func (c *Client) testConnection() error {
	ctx, cancel := context.WithTimeout(context.Background(), c.config.ConnectionTimeout)
	defer cancel()

	req, err := c.createHTTPRequest(ctx, "GET", "/api/v1/health", nil)
	if err != nil {
		return fmt.Errorf("failed to create health check request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("health check request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("health check failed with status %d", resp.StatusCode)
	}

	c.connectionMutex.Lock()
	c.connected = true
	c.stats.Connection.Connected = true
	c.stats.Connection.LastConnected = time.Now()
	c.stats.Connection.ConnectionCount++
	c.connectionMutex.Unlock()

	c.logger.Debug("connection test successful")
	return nil
}

// WebSocket implementation methods (simplified for brevity)

func (c *Client) isWebSocketConnected() bool {
	c.wsMutex.RLock()
	defer c.wsMutex.RUnlock()
	return c.wsConn != nil
}

func (c *Client) registerPodWebSocket(ctx context.Context, req *PodRegistrationRequest) (*PodRegistrationResponse, error) {
	msg := &WebSocketMessage{
		Type:      MessageTypePodRegistration,
		ID:        c.generateMessageID(),
		Timestamp: time.Now(),
		Data:      req,
	}

	respMsg, err := c.sendWebSocketMessage(ctx, msg)
	if err != nil {
		return nil, err
	}

	var resp PodRegistrationResponse
	if err := c.convertMessageData(respMsg.Data, &resp); err != nil {
		return nil, fmt.Errorf("failed to convert response data: %w", err)
	}

	return &resp, nil
}

func (c *Client) deregisterPodWebSocket(ctx context.Context, req map[string]interface{}) error {
	msg := &WebSocketMessage{
		Type:      MessageTypePodDeregistration,
		ID:        c.generateMessageID(),
		Timestamp: time.Now(),
		Data:      req,
	}

	_, err := c.sendWebSocketMessage(ctx, msg)
	return err
}

func (c *Client) reportStatisticsWebSocket(ctx context.Context, stats map[string]interface{}) error {
	msg := &WebSocketMessage{
		Type:      "statistics_report",
		ID:        c.generateMessageID(),
		Timestamp: time.Now(),
		Data:      stats,
	}

	_, err := c.sendWebSocketMessage(ctx, msg)
	return err
}

func (c *Client) sendWebSocketMessage(ctx context.Context, msg *WebSocketMessage) (*WebSocketMessage, error) {
	// Create response channel
	respChan := make(chan *WebSocketMessage, 1)
	
	c.requestMutex.Lock()
	c.pendingRequests[msg.ID] = respChan
	c.requestMutex.Unlock()

	defer func() {
		c.requestMutex.Lock()
		delete(c.pendingRequests, msg.ID)
		close(respChan)
		c.requestMutex.Unlock()
	}()

	// Send message
	c.wsMutex.Lock()
	if c.wsConn == nil {
		c.wsMutex.Unlock()
		return nil, fmt.Errorf("WebSocket not connected")
	}

	err := c.wsConn.WriteJSON(msg)
	c.wsMutex.Unlock()

	if err != nil {
		return nil, fmt.Errorf("failed to send WebSocket message: %w", err)
	}

	// Wait for response
	select {
	case resp := <-respChan:
		return resp, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-time.After(c.config.RequestTimeout):
		return nil, fmt.Errorf("WebSocket request timeout")
	}
}

// Background task implementations

func (c *Client) websocketManager() {
	defer c.wg.Done()
	
	reconnectDelay := c.config.WSReconnectInterval
	reconnectCount := 0

	for {
		select {
		case <-c.ctx.Done():
			return
		default:
		}

		// Connect to WebSocket
		err := c.connectWebSocket()
		if err != nil {
			c.logger.WithError(err).Error("failed to connect WebSocket")
			
			// Check reconnect limits
			if c.config.WSMaxReconnects > 0 && reconnectCount >= c.config.WSMaxReconnects {
				c.logger.Error("maximum WebSocket reconnect attempts reached")
				return
			}
			
			reconnectCount++
			
			// Wait before reconnecting
			select {
			case <-c.ctx.Done():
				return
			case <-time.After(reconnectDelay):
			}
			
			// Exponential backoff
			if reconnectDelay < c.config.MaxBackoff {
				reconnectDelay = time.Duration(float64(reconnectDelay) * c.config.BackoffMultiplier)
			}
			continue
		}

		// Reset reconnect parameters on successful connection
		reconnectCount = 0
		reconnectDelay = c.config.WSReconnectInterval

		// Handle WebSocket connection
		c.handleWebSocketConnection()

		// Connection closed, attempt to reconnect
		c.logger.Info("WebSocket connection closed, attempting to reconnect")
	}
}

func (c *Client) connectWebSocket() error {
	// Construct WebSocket URL
	wsURL := *c.baseURL
	if wsURL.Scheme == "https" {
		wsURL.Scheme = "wss"
	} else {
		wsURL.Scheme = "ws"
	}
	wsURL.Path = "/api/v1/ws"

	// Add authentication
	query := wsURL.Query()
	query.Set("token", c.config.APIKey)
	query.Set("cluster_id", c.config.ClusterID)
	query.Set("node_name", c.config.NodeName)
	wsURL.RawQuery = query.Encode()

	c.logger.WithField("url", wsURL.String()).Debug("connecting to WebSocket")

	conn, _, err := c.wsDialer.Dial(wsURL.String(), nil)
	if err != nil {
		return fmt.Errorf("WebSocket dial failed: %w", err)
	}

	c.wsMutex.Lock()
	c.wsConn = conn
	c.wsMutex.Unlock()

	c.connectionMutex.Lock()
	c.stats.Connection.LastConnected = time.Now()
	c.stats.Connection.ReconnectCount++
	c.connectionMutex.Unlock()

	c.logger.Info("WebSocket connected successfully")
	return nil
}

func (c *Client) handleWebSocketConnection() {
	// Start ping/pong handler
	go c.pingHandler()

	// Message reading loop
	for {
		var msg WebSocketMessage
		err := c.wsConn.ReadJSON(&msg)
		if err != nil {
			if websocket.IsCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				c.logger.Debug("WebSocket connection closed")
			} else {
				c.logger.WithError(err).Error("WebSocket read error")
			}
			break
		}

		// Handle the message
		c.handleWebSocketMessage(&msg)
	}

	// Clean up connection
	c.wsMutex.Lock()
	if c.wsConn != nil {
		c.wsConn.Close()
		c.wsConn = nil
	}
	c.wsMutex.Unlock()

	c.connectionMutex.Lock()
	c.stats.Connection.LastDisconnected = time.Now()
	c.connectionMutex.Unlock()
}

func (c *Client) handleWebSocketMessage(msg *WebSocketMessage) {
	c.logger.WithFields(logrus.Fields{
		"type": msg.Type,
		"id":   msg.ID,
	}).Debug("received WebSocket message")

	// Handle response messages
	if msg.ID != "" {
		c.requestMutex.RLock()
		if respChan, exists := c.pendingRequests[msg.ID]; exists {
			select {
			case respChan <- msg:
			default:
			}
		}
		c.requestMutex.RUnlock()
	}

	// Handle message types
	c.requestMutex.RLock()
	if handler, exists := c.messageHandlers[msg.Type]; exists {
		c.requestMutex.RUnlock()
		if err := handler(msg); err != nil {
			c.logger.WithError(err).Error("message handler failed")
		}
	} else {
		c.requestMutex.RUnlock()
	}
}

func (c *Client) pingHandler() {
	ticker := time.NewTicker(c.config.WSPingInterval)
	defer ticker.Stop()

	for {
		select {
		case <-c.ctx.Done():
			return
		case <-ticker.C:
			c.wsMutex.Lock()
			if c.wsConn != nil {
				err := c.wsConn.WriteMessage(websocket.PingMessage, nil)
				if err != nil {
					c.logger.WithError(err).Debug("WebSocket ping failed")
				}
			}
			c.wsMutex.Unlock()
		}
	}
}

func (c *Client) eventProcessor() {
	defer c.wg.Done()

	for {
		select {
		case <-c.ctx.Done():
			return
		case event := <-c.eventQueue:
			c.processEvent(event)
		}
	}
}

func (c *Client) processEvent(event interface{}) {
	switch e := event.(type) {
	case *HealthReport:
		ctx, cancel := context.WithTimeout(c.ctx, c.config.RequestTimeout)
		if err := c.sendHealthReport(ctx, e); err != nil {
			c.logger.WithError(err).Error("failed to send health report")
		}
		cancel()
	default:
		c.logger.WithField("type", fmt.Sprintf("%T", event)).Warn("unknown event type")
	}
}

func (c *Client) metricProcessor() {
	defer c.wg.Done()

	for {
		select {
		case <-c.ctx.Done():
			return
		case metric := <-c.metricQueue:
			c.processMetric(metric)
		}
	}
}

func (c *Client) processMetric(metric interface{}) {
	switch m := metric.(type) {
	case *TrafficReport:
		ctx, cancel := context.WithTimeout(c.ctx, c.config.RequestTimeout)
		if err := c.sendTrafficReport(ctx, m); err != nil {
			c.logger.WithError(err).Error("failed to send traffic report")
		}
		cancel()
	default:
		c.logger.WithField("type", fmt.Sprintf("%T", metric)).Warn("unknown metric type")
	}
}

func (c *Client) healthReporter() {
	defer c.wg.Done()

	ticker := time.NewTicker(c.config.ReportingInterval)
	defer ticker.Stop()

	for {
		select {
		case <-c.ctx.Done():
			return
		case <-ticker.C:
			report := c.generateHealthReport()
			c.ReportHealth(c.ctx, report)
		}
	}
}

func (c *Client) policySync() {
	defer c.wg.Done()

	var interval time.Duration
	if c.config.PolicySyncInterval > 0 {
		interval = c.config.PolicySyncInterval
	} else {
		interval = 5 * time.Minute
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-c.ctx.Done():
			return
		case <-ticker.C:
			if _, err := c.SyncPolicies(c.ctx); err != nil {
				c.logger.WithError(err).Error("policy sync failed")
			}
		}
	}
}

func (c *Client) sendHealthReport(ctx context.Context, report *HealthReport) error {
	if c.isWebSocketConnected() {
		msg := &WebSocketMessage{
			Type:      MessageTypeHealthReport,
			ID:        c.generateMessageID(),
			Timestamp: time.Now(),
			Data:      report,
		}
		_, err := c.sendWebSocketMessage(ctx, msg)
		return err
	}

	// Fall back to HTTP
	endpoint := fmt.Sprintf("/api/v1/clusters/%s/nodes/%s/health", c.config.ClusterID, c.config.NodeName)
	req, err := c.createHTTPRequest(ctx, "POST", endpoint, report)
	if err != nil {
		return err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	c.statsMutex.Lock()
	c.stats.HealthReportsSent++
	c.statsMutex.Unlock()

	return nil
}

func (c *Client) sendTrafficReport(ctx context.Context, report *TrafficReport) error {
	if c.isWebSocketConnected() {
		msg := &WebSocketMessage{
			Type:      MessageTypeTrafficReport,
			ID:        c.generateMessageID(),
			Timestamp: time.Now(),
			Data:      report,
		}
		_, err := c.sendWebSocketMessage(ctx, msg)
		return err
	}

	// Fall back to HTTP
	endpoint := fmt.Sprintf("/api/v1/clusters/%s/nodes/%s/traffic", c.config.ClusterID, c.config.NodeName)
	req, err := c.createHTTPRequest(ctx, "POST", endpoint, report)
	if err != nil {
		return err
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	c.statsMutex.Lock()
	c.stats.TrafficReportsSent++
	c.statsMutex.Unlock()

	return nil
}

// Helper methods

func (c *Client) registerDefaultHandlers() {
	c.messageHandlers[MessageTypePing] = c.handlePing
	c.messageHandlers[MessageTypePong] = c.handlePong
	c.messageHandlers[MessageTypeConfigUpdate] = c.handleConfigUpdate
	c.messageHandlers[MessageTypePolicySync] = c.handlePolicySync
}

func (c *Client) handlePing(msg *WebSocketMessage) error {
	pong := &WebSocketMessage{
		Type:      MessageTypePong,
		ID:        msg.ID,
		Timestamp: time.Now(),
	}

	c.wsMutex.Lock()
	if c.wsConn != nil {
		err := c.wsConn.WriteJSON(pong)
		c.wsMutex.Unlock()
		return err
	}
	c.wsMutex.Unlock()
	return nil
}

func (c *Client) handlePong(msg *WebSocketMessage) error {
	// Update latency calculation
	if msg.Timestamp.IsZero() {
		return nil
	}

	latency := time.Since(msg.Timestamp)
	c.connectionMutex.Lock()
	c.stats.Connection.Latency = latency
	c.connectionMutex.Unlock()

	return nil
}

func (c *Client) handleConfigUpdate(msg *WebSocketMessage) error {
	c.logger.Info("received configuration update from manager")
	// Handle configuration updates
	return nil
}

func (c *Client) handlePolicySync(msg *WebSocketMessage) error {
	c.logger.Info("received policy sync request from manager")
	// Trigger policy sync
	go func() {
		if _, err := c.SyncPolicies(c.ctx); err != nil {
			c.logger.WithError(err).Error("policy sync failed")
		}
	}()
	return nil
}

func (c *Client) generateMessageID() string {
	return fmt.Sprintf("%d-%s", time.Now().UnixNano(), c.config.NodeName)
}

func (c *Client) convertMessageData(data interface{}, target interface{}) error {
	jsonData, err := json.Marshal(data)
	if err != nil {
		return err
	}
	return json.Unmarshal(jsonData, target)
}

func (c *Client) generateHealthReport() *HealthReport {
	return &HealthReport{
		NodeName:      c.config.NodeName,
		ClusterID:     c.config.ClusterID,
		Timestamp:     time.Now(),
		OverallStatus: "healthy",
		CNIHealth: ComponentHealth{
			Status:    "healthy",
			LastCheck: time.Now(),
			Uptime:    time.Since(c.stats.Connection.LastConnected),
		},
		ResourceHealth: ResourceHealth{
			CPUUsage:    0.0, // Would be populated with actual metrics
			MemoryUsage: 0,
		},
		Performance: PerformanceMetrics{
			PacketsPerSecond: 0.0,
		},
	}
}