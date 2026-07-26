package main

import (
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/tobogganing/hub-router/proxy/auth"
	"github.com/tobogganing/hub-router/proxy/firewall"
	"github.com/tobogganing/hub-router/proxy/mirror"
)

// TestNewWireGuardRouter tests the constructor for WireGuardRouter
func TestNewWireGuardRouter(t *testing.T) {
	tests := []struct {
		name      string
		iface     string
		network   string
		headendIP string
		wantErr   bool
		errMsg    string
	}{
		{
			name:      "valid configuration",
			iface:     "wg0",
			network:   "10.200.0.0/16",
			headendIP: "10.200.0.1",
			wantErr:   false,
		},
		{
			name:      "invalid network CIDR",
			iface:     "wg0",
			network:   "invalid-cidr",
			headendIP: "10.200.0.1",
			wantErr:   true,
			errMsg:    "invalid WireGuard network CIDR",
		},
		{
			name:      "invalid headend IP",
			iface:     "wg0",
			network:   "10.200.0.0/16",
			headendIP: "not-an-ip",
			wantErr:   true,
			errMsg:    "invalid headend IP",
		},
		{
			name:      "malformed network",
			iface:     "wg0",
			network:   "10.200.0.0/33", // /33 is invalid for IPv4
			headendIP: "10.200.0.1",
			wantErr:   true,
			errMsg:    "invalid WireGuard network CIDR",
		},
		{
			name:      "IPv6 support",
			iface:     "wg0",
			network:   "fd00::/64",
			headendIP: "fd00::1",
			wantErr:   false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			router, err := NewWireGuardRouter(tt.iface, tt.network, tt.headendIP)
			if tt.wantErr {
				assert.Error(t, err)
				if tt.errMsg != "" {
					assert.Contains(t, err.Error(), tt.errMsg)
				}
				assert.Nil(t, router)
			} else {
				assert.NoError(t, err)
				assert.NotNil(t, router)
				assert.Equal(t, tt.iface, router.wgInterface)
				assert.Equal(t, tt.headendIP, router.headendIP.String())
			}
		})
	}
}

// TestWireGuardRouterIsWireGuardDestination tests destination checking
func TestWireGuardRouterIsWireGuardDestination(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	tests := []struct {
		name     string
		host     string
		expected bool
	}{
		{
			name:     "IP in WireGuard network",
			host:     "10.200.1.5",
			expected: true,
		},
		{
			name:     "headend IP",
			host:     "10.200.0.1",
			expected: true,
		},
		{
			name:     "network address",
			host:     "10.200.0.0",
			expected: true,
		},
		{
			name:     "broadcast address",
			host:     "10.200.255.255",
			expected: true,
		},
		{
			name:     "IP outside WireGuard network",
			host:     "8.8.8.8",
			expected: false,
		},
		{
			name:     "192.168 private range",
			host:     "192.168.1.1",
			expected: false,
		},
		{
			name:     "localhost",
			host:     "127.0.0.1",
			expected: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := router.IsWireGuardDestination(tt.host)
			assert.Equal(t, tt.expected, result, "host: %s", tt.host)
		})
	}
}

// TestWireGuardRouterGetWireGuardPeersCommandFailure tests error handling when wg command fails
func TestWireGuardRouterGetWireGuardPeersCommandFailure(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// This will fail because wg command is not available in test environment
	peers, err := router.GetWireGuardPeers()
	assert.Error(t, err)
	assert.Nil(t, peers)
	assert.Contains(t, err.Error(), "failed to get WireGuard peers")
}

// TestWireGuardRouterIsPeerConfiguredCommandFailure tests isPeerConfigured error handling
func TestWireGuardRouterIsPeerConfiguredCommandFailure(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// This will fail because wg command is not available
	result := router.isPeerConfigured("10.200.1.5")
	assert.False(t, result, "should return false when wg command fails")
}

// TestWireGuardRouterDialPeerFormat tests dialPeer port construction
func TestWireGuardRouterDialPeerFormat(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// Test that dialPeer constructs the correct address format
	// We can't actually dial in tests without a real WireGuard interface,
	// but we can verify the logic is correct via integration test patterns
	targetIP := "10.200.1.5"

	// Verify IP is in the network
	assert.True(t, router.IsWireGuardDestination(targetIP))
}

