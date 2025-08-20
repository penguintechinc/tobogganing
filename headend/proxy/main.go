package main

import (
    "context"
    "crypto/tls"
    "fmt"
    "net"
    "net/http"
    "net/http/httputil"
    "net/url"
    "os"
    "os/signal"
    "strings"
    "sync"
    "syscall"
    "time"

    "github.com/gin-gonic/gin"
    "github.com/prometheus/client_golang/prometheus/promhttp"
    log "github.com/sirupsen/logrus"
    "github.com/spf13/viper"

    "github.com/sasewaddle/headend/proxy/auth"
    "github.com/sasewaddle/headend/proxy/firewall"
    "github.com/sasewaddle/headend/proxy/mirror"
    "github.com/sasewaddle/headend/proxy/middleware"
)

type ProxyServer struct {
    router          *gin.Engine
    httpServer      *http.Server
    tcpProxy        *TCPProxy
    udpProxy        *UDPProxy
    authProvider    auth.Provider
    mirrorManager   *mirror.Manager
    firewallManager *firewall.Manager
    proxies         map[string]*httputil.ReverseProxy
    mu              sync.RWMutex
}

// TCPProxy handles raw TCP traffic with JWT authentication
type TCPProxy struct {
    listener        net.Listener
    authProvider    auth.Provider
    mirrorManager   *mirror.Manager
    firewallManager *firewall.Manager
}

// UDPProxy handles raw UDP traffic with JWT authentication  
type UDPProxy struct {
    conn            *net.UDPConn
    authProvider    auth.Provider
    mirrorManager   *mirror.Manager
    firewallManager *firewall.Manager
}

func main() {
    initConfig()
    initLogging()

    server := &ProxyServer{
        proxies: make(map[string]*httputil.ReverseProxy),
    }

    if err := server.Initialize(); err != nil {
        log.Fatalf("Failed to initialize server: %v", err)
    }

    if err := server.Run(); err != nil {
        log.Fatalf("Server failed: %v", err)
    }
}

func initConfig() {
    viper.SetConfigName("config")
    viper.SetConfigType("yaml")
    viper.AddConfigPath("/etc/headend/")
    viper.AddConfigPath(".")

    viper.SetEnvPrefix("HEADEND")
    viper.AutomaticEnv()
    viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))

    viper.SetDefault("server.http_port", "8443")
    viper.SetDefault("server.tcp_port", "8444") 
    viper.SetDefault("server.udp_port", "8445")
    viper.SetDefault("server.metrics_port", "9090")
    viper.SetDefault("auth.type", "jwt")
    viper.SetDefault("auth.manager_url", "http://manager:8000")
    viper.SetDefault("mirror.enabled", false)
    viper.SetDefault("mirror.buffer_size", 1000)
    viper.SetDefault("mirror.suricata_enabled", false)
    viper.SetDefault("mirror.suricata_host", "")
    viper.SetDefault("mirror.suricata_port", "9999")
    viper.SetDefault("log.level", "info")
    viper.SetDefault("wireguard.interface", "wg0")
    viper.SetDefault("wireguard.network", "10.200.0.0/16")

    if err := viper.ReadInConfig(); err != nil {
        log.Warnf("No config file found, using environment variables: %v", err)
    }
}

func initLogging() {
    logLevel := viper.GetString("log.level")
    level, err := log.ParseLevel(logLevel)
    if err != nil {
        level = log.InfoLevel
    }
    log.SetLevel(level)
    log.SetFormatter(&log.JSONFormatter{})
}

func (s *ProxyServer) Initialize() error {
    var err error

    // Initialize auth provider - supports JWT, OAuth2, or SAML2
    authType := viper.GetString("auth.type")
    switch authType {
    case "jwt":
        s.authProvider, err = auth.NewJWTProvider(
            viper.GetString("auth.manager_url"),
            viper.GetString("auth.jwt_public_key_path"),
        )
    case "oauth2":
        s.authProvider, err = auth.NewOAuth2Provider(
            viper.GetString("auth.oauth2.issuer"),
            viper.GetString("auth.oauth2.client_id"),
            viper.GetString("auth.oauth2.client_secret"),
        )
    case "saml2":
        s.authProvider, err = auth.NewSAML2Provider(
            viper.GetString("auth.saml2.idp_metadata_url"),
            viper.GetString("auth.saml2.sp_entity_id"),
        )
    default:
        return fmt.Errorf("unsupported auth type: %s", authType)
    }

    if err != nil {
        return fmt.Errorf("failed to initialize auth provider: %w", err)
    }

    // Initialize traffic mirroring if enabled
    if viper.GetBool("mirror.enabled") {
        destinations := viper.GetStringSlice("mirror.destinations")
        
        // Check if Suricata is enabled
        suricataEnabled := viper.GetBool("mirror.suricata_enabled")
        if suricataEnabled {
            s.mirrorManager = mirror.NewManagerWithSuricata(
                destinations,
                viper.GetString("mirror.protocol"),
                viper.GetInt("mirror.buffer_size"),
                viper.GetString("mirror.suricata_host"),
                viper.GetString("mirror.suricata_port"),
            )
            log.Info("Traffic mirroring with Suricata IDS/IPS enabled")
        } else {
            s.mirrorManager = mirror.NewManager(
                destinations,
                viper.GetString("mirror.protocol"),
                viper.GetInt("mirror.buffer_size"),
            )
            log.Info("Traffic mirroring enabled")
        }
        
        if err := s.mirrorManager.Start(); err != nil {
            return fmt.Errorf("failed to start mirror manager: %w", err)
        }
    }

    // Initialize TCP and UDP proxies
    if err := s.initializeTCPProxy(); err != nil {
        return fmt.Errorf("failed to initialize TCP proxy: %w", err)
    }
    
    if err := s.initializeUDPProxy(); err != nil {
        return fmt.Errorf("failed to initialize UDP proxy: %w", err)  
    }

    // Setup HTTP routes
    s.setupRoutes()

    return nil
}

func (s *ProxyServer) setupRoutes() {
    gin.SetMode(gin.ReleaseMode)
    s.router = gin.New()

    // Add middleware
    s.router.Use(gin.Recovery())
    s.router.Use(middleware.Logger())
    s.router.Use(middleware.Metrics())

    // Health check endpoints
    s.router.GET("/health", s.healthHandler)
    s.router.GET("/healthz", s.healthzHandler)

    // Auth endpoints
    authGroup := s.router.Group("/auth")
    {
        authGroup.POST("/login", s.authProvider.LoginHandler())
        authGroup.GET("/callback", s.authProvider.CallbackHandler())
        authGroup.POST("/logout", s.authProvider.LogoutHandler())
        authGroup.GET("/userinfo", middleware.AuthRequired(s.authProvider), s.userInfoHandler)
    }

    // Proxy endpoints (require authentication)
    proxyGroup := s.router.Group("/proxy")
    proxyGroup.Use(middleware.AuthRequired(s.authProvider))
    {
        proxyGroup.Any("/*path", s.proxyHandler)
    }

    // Metrics endpoint with authentication
    go func() {
        metricsPort := viper.GetString("server.metrics_port")
        metricsRouter := gin.New()
        metricsRouter.Use(gin.Recovery())
        
        // Authenticated metrics endpoint
        metricsRouter.GET("/metrics", s.metricsHandler)
        
        log.Infof("Metrics server listening on :%s", metricsPort)
        if err := http.ListenAndServe(":"+metricsPort, metricsRouter); err != nil {
            log.Errorf("Metrics server failed: %v", err)
        }
    }()
}

func (s *ProxyServer) healthHandler(c *gin.Context) {
    c.JSON(http.StatusOK, gin.H{
        "status": "healthy",
        "service": "headend-proxy",
        "mirror_enabled": s.mirrorManager != nil,
        "auth_provider": s.authProvider != nil,
        "tcp_proxy": s.tcpProxy != nil,
        "udp_proxy": s.udpProxy != nil,
    })
}

func (s *ProxyServer) healthzHandler(c *gin.Context) {
    // Kubernetes-style health check
    healthy := true
    
    // Check auth provider
    if s.authProvider == nil {
        healthy = false
    }
    
    // Check proxies
    if s.tcpProxy == nil || s.udpProxy == nil {
        healthy = false
    }
    
    if healthy {
        c.JSON(http.StatusOK, gin.H{"status": "ok"})
    } else {
        c.JSON(http.StatusServiceUnavailable, gin.H{"status": "error"})
    }
}