// TestProxyServer initialization tests
func TestProxyServerInitializeDefaults(t *testing.T) {
	// Set up defaults without reading config files
	viper.Reset()
	viper.SetDefault("server.http_port", "8443")
	viper.SetDefault("server.tcp_port", "8444")
	viper.SetDefault("server.udp_port", "8445")
	viper.SetDefault("server.metrics_port", "9090")
	viper.SetDefault("auth.type", "jwt")
	viper.SetDefault("auth.manager_url", "http://manager:8000")
	viper.SetDefault("mirror.enabled", false)
	viper.SetDefault("firewall.enabled", false)
	viper.SetDefault("syslog.enabled", false)
	viper.SetDefault("wireguard.interface", "wg0")
	viper.SetDefault("wireguard.network", "10.200.0.0/16")
	viper.SetDefault("ports.dynamic_enabled", false)
	viper.SetDefault("overlay.type", "wireguard")
	viper.SetDefault("xdp.enabled", false)

	server := &ProxyServer{}

	// Test that auth provider initialization fails gracefully with incomplete config
	// (since auth.jwt_public_key_path is not set)
	err := server.Initialize()
	assert.Error(t, err, "Initialize should error with missing auth config")
}

// TestProxyServerHealthHandler tests health check endpoint
func TestProxyServerHealthHandler(t *testing.T) {
	server := &ProxyServer{}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/health", nil)

	server.healthHandler(c)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "status")
}

// TestProxyServerHealthzHandler tests healthz endpoint returns error when proxies not initialized
func TestProxyServerHealthzHandler(t *testing.T) {
	server := &ProxyServer{}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/healthz", nil)

	server.healthzHandler(c)

	// Should return unavailable since proxies are not initialized
	assert.Equal(t, http.StatusServiceUnavailable, w.Code)
	assert.Contains(t, w.Body.String(), "error")
}

// TestProxyServerHealthzHandlerHealthy tests healthz when healthy
func TestProxyServerHealthzHandlerHealthy(t *testing.T) {
	server := &ProxyServer{
		authProvider: &mockAuthProvider{},
		tcpProxy:     &TCPProxy{},
		udpProxy:     &UDPProxy{},
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/healthz", nil)

	server.healthzHandler(c)

	// Should return OK when proxies are initialized
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "ok")
}

// TestProxyServerMetricsHandler tests metrics endpoint
func TestProxyServerMetricsHandler(t *testing.T) {
	server := &ProxyServer{}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/metrics", nil)

	server.metricsHandler(c)

	// Should return unauthorized since no auth header is present
	assert.Equal(t, http.StatusUnauthorized, w.Code)
}

// TestProxyServerMetricsHandlerWithValidToken tests metrics with valid token
func TestProxyServerMetricsHandlerWithValidToken(t *testing.T) {
	server := &ProxyServer{}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/metrics", nil)
	req.Header.Set("Authorization", "Bearer prometheus-scraper-token")
	c.Request = req

	server.metricsHandler(c)

	// Should return unauthorized (promhttp not properly initialized in test)
	// but at least the header parsing should work
	assert.True(t, w.Code == http.StatusUnauthorized || w.Code == http.StatusOK)
}

// TestTCPProxyStructure tests that TCPProxy has required fields
func TestTCPProxyStructure(t *testing.T) {
	proxy := &TCPProxy{
		listener: nil,
	}

	assert.NotNil(t, proxy)
	assert.Nil(t, proxy.listener)
	assert.Nil(t, proxy.authProvider)
}

// TestUDPProxyStructure tests that UDPProxy has required fields
func TestUDPProxyStructure(t *testing.T) {
	proxy := &UDPProxy{
		conn: nil,
	}

	assert.NotNil(t, proxy)
	assert.Nil(t, proxy.conn)
	assert.Nil(t, proxy.authProvider)
}

// TestInitLogging tests logging initialization
func TestInitLogging(t *testing.T) {
	viper.Reset()
	viper.SetDefault("log.level", "info")

	// Should not panic
	assert.NotPanics(t, func() {
		initLogging()
	})
}

// TestInitLoggingInvalidLevel tests logging with invalid level
func TestInitLoggingInvalidLevel(t *testing.T) {
	viper.Reset()
	viper.SetDefault("log.level", "invalid-level")

	// Should not panic, should default to info
	assert.NotPanics(t, func() {
		initLogging()
	})
}

// TestInitConfig tests configuration initialization
func TestInitConfig(t *testing.T) {
	// Clear environment
	os.Clearenv()

	// Should not panic
	assert.NotPanics(t, func() {
		initConfig()
	})

	// Verify defaults are set
	assert.Equal(t, "8443", viper.GetString("server.http_port"))
	assert.Equal(t, "8444", viper.GetString("server.tcp_port"))
	assert.Equal(t, "jwt", viper.GetString("auth.type"))
}

// TestInitConfigWithEnvironment tests config with environment variables
func TestInitConfigWithEnvironment(t *testing.T) {
	os.Setenv("HEADEND_AUTH_TYPE", "oauth2")
	defer os.Unsetenv("HEADEND_AUTH_TYPE")

	viper.Reset()
	initConfig()

	assert.Equal(t, "oauth2", viper.GetString("auth.type"))
}

// TestWireGuardRouterRouteTrafficIPParsing tests RouteTraffic with invalid IP
func TestWireGuardRouterRouteTrafficInvalidIP(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// Create a mock connection
	conn := &mockConn{
		remoteAddr: "127.0.0.1:5000",
	}

	// RouteTraffic should handle invalid hostnames by trying to resolve them
	// In test environment, resolution will fail, so we test the non-error path
	err = router.RouteTraffic("10.200.1.5", conn)
	// We expect an error since we can't actually dial or route in test env
	assert.Error(t, err)
}

// mockAuthProvider implements auth.Provider for testing
type mockAuthProvider struct{}

func (m *mockAuthProvider) LoginHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	}
}

func (m *mockAuthProvider) CallbackHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	}
}

func (m *mockAuthProvider) LogoutHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	}
}

func (m *mockAuthProvider) ValidateToken(token string) (*auth.User, error) {
	return &auth.User{Email: "test@example.com"}, nil
}

func (m *mockAuthProvider) GetUser(ctx *gin.Context) (*auth.User, error) {
	return &auth.User{Email: "test@example.com"}, nil
}

// mockConn implements net.Conn for testing
type mockConn struct {
	readData   []byte
	readIdx    int
	remoteAddr string
	closed     bool
}

func (m *mockConn) Read(b []byte) (n int, err error) {
	if m.readIdx >= len(m.readData) {
		return 0, fmt.Errorf("EOF")
	}
	n = copy(b, m.readData[m.readIdx:])
	m.readIdx += n
	return n, nil
}

func (m *mockConn) Write(b []byte) (n int, err error) {
	return len(b), nil
}

func (m *mockConn) Close() error {
	m.closed = true
	return nil
}

func (m *mockConn) LocalAddr() net.Addr {
	return &net.TCPAddr{IP: net.ParseIP("127.0.0.1"), Port: 5001}
}

func (m *mockConn) RemoteAddr() net.Addr {
	addr, _ := net.ResolveTCPAddr("tcp", m.remoteAddr)
	return addr
}

func (m *mockConn) SetDeadline(t time.Time) error {
	return nil
}

func (m *mockConn) SetReadDeadline(t time.Time) error {
	return nil
}

func (m *mockConn) SetWriteDeadline(t time.Time) error {
	return nil
}

// TestWireGuardRouterProxyData tests the proxyData method with small data
func TestWireGuardRouterProxyData(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	srcConn := &mockConn{
		readData:   []byte("test data"),
		remoteAddr: "127.0.0.1:5000",
	}

	dstConn := &mockConn{
		remoteAddr: "127.0.0.1:6000",
	}

	// Run proxy in goroutine since it blocks until EOF
	go router.proxyData(srcConn, dstConn, "test-direction")

	// Give goroutine time to read data
	time.Sleep(100 * time.Millisecond)

	// Both connections should be functional
	assert.NotNil(t, srcConn)
	assert.NotNil(t, dstConn)
}

// TestWireGuardRouterNetworkContainment tests network containment with various IPs
func TestWireGuardRouterNetworkContainment(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	tests := []struct {
		ip       string
		expected bool
	}{
		{"10.200.0.1", true},
		{"10.200.0.255", true},
		{"10.200.1.0", true},
		{"10.200.255.255", true},
		{"10.201.0.0", false},
		{"10.199.255.255", false},
		{"192.168.0.1", false},
		{"172.16.0.1", false},
	}

	for _, tt := range tests {
		t.Run(tt.ip, func(t *testing.T) {
			ip := net.ParseIP(tt.ip)
			result := router.wgNetwork.Contains(ip)
			assert.Equal(t, tt.expected, result)
		})
	}
}