func (s *ProxyServer) metricsHandler(c *gin.Context) {
    // Check authentication for metrics endpoint
    authHeader := c.GetHeader("Authorization")
    
    if authHeader == "" {
        c.JSON(http.StatusUnauthorized, gin.H{"error": "Authorization header required"})
        return
    }
    
    if strings.HasPrefix(authHeader, "Bearer ") {
        // Check for Prometheus scraper token
        token := strings.TrimPrefix(authHeader, "Bearer ")
        expectedToken := viper.GetString("metrics.auth_token")
        
        if expectedToken == "" {
            expectedToken = "prometheus-scraper-token" // Default token
        }
        
        if token == expectedToken {
            // Serve Prometheus metrics
            promhttp.Handler().ServeHTTP(c.Writer, c.Request)
            return
        }
    }
    
    // Try JWT authentication for headend users
    if strings.HasPrefix(authHeader, "Bearer ") {
        token := strings.TrimPrefix(authHeader, "Bearer ")
        user, err := s.authProvider.ValidateToken(token)
        
        if err == nil && user != nil {
            // Valid JWT token - allow access
            promhttp.Handler().ServeHTTP(c.Writer, c.Request)
            return
        }
    }
    
    c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid authentication"})
}

func (s *ProxyServer) userInfoHandler(c *gin.Context) {
    user := c.MustGet("user").(auth.User)
    c.JSON(http.StatusOK, user)
}

func (s *ProxyServer) proxyHandler(c *gin.Context) {
    targetHost := c.GetHeader("X-Target-Host")
    if targetHost == "" {
        c.JSON(http.StatusBadRequest, gin.H{"error": "Missing X-Target-Host header"})
        return
    }

    // Get or create proxy for target
    proxy := s.getOrCreateProxy(targetHost)

    // Mirror traffic if enabled
    if s.mirrorManager != nil {
        // Create a response writer wrapper to capture response
        mrw := &mirrorResponseWriter{
            ResponseWriter: c.Writer,
            mirrorManager: s.mirrorManager,
            request:       c.Request,
        }
        c.Writer = mrw
    }

    // Proxy the request
    proxy.ServeHTTP(c.Writer, c.Request)
}

func (s *ProxyServer) getOrCreateProxy(targetHost string) *httputil.ReverseProxy {
    s.mu.RLock()
    proxy, exists := s.proxies[targetHost]
    s.mu.RUnlock()

    if exists {
        return proxy
    }

    s.mu.Lock()
    defer s.mu.Unlock()

    // Double-check after acquiring write lock
    if proxy, exists := s.proxies[targetHost]; exists {
        return proxy
    }

    // Create new proxy
    targetURL, _ := url.Parse(fmt.Sprintf("https://%s", targetHost))
    proxy = httputil.NewSingleHostReverseProxy(targetURL)

    // Configure proxy
    proxy.Transport = &http.Transport{
        TLSClientConfig: &tls.Config{
            InsecureSkipVerify: viper.GetBool("proxy.skip_tls_verify"),
        },
        MaxIdleConns:        100,
        MaxIdleConnsPerHost: 10,
        IdleConnTimeout:     90 * time.Second,
    }

    proxy.ModifyResponse = func(resp *http.Response) error {
        // Add security headers
        resp.Header.Set("X-Frame-Options", "DENY")
        resp.Header.Set("X-Content-Type-Options", "nosniff")
        resp.Header.Set("X-XSS-Protection", "1; mode=block")
        return nil
    }

    s.proxies[targetHost] = proxy
    return proxy
}

func (s *ProxyServer) initializeTCPProxy() error {
    tcpPort := viper.GetString("server.tcp_port")
    
    listener, err := net.Listen("tcp", ":"+tcpPort)
    if err != nil {
        return fmt.Errorf("failed to create TCP listener: %w", err)
    }
    
    s.tcpProxy = &TCPProxy{
        listener:      listener,
        authProvider:  s.authProvider,
        mirrorManager: s.mirrorManager,
    }
    
    // Start TCP proxy in goroutine
    go s.tcpProxy.Start()
    
    log.Infof("TCP proxy listening on port %s", tcpPort)
    return nil
}

func (s *ProxyServer) initializeUDPProxy() error {
    udpPort := viper.GetString("server.udp_port")
    
    addr, err := net.ResolveUDPAddr("udp", ":"+udpPort)
    if err != nil {
        return fmt.Errorf("failed to resolve UDP address: %w", err)
    }
    
    conn, err := net.ListenUDP("udp", addr)
    if err != nil {
        return fmt.Errorf("failed to create UDP listener: %w", err)
    }
    
    s.udpProxy = &UDPProxy{
        conn:          conn,
        authProvider:  s.authProvider,
        mirrorManager: s.mirrorManager,
    }
    
    // Start UDP proxy in goroutine
    go s.udpProxy.Start()
    
    log.Infof("UDP proxy listening on port %s", udpPort)
    return nil
}