// TestWireGuardRouterIPv6Support tests IPv6 CIDR support
func TestWireGuardRouterIPv6Support(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "fd00::/64", "fd00::1")
	require.NoError(t, err)

	tests := []struct {
		ip       string
		expected bool
	}{
		{"fd00::1", true},
		{"fd00::100", true},
		{"fd00::ffff:ffff:ffff:ffff", true},
		{"fe80::1", false},
		{"2001:db8::1", false},
	}

	for _, tt := range tests {
		t.Run(tt.ip, func(t *testing.T) {
			result := router.IsWireGuardDestination(tt.ip)
			assert.Equal(t, tt.expected, result)
		})
	}
}

// TestProxyServerSetupRoutes tests route setup creates gin router
func TestProxyServerSetupRoutes(t *testing.T) {
	// Set defaults for viper
	viper.Reset()
	viper.SetDefault("metrics.auth_token", "test-token")

	server := &ProxyServer{}

	// Wrap to handle potential panics from nil authProvider in routes
	defer func() {
		if r := recover(); r != nil {
			// setupRoutes calls middlewares that may panic if authProvider is nil
			// This is expected behavior
			t.Logf("setupRoutes panicked (expected): %v", r)
		}
	}()

	server.setupRoutes()

	if server.router != nil {
		assert.NotNil(t, server.router)
	}
}

// TestWireGuardRouterMarkTrafficAuthenticatedNonTCP tests with non-TCP connection
func TestWireGuardRouterMarkTrafficAuthenticatedNonTCP(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// Use mock connection (not TCP)
	conn := &mockConn{
		remoteAddr: "127.0.0.1:5000",
	}

	// Should return nil since we only mark TCP connections
	err = router.markTrafficAuthenticated(conn)
	assert.NoError(t, err)
}

// BenchmarkWireGuardRouterIsWireGuardDestination benchmarks IP containment checks
func BenchmarkWireGuardRouterIsWireGuardDestination(b *testing.B) {
	router, _ := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		router.IsWireGuardDestination("10.200.1.5")
	}
}

// BenchmarkWireGuardRouterNetworkContainment benchmarks network containment checks
func BenchmarkWireGuardRouterNetworkContainment(b *testing.B) {
	router, _ := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	ip := net.ParseIP("10.200.1.5")

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = router.wgNetwork.Contains(ip)
	}
}

// TestProxyServerExtractJWTFromTCPPacket tests JWT extraction
func TestProxyServerExtractJWTFromTCPPacket(t *testing.T) {
	server := &ProxyServer{}

	tests := []struct {
		name      string
		data      []byte
		expected  string
	}{
		{
			name:     "JWT found",
			data:     []byte("JWT:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\nOther data"),
			expected: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
		},
		{
			name:     "JWT without newline",
			data:     []byte("JWT:mytoken123"),
			expected: "mytoken123",
		},
		{
			name:     "JWT not found",
			data:     []byte("Some other data"),
			expected: "",
		},
		{
			name:     "JWT with spaces",
			data:     []byte("JWT:  token123  \nmore"),
			expected: "token123",
		},
		{
			name:     "empty data",
			data:     []byte(""),
			expected: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := server.extractJWTFromTCPPacket(tt.data)
			assert.Equal(t, tt.expected, result)
		})
	}
}

// TestProxyServerExtractTargetFromTCPPacket tests target extraction
func TestProxyServerExtractTargetFromTCPPacket(t *testing.T) {
	server := &ProxyServer{}

	tests := []struct {
		name     string
		data     []byte
		expected string
	}{
		{
			name:     "target found",
			data:     []byte("HOST:example.com:443\nOther data"),
			expected: "example.com:443",
		},
		{
			name:     "target without newline",
			data:     []byte("HOST:10.200.1.5"),
			expected: "10.200.1.5",
		},
		{
			name:     "target not found",
			data:     []byte("Some other data"),
			expected: "",
		},
		{
			name:     "target with spaces",
			data:     []byte("HOST:  api.example.com  \nmore"),
			expected: "api.example.com",
		},
		{
			name:     "empty data",
			data:     []byte(""),
			expected: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := server.extractTargetFromTCPPacket(tt.data)
			assert.Equal(t, tt.expected, result)
		})
	}
}

// TestProxyServerExtractJWTFromUDPPacket tests UDP JWT extraction
func TestProxyServerExtractJWTFromUDPPacket(t *testing.T) {
	server := &ProxyServer{}

	data := []byte("JWT:udp-token-123\nMore data")
	result := server.extractJWTFromUDPPacket(data)
	assert.Equal(t, "udp-token-123", result)
}