func (s *ProxyServer) Run() error {
    httpPort := viper.GetString("server.http_port")
    certFile := viper.GetString("server.cert_file")
    keyFile := viper.GetString("server.key_file")

    s.httpServer = &http.Server{
        Addr:         ":" + httpPort,
        Handler:      s.router,
        ReadTimeout:  30 * time.Second,
        WriteTimeout: 30 * time.Second,
        IdleTimeout:  120 * time.Second,
    }

    // Graceful shutdown
    go func() {
        sigChan := make(chan os.Signal, 1)
        signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
        <-sigChan

        log.Info("Shutting down server...")
        
        ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
        defer cancel()

        if s.mirrorManager != nil {
            s.mirrorManager.Stop()
        }
        
        // Close TCP and UDP proxies
        if s.tcpProxy != nil && s.tcpProxy.listener != nil {
            s.tcpProxy.listener.Close()
        }
        if s.udpProxy != nil && s.udpProxy.conn != nil {
            s.udpProxy.conn.Close()
        }

        if err := s.httpServer.Shutdown(ctx); err != nil {
            log.Errorf("Server shutdown error: %v", err)
        }
    }()

    log.Infof("Starting headend HTTP proxy on port %s", httpPort)
    
    if certFile != "" && keyFile != "" {
        return s.httpServer.ListenAndServeTLS(certFile, keyFile)
    }
    
    return s.httpServer.ListenAndServe()
}

type mirrorResponseWriter struct {
    http.ResponseWriter
    mirrorManager *mirror.Manager
    request       *http.Request
    statusCode    int
    written       []byte
}

func (mrw *mirrorResponseWriter) WriteHeader(code int) {
    mrw.statusCode = code
    mrw.ResponseWriter.WriteHeader(code)
}

func (mrw *mirrorResponseWriter) Write(data []byte) (int, error) {
    mrw.written = append(mrw.written, data...)
    
    // Send to mirror asynchronously
    go mrw.mirrorManager.MirrorHTTP(mrw.request, mrw.statusCode, mrw.written)
    
    return mrw.ResponseWriter.Write(data)
}

// TCP Proxy Implementation
func (t *TCPProxy) Start() {
    log.Info("Starting TCP proxy server")
    
    for {
        conn, err := t.listener.Accept()
        if err != nil {
            log.Errorf("TCP accept error: %v", err)
            continue
        }
        
        // Handle connection in goroutine with authentication
        go t.handleConnection(conn)
    }
}

func (t *TCPProxy) handleConnection(clientConn net.Conn) {
    defer clientConn.Close()
    
    // Read first packet to extract JWT token from headers
    buffer := make([]byte, 4096)
    n, err := clientConn.Read(buffer)
    if err != nil {
        log.Errorf("TCP read error: %v", err)
        return
    }
    
    // Parse JWT token from connection metadata
    // This would typically be in a custom protocol header
    token := t.extractJWTFromTCPPacket(buffer[:n])
    
    // Authenticate using JWT
    user, err := t.authProvider.ValidateToken(token)
    if err != nil {
        log.Errorf("TCP authentication failed: %v", err)
        return
    }
    
    log.Infof("TCP connection authenticated for user: %s", user.ID)
    
    // Extract target host from the packet
    targetHost := t.extractTargetFromTCPPacket(buffer[:n])
    if targetHost == "" {
        log.Error("No target host found in TCP packet")
        return
    }
    
    // Connect to target
    targetConn, err := net.Dial("tcp", targetHost)
    if err != nil {
        log.Errorf("Failed to connect to target %s: %v", targetHost, err)
        return
    }
    defer targetConn.Close()
    
    // Send original packet to target
    if _, err := targetConn.Write(buffer[:n]); err != nil {
        log.Errorf("Failed to write to target: %v", err)
        return
    }
    
    // Mirror traffic if enabled
    if t.mirrorManager != nil {
        go t.mirrorManager.MirrorTCP(clientConn.RemoteAddr().String(), targetHost, buffer[:n])
    }
    
    // Bidirectional proxy
    go t.proxyData(clientConn, targetConn, "client->target")
    t.proxyData(targetConn, clientConn, "target->client")
}

func (t *TCPProxy) proxyData(src, dst net.Conn, direction string) {
    buffer := make([]byte, 32768)
    
    for {
        n, err := src.Read(buffer)
        if err != nil {
            break
        }
        
        if _, err := dst.Write(buffer[:n]); err != nil {
            break
        }
        
        // Mirror additional data if enabled
        if t.mirrorManager != nil {
            go t.mirrorManager.MirrorTCP(src.RemoteAddr().String(), dst.RemoteAddr().String(), buffer[:n])
        }
    }
}