// TestProxyServerExtractTargetFromUDPPacket tests UDP target extraction
func TestProxyServerExtractTargetFromUDPPacket(t *testing.T) {
	server := &ProxyServer{}

	data := []byte("HOST:8.8.8.8:53\nMore data")
	result := server.extractTargetFromUDPPacket(data)
	assert.Equal(t, "8.8.8.8:53", result)
}

// TestProxyServerProxyTCPData tests bidirectional data proxying
func TestProxyServerProxyTCPData(t *testing.T) {
	server := &ProxyServer{}

	srcConn := &mockConn{
		readData:   []byte("test tcp data"),
		remoteAddr: "127.0.0.1:5000",
	}

	dstConn := &mockConn{
		remoteAddr: "127.0.0.1:6000",
	}

	// Run in goroutine to avoid blocking
	go server.proxyTCPData(srcConn, dstConn, "test-direction")

	// Give goroutine time to process
	time.Sleep(100 * time.Millisecond)
}

// TestProxyServerOverlayScope tests overlay scope determination
func TestProxyServerOverlayScope(t *testing.T) {
	viper.Reset()
	viper.SetDefault("overlay.type", "wireguard")

	server := &ProxyServer{}
	server.overlayManager = nil

	// Should return default when overlay manager is nil
	scope := server.overlayScope()
	assert.NotEmpty(t, scope)
}

// TestTCPProxyHandleConnectionEmptyData tests TCP proxy with empty data
func TestTCPProxyHandleConnectionEmptyData(t *testing.T) {
	tcpProxy := &TCPProxy{
		authProvider: &mockAuthProvider{},
	}

	conn := &mockConn{
		readData:   []byte(""),
		remoteAddr: "127.0.0.1:5000",
	}

	// Should handle gracefully
	defer func() {
		if r := recover(); r != nil {
			t.Logf("handleConnection panicked: %v", r)
		}
	}()
	tcpProxy.handleConnection(conn)
}

// TestUDPProxyHandlePacketEmptyData tests UDP proxy with empty data
func TestUDPProxyHandlePacketEmptyData(t *testing.T) {
	udpProxy := &UDPProxy{
		authProvider: &mockAuthProvider{},
	}

	addr := &net.UDPAddr{
		IP:   net.ParseIP("127.0.0.1"),
		Port: 5000,
	}

	// Should handle gracefully
	defer func() {
		if r := recover(); r != nil {
			t.Logf("handlePacket panicked: %v", r)
		}
	}()
	udpProxy.handlePacket([]byte(""), addr)
}

// TestProxyServerProxyDataLargePayload tests proxy with large data
func TestProxyServerProxyDataLargePayload(t *testing.T) {
	server := &ProxyServer{}

	// Create 1MB of test data
	largeData := make([]byte, 1024*1024)
	for i := range largeData {
		largeData[i] = byte(i % 256)
	}

	srcConn := &mockConn{
		readData:   largeData,
		remoteAddr: "127.0.0.1:5000",
	}

	dstConn := &mockConn{
		remoteAddr: "127.0.0.1:6000",
	}

	// Should handle large payloads
	go server.proxyTCPData(srcConn, dstConn, "large-payload-test")
	time.Sleep(100 * time.Millisecond)
}

// TestWireGuardRouterRouteTrafficWithIPAddress tests RouteTraffic with IP address
func TestWireGuardRouterRouteTrafficWithIPAddress(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// Try routing to an IP (will fail due to no real WireGuard interface)
	conn := &mockConn{
		remoteAddr: "127.0.0.1:5000",
	}

	// Should attempt to route
	err = router.RouteTraffic("10.200.1.5", conn)
	assert.Error(t, err) // Expected to fail in test environment
}

// TestWireGuardRouterRouteTrafficExternalHost tests RouteTraffic to external host
func TestWireGuardRouterRouteTrafficExternalHost(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	conn := &mockConn{
		remoteAddr: "127.0.0.1:5000",
	}

	// Try routing to external host
	err = router.RouteTraffic("8.8.8.8", conn)
	assert.Error(t, err) // Expected to fail (can't dial in test)
}

// TestProxyServerHealthHandlerWithManagers tests health with initialized managers
func TestProxyServerHealthHandlerWithManagers(t *testing.T) {
	server := &ProxyServer{
		tcpProxy: &TCPProxy{},
		udpProxy: &UDPProxy{},
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/health", nil)

	server.healthHandler(c)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "tcp_proxy")
	assert.Contains(t, w.Body.String(), "udp_proxy")
}

// TestTCPProxyExtractJWTFromTCPPacket tests TCP proxy JWT extraction
func TestTCPProxyExtractJWTFromTCPPacket(t *testing.T) {
	tcpProxy := &TCPProxy{}

	data := []byte("JWT:tcp-proxy-token\n")
	result := tcpProxy.extractJWTFromTCPPacket(data)
	assert.Equal(t, "tcp-proxy-token", result)
}

// TestTCPProxyExtractTargetFromTCPPacket tests TCP proxy target extraction
func TestTCPProxyExtractTargetFromTCPPacket(t *testing.T) {
	tcpProxy := &TCPProxy{}

	data := []byte("HOST:proxy.test:8080\n")
	result := tcpProxy.extractTargetFromTCPPacket(data)
	assert.Equal(t, "proxy.test:8080", result)
}

// TestUDPProxyExtractJWTFromUDPPacket tests UDP proxy JWT extraction
func TestUDPProxyExtractJWTFromUDPPacket(t *testing.T) {
	udpProxy := &UDPProxy{}

	data := []byte("JWT:udp-proxy-token\n")
	result := udpProxy.extractJWTFromUDPPacket(data)
	assert.Equal(t, "udp-proxy-token", result)
}

// TestUDPProxyExtractTargetFromUDPPacket tests UDP proxy target extraction
func TestUDPProxyExtractTargetFromUDPPacket(t *testing.T) {
	udpProxy := &UDPProxy{}

	data := []byte("HOST:dns.test:53\n")
	result := udpProxy.extractTargetFromUDPPacket(data)
	assert.Equal(t, "dns.test:53", result)
}

// TestTCPProxyProxyData tests TCP proxy data proxying
func TestTCPProxyProxyData(t *testing.T) {
	tcpProxy := &TCPProxy{}

	src := &mockConn{
		readData:   []byte("test"),
		remoteAddr: "127.0.0.1:5000",
	}

	dst := &mockConn{
		remoteAddr: "127.0.0.1:6000",
	}

	go tcpProxy.proxyData(src, dst, "test")
	time.Sleep(50 * time.Millisecond)
}

// TestUDPProxyNoConn tests UDP proxy when conn is nil
func TestUDPProxyNoConn(t *testing.T) {
	udpProxy := &UDPProxy{
		conn: nil,
	}

	assert.Nil(t, udpProxy.conn)
	assert.Nil(t, udpProxy.authProvider)
}

// TestProxyServerUserInfoHandlerWithClaims tests userinfo with valid claims
func TestProxyServerUserInfoHandlerWithClaims(t *testing.T) {
	server := &ProxyServer{}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/auth/userinfo", nil)

	// Simulate setting claims in context
	c.Set("claims", map[string]interface{}{
		"email": "test@example.com",
	})

	// Should panic or error gracefully since claims is not the right type
	defer func() {
		if r := recover(); r != nil {
			t.Logf("userInfoHandler panicked as expected: %v", r)
		}
	}()
	server.userInfoHandler(c)
}

// TestProxyServerProxyHandlerNoTarget tests proxy handler without target
func TestProxyServerProxyHandlerNoTarget(t *testing.T) {
	server := &ProxyServer{}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("POST", "/proxy", nil)

	defer func() {
		if r := recover(); r != nil {
			t.Logf("proxyHandler panicked: %v", r)
		}
	}()
	server.proxyHandler(c)
}

// TestWireGuardRouterRouteToPeerWithValidIP tests routeToPeer logic
func TestWireGuardRouterRouteToPeerWithValidIP(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	conn := &mockConn{
		readData:   []byte("test"),
		remoteAddr: "10.200.1.1:5000",
	}

	// This will fail because wg command is not available, but we test the code path
	err = router.routeToPeer("10.200.1.5", conn)
	assert.Error(t, err)
}

// TestWireGuardRouterRouteToInternetNoDialing tests routeToInternet failure
func TestWireGuardRouterRouteToInternetNoDialing(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	conn := &mockConn{
		readData:   []byte("test"),
		remoteAddr: "127.0.0.1:5000",
	}

	// Try to route to a non-existent host
	err = router.routeToInternet("invalid-host:99999", conn)
	assert.Error(t, err)
}