func (t *TCPProxy) extractJWTFromTCPPacket(data []byte) string {
    // Simple implementation - look for JWT token in first 512 bytes
    // In practice, this would be part of a custom protocol
    dataStr := string(data)
    if idx := strings.Index(dataStr, "JWT:"); idx != -1 {
        end := strings.Index(dataStr[idx+4:], "\n")
        if end == -1 {
            end = len(dataStr) - idx - 4
        }
        return strings.TrimSpace(dataStr[idx+4 : idx+4+end])
    }
    return ""
}

func (t *TCPProxy) extractTargetFromTCPPacket(data []byte) string {
    // Simple implementation - look for target host in packet
    dataStr := string(data)
    if idx := strings.Index(dataStr, "HOST:"); idx != -1 {
        end := strings.Index(dataStr[idx+5:], "\n")
        if end == -1 {
            end = len(dataStr) - idx - 5
        }
        return strings.TrimSpace(dataStr[idx+5 : idx+5+end])
    }
    return ""
}

// UDP Proxy Implementation  
func (u *UDPProxy) Start() {
    log.Info("Starting UDP proxy server")
    
    buffer := make([]byte, 65536)
    
    for {
        n, clientAddr, err := u.conn.ReadFromUDP(buffer)
        if err != nil {
            log.Errorf("UDP read error: %v", err)
            continue
        }
        
        // Handle packet in goroutine with authentication
        go u.handlePacket(buffer[:n], clientAddr)
    }
}

func (u *UDPProxy) handlePacket(data []byte, clientAddr *net.UDPAddr) {
    // Parse JWT token from UDP packet
    token := u.extractJWTFromUDPPacket(data)
    
    // Authenticate using JWT
    user, err := u.authProvider.ValidateToken(token)
    if err != nil {
        log.Errorf("UDP authentication failed: %v", err)
        return
    }
    
    log.Infof("UDP packet authenticated for user: %s", user.ID)
    
    // Extract target from packet
    targetHost := u.extractTargetFromUDPPacket(data)
    if targetHost == "" {
        log.Error("No target host found in UDP packet")
        return
    }
    
    // Connect to target
    targetAddr, err := net.ResolveUDPAddr("udp", targetHost)
    if err != nil {
        log.Errorf("Failed to resolve target %s: %v", targetHost, err)
        return
    }
    
    targetConn, err := net.DialUDP("udp", nil, targetAddr)
    if err != nil {
        log.Errorf("Failed to connect to target %s: %v", targetHost, err)
        return
    }
    defer targetConn.Close()
    
    // Forward packet to target
    if _, err := targetConn.Write(data); err != nil {
        log.Errorf("Failed to write to target: %v", err)
        return
    }
    
    // Mirror traffic if enabled
    if u.mirrorManager != nil {
        go u.mirrorManager.MirrorUDP(clientAddr.String(), targetHost, data)
    }
    
    // Read response and send back
    response := make([]byte, 65536)
    targetConn.SetReadDeadline(time.Now().Add(30 * time.Second))
    n, err := targetConn.Read(response)
    if err != nil {
        log.Errorf("Failed to read response from target: %v", err)
        return
    }
    
    // Send response back to client
    if _, err := u.conn.WriteToUDP(response[:n], clientAddr); err != nil {
        log.Errorf("Failed to write response to client: %v", err)
        return
    }
    
    // Mirror response if enabled
    if u.mirrorManager != nil {
        go u.mirrorManager.MirrorUDP(targetHost, clientAddr.String(), response[:n])
    }
}

func (u *UDPProxy) extractJWTFromUDPPacket(data []byte) string {
    // Similar to TCP implementation
    dataStr := string(data)
    if idx := strings.Index(dataStr, "JWT:"); idx != -1 {
        end := strings.Index(dataStr[idx+4:], "\n")
        if end == -1 {
            end = len(dataStr) - idx - 4
        }
        return strings.TrimSpace(dataStr[idx+4 : idx+4+end])
    }
    return ""
}

func (u *UDPProxy) extractTargetFromUDPPacket(data []byte) string {
    // Similar to TCP implementation
    dataStr := string(data)
    if idx := strings.Index(dataStr, "HOST:"); idx != -1 {
        end := strings.Index(dataStr[idx+5:], "\n")
        if end == -1 {
            end = len(dataStr) - idx - 5
        }
        return strings.TrimSpace(dataStr[idx+5 : idx+5+end])
    }
    return ""
}