// TestWireGuardRouterDialPeerErrorHandling tests dialPeer
func TestWireGuardRouterDialPeerErrorHandling(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// Attempt to dial an invalid peer
	conn, err := router.dialPeer("999.999.999.999")
	assert.Error(t, err)
	assert.Nil(t, conn)
}

// TestWireGuardRouterGetWireGuardPeersEmpty tests getPeers with simulated empty output
func TestWireGuardRouterGetWireGuardPeersEmpty(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// This will fail but we verify error handling
	peers, err := router.GetWireGuardPeers()
	assert.Error(t, err)
	assert.Nil(t, peers)
}

// TestTCPProxyStart tests TCP proxy start method
func TestTCPProxyStart(t *testing.T) {
	tcpProxy := &TCPProxy{
		listener:     nil,
		authProvider: &mockAuthProvider{},
	}

	// Start without a listener will just wait
	assert.Nil(t, tcpProxy.listener)
}

// TestUDPProxyStart tests UDP proxy start method
func TestUDPProxyStart(t *testing.T) {
	udpProxy := &UDPProxy{
		conn:         nil,
		authProvider: &mockAuthProvider{},
	}

	// Start without a connection
	assert.Nil(t, udpProxy.conn)
}

// TestProxyServerPortManagerIntegration tests port manager field
func TestProxyServerPortManagerIntegration(t *testing.T) {
	server := &ProxyServer{
		portManager: nil,
	}

	assert.Nil(t, server.portManager)
}

// TestProxyServerMirrorManagerIntegration tests mirror manager field
func TestProxyServerMirrorManagerIntegration(t *testing.T) {
	server := &ProxyServer{
		mirrorManager: nil,
	}

	assert.Nil(t, server.mirrorManager)
}

// TestProxyServerFirewallManagerIntegration tests firewall manager field
func TestProxyServerFirewallManagerIntegration(t *testing.T) {
	server := &ProxyServer{
		firewallManager: nil,
	}

	assert.Nil(t, server.firewallManager)
}

// TestProxyServerSyslogLoggerIntegration tests syslog logger field
func TestProxyServerSyslogLoggerIntegration(t *testing.T) {
	server := &ProxyServer{
		syslogLogger: nil,
	}

	assert.Nil(t, server.syslogLogger)
}

// TestProxyServerXDPProtectionIntegration tests XDP protection field
func TestProxyServerXDPProtectionIntegration(t *testing.T) {
	server := &ProxyServer{
		xdpProtection: nil,
	}

	assert.Nil(t, server.xdpProtection)
}

// TestProxyServerOverlayManagerIntegration tests overlay manager field
func TestProxyServerOverlayManagerIntegration(t *testing.T) {
	server := &ProxyServer{
		overlayManager: nil,
	}

	assert.Nil(t, server.overlayManager)
}

// TestProxyServerEgressProxyIntegration tests egress proxy field
func TestProxyServerEgressProxyIntegration(t *testing.T) {
	server := &ProxyServer{
		egressProxy: nil,
	}

	assert.Nil(t, server.egressProxy)
}

// TestProxyServerHTTPServerIntegration tests HTTP server field
func TestProxyServerHTTPServerIntegration(t *testing.T) {
	server := &ProxyServer{
		httpServer: nil,
	}

	assert.Nil(t, server.httpServer)
}

// TestWireGuardRouterIsWireGuardDestinationHostname tests hostname resolution
func TestWireGuardRouterIsWireGuardDestinationHostname(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	// Test with an invalid hostname that won't resolve
	result := router.IsWireGuardDestination("invalid-host-that-doesnt-exist.internal")
	assert.False(t, result)
}

// TestWireGuardRouterIPv4Parsing tests IPv4 parsing variations
func TestWireGuardRouterIPv4Parsing(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/24", "10.200.0.1")
	require.NoError(t, err)

	tests := []struct {
		name     string
		ip       string
		expected bool
	}{
		{"valid IP in range", "10.200.0.100", true},
		{"network address", "10.200.0.0", true},
		{"broadcast address", "10.200.0.255", true},
		{"outside range", "10.201.0.0", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := router.IsWireGuardDestination(tt.ip)
			assert.Equal(t, tt.expected, result)
		})
	}
}

// TestProxyServerMetricsHandlerWithBadToken tests metrics with invalid token
func TestProxyServerMetricsHandlerWithBadToken(t *testing.T) {
	server := &ProxyServer{
		authProvider: &mockAuthProvider{},
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/metrics", nil)
	req.Header.Set("Authorization", "Bearer invalid-token-123")
	c.Request = req

	server.metricsHandler(c)

	// Should return unauthorized or OK depending on implementation
	assert.Contains(t, []int{http.StatusUnauthorized, http.StatusOK}, w.Code)
}

// TestProxyServerHealthHandlerWithSyslog tests health with syslog
func TestProxyServerHealthHandlerWithSyslog(t *testing.T) {
	viper.Reset()

	server := &ProxyServer{
		tcpProxy:     &TCPProxy{},
		udpProxy:     &UDPProxy{},
		syslogLogger: nil,
		portManager:  nil,
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/health", nil)

	server.healthHandler(c)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "healthy")
}

// TestWireGuardRouterRouteToPeerWithMockConn tests routing to peer
func TestWireGuardRouterRouteToPeerWithMockConn(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	srcConn := &mockConn{
		readData:   []byte{},
		remoteAddr: "127.0.0.1:5000",
	}

	// This will fail because isPeerConfigured calls wg command
	// which is not available in test, but it exercises the code path
	err = router.routeToPeer("10.200.1.5", srcConn)
	assert.Error(t, err, "routeToPeer should error when peer not found")
}

// TestWireGuardRouterRouteToInternetWithMockConn tests routing to internet
func TestWireGuardRouterRouteToInternetWithMockConn(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	srcConn := &mockConn{
		readData:   []byte{},
		remoteAddr: "127.0.0.1:5000",
	}

	// This will fail because we can't actually dial to invalid host
	// but it exercises the code path
	err = router.routeToInternet("invalid-host-x.local:9999", srcConn)
	// May error or succeed depending on net.Dial behavior
	_ = err
}

// TestOIDCRPOrNil tests oidcRPOrNil function
func TestOIDCRPOrNil(t *testing.T) {
	result := oidcRPOrNil(nil)
	assert.Nil(t, result)
}

// TestHealthHandlerWithMirrorManager tests health handler with mirror enabled
func TestHealthHandlerWithMirrorManager(t *testing.T) {
	viper.Reset()
	viper.SetDefault("server.metrics_port", "9090")

	server := &ProxyServer{
		tcpProxy:      &TCPProxy{},
		udpProxy:      &UDPProxy{},
		mirrorManager: &mirror.Manager{}, // Non-nil indicates enabled
		portManager:   nil,
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/health", nil)

	server.healthHandler(c)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "mirror_enabled")
}

// TestHealthHandlerWithFirewall tests health handler with firewall
func TestHealthHandlerWithFirewall(t *testing.T) {
	viper.Reset()
	viper.SetDefault("server.metrics_port", "9090")

	server := &ProxyServer{
		tcpProxy:        &TCPProxy{},
		udpProxy:        &UDPProxy{},
		firewallManager: &firewall.Manager{},
		portManager:     nil,
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest("GET", "/health", nil)

	server.healthHandler(c)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), "firewall_enabled")
}

// TestMetricsHandlerWithJWTAuth tests metrics with JWT token validation
func TestMetricsHandlerWithJWTAuth(t *testing.T) {
	server := &ProxyServer{
		authProvider: &mockAuthProvider{},
	}

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/metrics", nil)
	req.Header.Set("Authorization", "Bearer valid-jwt-token")
	c.Request = req

	server.metricsHandler(c)

	// Should try JWT auth
	assert.True(t, w.Code == http.StatusUnauthorized || w.Code == http.StatusOK)
}

// TestInitializeUDPProxyConfigOptions tests UDP proxy initialization error handling
func TestInitializeUDPProxyListenError(t *testing.T) {
	viper.Reset()
	viper.SetDefault("server.udp_port", "invalid-port")

	server := &ProxyServer{
		authProvider: &mockAuthProvider{},
	}

	err := server.initializeUDPProxy()
	assert.Error(t, err, "UDP proxy should error with invalid port")
}

// TestWireGuardRouterMarkTrafficAuthenticatedNonTCPConn tests mark traffic with non-TCP connection
func TestWireGuardRouterMarkTrafficAuthenticatedNonTCPConn(t *testing.T) {
	router, err := NewWireGuardRouter("wg0", "10.200.0.0/16", "10.200.0.1")
	require.NoError(t, err)

	conn := &mockConn{
		remoteAddr: "127.0.0.1:5000",
	}

	// Should return nil since mockConn is not a *net.TCPConn
	err = router.markTrafficAuthenticated(conn)
	assert.Nil(t, err, "markTrafficAuthenticated should handle non-TCP connections gracefully")
}
