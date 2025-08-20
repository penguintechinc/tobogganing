// Package main implements the SASEWaddle headend proxy server.
//
// The headend proxy is a high-performance, multi-protocol proxy server that:
// - Terminates WireGuard VPN connections from clients
// - Provides HTTP/HTTPS/TCP/UDP proxying with authentication
// - Implements comprehensive firewall rules and traffic filtering
// - Supports traffic mirroring to external IDS/IPS systems
// - Integrates with external identity providers (SAML2/OAuth2)
// - Provides real-time metrics and monitoring capabilities
//
// The proxy server is designed for enterprise SASE deployments with
// support for multiple datacenters, high availability, and scalability.
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
    "github.com/sasewaddle/headend/proxy/ports"
    "github.com/sasewaddle/headend/proxy/syslog"
)

type ProxyServer struct {
    router          *gin.Engine
    httpServer      *http.Server
    tcpProxy        *TCPProxy
    udpProxy        *UDPProxy
    portManager     *ports.PortManager
    authProvider    auth.Provider
    mirrorManager   *mirror.Manager
    firewallManager *firewall.Manager
    syslogLogger    *syslog.SyslogLogger
    wgRouter        *WireGuardRouter
    proxies         map[string]*httputil.ReverseProxy
    mu              sync.RWMutex
}

// TCPProxy handles raw TCP traffic with JWT authentication
type TCPProxy struct {
    listener        net.Listener
    authProvider    auth.Provider
    mirrorManager   *mirror.Manager
    firewallManager *firewall.Manager
    syslogLogger    *syslog.SyslogLogger
    wgRouter        *WireGuardRouter
}

// UDPProxy handles raw UDP traffic with JWT authentication  
type UDPProxy struct {
    conn            *net.UDPConn
    authProvider    auth.Provider
    mirrorManager   *mirror.Manager
    firewallManager *firewall.Manager
    syslogLogger    *syslog.SyslogLogger
    wgRouter        *WireGuardRouter
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
    viper.SetDefault("firewall.enabled", true)
    viper.SetDefault("firewall.manager_url", "http://manager:8000")
    viper.SetDefault("firewall.auth_token", "headend-server-token")
    viper.SetDefault("syslog.enabled", false)
    viper.SetDefault("syslog.host", "")
    viper.SetDefault("syslog.port", "514")
    viper.SetDefault("syslog.facility", "local0")
    viper.SetDefault("syslog.tag", "sasewaddle-headend")
    viper.SetDefault("ports.dynamic_enabled", true)
    viper.SetDefault("ports.headend_id", "")
    viper.SetDefault("ports.cluster_id", "default")
    viper.SetDefault("ports.refresh_interval", "60s")

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

    // Initialize WireGuard router for peer-to-peer and internet routing
    wgInterface := viper.GetString("wireguard.interface")
    wgNetwork := viper.GetString("wireguard.network")
    headendIP := "10.200.0.1" // Headend's IP in WireGuard network
    
    s.wgRouter, err = NewWireGuardRouter(wgInterface, wgNetwork, headendIP)
    if err != nil {
        log.Warnf("Failed to initialize WireGuard router: %v (continuing without WG routing)", err)
        s.wgRouter = nil
    } else {
        log.Info("WireGuard-aware routing enabled")
    }

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

    // Initialize firewall manager if enabled
    if viper.GetBool("firewall.enabled") {
        managerURL := viper.GetString("firewall.manager_url")
        authToken := viper.GetString("firewall.auth_token")
        
        s.firewallManager = firewall.NewManager(managerURL, authToken)
        if err := s.firewallManager.Start(); err != nil {
            return fmt.Errorf("failed to start firewall manager: %w", err)
        }
        log.Info("Firewall manager enabled and started")
    } else {
        log.Info("Firewall manager disabled")
    }

    // Initialize syslog logger if enabled
    if viper.GetBool("syslog.enabled") {
        syslogHost := viper.GetString("syslog.host")
        syslogPort := viper.GetString("syslog.port")
        
        if syslogHost != "" {
            s.syslogLogger = syslog.NewSyslogLogger(syslogHost, syslogPort)
            if err := s.syslogLogger.Start(); err != nil {
                return fmt.Errorf("failed to start syslog logger: %w", err)
            }
            log.Infof("Syslog logging enabled - sending to %s:%s", syslogHost, syslogPort)
        } else {
            log.Warn("Syslog enabled but no host configured")
        }
    } else {
        log.Info("Syslog logging disabled")
    }

    // Initialize dynamic port manager if enabled
    if viper.GetBool("ports.dynamic_enabled") {
        headendID := viper.GetString("ports.headend_id")
        clusterID := viper.GetString("ports.cluster_id")
        managerURL := viper.GetString("firewall.manager_url")
        authToken := viper.GetString("firewall.auth_token")
        
        if headendID == "" {
            log.Warn("Dynamic ports enabled but no headend_id configured, using hostname")
            if hostname, err := os.Hostname(); err == nil {
                headendID = hostname
            } else {
                headendID = "headend-" + fmt.Sprintf("%d", time.Now().Unix())
            }
        }
        
        s.portManager = ports.NewPortManager()
        
        // Set up connection handlers
        s.portManager.SetConnectionHandlers(
            s.handleDynamicTCPConnection,
            s.handleDynamicUDPPacket,
        )
        
        // Fetch initial configuration
        configClient := ports.NewConfigClient(managerURL, authToken, headendID, clusterID)
        config, err := configClient.FetchConfig()
        if err != nil {
            log.Errorf("Failed to fetch initial port config: %v", err)
            log.Info("Continuing with static port configuration")
        } else {
            // Parse and apply the configuration
            if err := s.portManager.ParsePortRanges(config.TCPRanges, config.UDPRanges); err != nil {
                log.Errorf("Failed to parse port ranges: %v", err)
            } else {
                if err := s.portManager.StartListening(); err != nil {
                    log.Errorf("Failed to start dynamic port listeners: %v", err)
                } else {
                    log.Infof("Dynamic port manager started with %d listeners", s.portManager.GetListenerCount())
                    
                    // Start periodic config refresh
                    go s.refreshPortConfig(configClient)
                }
            }
        }
    } else {
        log.Info("Dynamic port management disabled")
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
    syslogQueueDepth := 0
    if s.syslogLogger != nil {
        syslogQueueDepth = s.syslogLogger.GetQueueDepth()
    }
    
    portListenerCount := 0
    if s.portManager != nil {
        portListenerCount = s.portManager.GetListenerCount()
    }
    
    c.JSON(http.StatusOK, gin.H{
        "status": "healthy",
        "service": "headend-proxy",
        "mirror_enabled": s.mirrorManager != nil,
        "firewall_enabled": s.firewallManager != nil,
        "syslog_enabled": s.syslogLogger != nil && s.syslogLogger.IsEnabled(),
        "syslog_queue_depth": syslogQueueDepth,
        "dynamic_ports_enabled": s.portManager != nil,
        "port_listeners_count": portListenerCount,
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

    user := c.MustGet("user").(auth.User)
    sourceIP := c.ClientIP()
    method := c.Request.Method
    path := c.Request.URL.Path
    userAgent := c.GetHeader("User-Agent")
    requestID := c.GetHeader("X-Request-ID")
    
    // Check firewall rules if firewall manager is enabled
    allowed := true
    if s.firewallManager != nil {
        allowed = s.firewallManager.CheckAccess(user.ID, targetHost)
        
        if !allowed {
            log.Warnf("Firewall blocked access for user %s to %s", user.ID, targetHost)
            
            // Log denied access to syslog
            if s.syslogLogger != nil {
                s.syslogLogger.LogHTTPAccess(user.ID, user.Name, sourceIP, targetHost, method, path, userAgent, requestID, 403, 0, false)
            }
            
            c.JSON(http.StatusForbidden, gin.H{"error": "Access denied by firewall policy"})
            return
        }
        
        log.Debugf("Firewall allowed access for user %s to %s", user.ID, targetHost)
    }

    // Get or create proxy for target
    proxy := s.getOrCreateProxy(targetHost)

    // Create response writer wrapper for monitoring
    wrapper := &responseWriterWrapper{
        ResponseWriter: c.Writer,
        mirrorManager:  s.mirrorManager,
        syslogLogger:   s.syslogLogger,
        request:        c.Request,
        user:           user,
        targetHost:     targetHost,
        sourceIP:       sourceIP,
        method:         method,
        path:           path,
        userAgent:      userAgent,
        requestID:      requestID,
    }
    c.Writer = wrapper

    // Proxy the request
    proxy.ServeHTTP(c.Writer, c.Request)
    
    // Ensure logging and mirroring happens
    if wrapper, ok := c.Writer.(*responseWriterWrapper); ok {
        wrapper.Flush()
    }
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
        listener:        listener,
        authProvider:    s.authProvider,
        mirrorManager:   s.mirrorManager,
        firewallManager: s.firewallManager,
        syslogLogger:    s.syslogLogger,
        wgRouter:        s.wgRouter,
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
        conn:            conn,
        authProvider:    s.authProvider,
        mirrorManager:   s.mirrorManager,
        firewallManager: s.firewallManager,
        syslogLogger:    s.syslogLogger,
        wgRouter:        s.wgRouter,
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
        
        if s.firewallManager != nil {
            s.firewallManager.Stop()
        }
        
        if s.syslogLogger != nil {
            s.syslogLogger.Stop()
        }
        
        if s.portManager != nil {
            s.portManager.Stop()
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

type responseWriterWrapper struct {
    gin.ResponseWriter
    mirrorManager *mirror.Manager
    syslogLogger  *syslog.SyslogLogger
    request       *http.Request
    user          auth.User
    targetHost    string
    sourceIP      string
    method        string
    path          string
    userAgent     string
    requestID     string
    statusCode    int
    bytesWritten  int64
    written       []byte
}

func (w *responseWriterWrapper) WriteHeader(code int) {
    w.statusCode = code
    w.ResponseWriter.WriteHeader(code)
}

func (w *responseWriterWrapper) Write(data []byte) (int, error) {
    // Only store data for mirroring if mirror is enabled
    if w.mirrorManager != nil {
        w.written = append(w.written, data...)
    }
    w.bytesWritten += int64(len(data))
    
    // Mirror and log are handled by worker queues for performance
    // Just track the data here, actual work is deferred
    
    return w.ResponseWriter.Write(data)
}

// Flush handles final logging and mirroring when the response is complete
func (w *responseWriterWrapper) Flush() {
    // Send to mirror asynchronously if enabled
    if w.mirrorManager != nil && len(w.written) > 0 {
        go w.mirrorManager.MirrorHTTP(w.request, w.statusCode, w.written)
    }
    
    // Log to syslog - uses internal worker queue for performance
    if w.syslogLogger != nil {
        w.syslogLogger.LogHTTPAccess(
            w.user.ID,
            w.user.Name,
            w.sourceIP,
            w.targetHost,
            w.method,
            w.path,
            w.userAgent,
            w.requestID,
            w.statusCode,
            w.bytesWritten,
            true, // allowed (we wouldn't get here if not allowed)
        )
    }
    
    // Call the underlying Flush if available
    if flusher, ok := w.ResponseWriter.(http.Flusher); ok {
        flusher.Flush()
    }
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
    
    // Check firewall rules if firewall manager is enabled
    allowed := true
    if t.firewallManager != nil {
        allowed = t.firewallManager.CheckAccess(user.ID, targetHost)
        
        if !allowed {
            log.Warnf("Firewall blocked TCP connection for user %s to %s", user.ID, targetHost)
            
            // Log denied access to syslog
            if t.syslogLogger != nil {
                t.syslogLogger.LogTCPAccess(user.ID, user.Name, clientConn.RemoteAddr().String(), targetHost, false)
            }
            
            return
        }
        log.Debugf("Firewall allowed TCP connection for user %s to %s", user.ID, targetHost)
    }
    
    // Log allowed access to syslog
    if t.syslogLogger != nil {
        t.syslogLogger.LogTCPAccess(user.ID, user.Name, clientConn.RemoteAddr().String(), targetHost, true)
    }
    
    // Use WireGuard router if available for intelligent routing
    if t.wgRouter != nil {
        log.Infof("Using WireGuard router for TCP traffic to %s", targetHost)
        if err := t.wgRouter.RouteTraffic(targetHost, clientConn); err != nil {
            log.Errorf("WireGuard routing failed for %s: %v", targetHost, err)
        }
        return
    }
    
    // Fallback to direct connection
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
    
    // Check firewall rules if firewall manager is enabled
    allowed := true
    if u.firewallManager != nil {
        allowed = u.firewallManager.CheckAccess(user.ID, targetHost)
        
        if !allowed {
            log.Warnf("Firewall blocked UDP packet for user %s to %s", user.ID, targetHost)
            
            // Log denied access to syslog
            if u.syslogLogger != nil {
                u.syslogLogger.LogUDPAccess(user.ID, user.Name, clientAddr.String(), targetHost, false)
            }
            
            return
        }
        log.Debugf("Firewall allowed UDP packet for user %s to %s", user.ID, targetHost)
    }
    
    // Log allowed access to syslog
    if u.syslogLogger != nil {
        u.syslogLogger.LogUDPAccess(user.ID, user.Name, clientAddr.String(), targetHost, true)
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

// refreshPortConfig periodically fetches updated port configuration from the Manager
func (s *ProxyServer) refreshPortConfig(configClient *ports.ConfigClient) {
	refreshInterval, err := time.ParseDuration(viper.GetString("ports.refresh_interval"))
	if err != nil {
		refreshInterval = 60 * time.Second
	}
	
	ticker := time.NewTicker(refreshInterval)
	defer ticker.Stop()
	
	for {
		select {
		case <-ticker.C:
			config, err := configClient.FetchConfig()
			if err != nil {
				log.Errorf("Failed to refresh port config: %v", err)
				continue
			}
			
			// Validate the configuration
			if err := configClient.ValidateConfig(config); err != nil {
				log.Errorf("Invalid port config received: %v", err)
				continue
			}
			
			// Update port manager configuration
			if err := s.updatePortConfiguration(config); err != nil {
				log.Errorf("Failed to update port configuration: %v", err)
			} else {
				log.Infof("Updated port configuration: TCP=%s, UDP=%s", config.TCPRanges, config.UDPRanges)
			}
		}
	}
}

// updatePortConfiguration applies new port configuration to the port manager
func (s *ProxyServer) updatePortConfiguration(config *ports.PortConfig) error {
	// Stop current listeners
	s.portManager.Stop()
	
	// Create new port manager with updated config
	s.portManager = ports.NewPortManager()
	s.portManager.SetConnectionHandlers(
		s.handleDynamicTCPConnection,
		s.handleDynamicUDPPacket,
	)
	
	// Parse and apply new configuration
	if err := s.portManager.ParsePortRanges(config.TCPRanges, config.UDPRanges); err != nil {
		return fmt.Errorf("failed to parse port ranges: %w", err)
	}
	
	if err := s.portManager.StartListening(); err != nil {
		return fmt.Errorf("failed to start listeners: %w", err)
	}
	
	return nil
}

// handleDynamicTCPConnection handles new TCP connections on dynamically configured ports
func (s *ProxyServer) handleDynamicTCPConnection(conn net.Conn, port int, protocol string) {
	defer conn.Close()
	
	log.Debugf("New TCP connection on dynamic port %d from %s", port, conn.RemoteAddr())
	
	// Read first packet to extract authentication and target information
	buffer := make([]byte, 4096)
	n, err := conn.Read(buffer)
	if err != nil {
		log.Errorf("Failed to read from TCP connection on port %d: %v", port, err)
		return
	}
	
	// Extract JWT token and target from the packet
	token := s.extractJWTFromTCPPacket(buffer[:n])
	targetHost := s.extractTargetFromTCPPacket(buffer[:n])
	
	if token == "" || targetHost == "" {
		log.Errorf("Missing authentication or target in TCP packet on port %d", port)
		return
	}
	
	// Authenticate using JWT
	user, err := s.authProvider.ValidateToken(token)
	if err != nil {
		log.Errorf("Authentication failed for TCP connection on port %d: %v", port, err)
		return
	}
	
	log.Infof("Authenticated TCP connection on port %d for user: %s to %s", port, user.ID, targetHost)
	
	// Check firewall rules
	allowed := true
	if s.firewallManager != nil {
		allowed = s.firewallManager.CheckAccess(user.ID, targetHost)
		if !allowed {
			log.Warnf("Firewall blocked TCP connection on port %d for user %s to %s", port, user.ID, targetHost)
			
			// Log denied access to syslog
			if s.syslogLogger != nil {
				s.syslogLogger.LogTCPAccess(user.ID, user.Name, conn.RemoteAddr().String(), targetHost, false)
			}
			return
		}
	}
	
	// Log allowed access to syslog
	if s.syslogLogger != nil {
		s.syslogLogger.LogTCPAccess(user.ID, user.Name, conn.RemoteAddr().String(), targetHost, true)
	}
	
	// Use WireGuard router if available for intelligent routing
	if s.wgRouter != nil {
		log.Infof("Using WireGuard router for dynamic TCP traffic to %s on port %d", targetHost, port)
		if err := s.wgRouter.RouteTraffic(targetHost, conn); err != nil {
			log.Errorf("WireGuard routing failed for %s on port %d: %v", targetHost, port, err)
		}
		return
	}
	
	// Fallback to direct connection
	targetConn, err := net.Dial("tcp", targetHost)
	if err != nil {
		log.Errorf("Failed to connect to target %s from port %d: %v", targetHost, port, err)
		return
	}
	defer targetConn.Close()
	
	// Send original packet to target
	if _, err := targetConn.Write(buffer[:n]); err != nil {
		log.Errorf("Failed to write to target: %v", err)
		return
	}
	
	// Mirror traffic if enabled
	if s.mirrorManager != nil {
		go s.mirrorManager.MirrorTCP(conn.RemoteAddr().String(), targetHost, buffer[:n])
	}
	
	// Bidirectional proxy
	go s.proxyTCPData(conn, targetConn, fmt.Sprintf("client->target (port %d)", port))
	s.proxyTCPData(targetConn, conn, fmt.Sprintf("target->client (port %d)", port))
}

// handleDynamicUDPPacket handles new UDP packets on dynamically configured ports
func (s *ProxyServer) handleDynamicUDPPacket(data []byte, addr *net.UDPAddr, port int) {
	log.Debugf("New UDP packet on dynamic port %d from %s", port, addr)
	
	// Extract JWT token and target from the packet
	token := s.extractJWTFromUDPPacket(data)
	targetHost := s.extractTargetFromUDPPacket(data)
	
	if token == "" || targetHost == "" {
		log.Errorf("Missing authentication or target in UDP packet on port %d", port)
		return
	}
	
	// Authenticate using JWT
	user, err := s.authProvider.ValidateToken(token)
	if err != nil {
		log.Errorf("Authentication failed for UDP packet on port %d: %v", port, err)
		return
	}
	
	log.Infof("Authenticated UDP packet on port %d for user: %s to %s", port, user.ID, targetHost)
	
	// Check firewall rules
	allowed := true
	if s.firewallManager != nil {
		allowed = s.firewallManager.CheckAccess(user.ID, targetHost)
		if !allowed {
			log.Warnf("Firewall blocked UDP packet on port %d for user %s to %s", port, user.ID, targetHost)
			
			// Log denied access to syslog
			if s.syslogLogger != nil {
				s.syslogLogger.LogUDPAccess(user.ID, user.Name, addr.String(), targetHost, false)
			}
			return
		}
	}
	
	// Log allowed access to syslog
	if s.syslogLogger != nil {
		s.syslogLogger.LogUDPAccess(user.ID, user.Name, addr.String(), targetHost, true)
	}
	
	// Connect to target
	targetAddr, err := net.ResolveUDPAddr("udp", targetHost)
	if err != nil {
		log.Errorf("Failed to resolve target %s from port %d: %v", targetHost, port, err)
		return
	}
	
	targetConn, err := net.DialUDP("udp", nil, targetAddr)
	if err != nil {
		log.Errorf("Failed to connect to target %s from port %d: %v", targetHost, port, err)
		return
	}
	defer targetConn.Close()
	
	// Forward packet to target
	if _, err := targetConn.Write(data); err != nil {
		log.Errorf("Failed to write to target: %v", err)
		return
	}
	
	// Mirror traffic if enabled
	if s.mirrorManager != nil {
		go s.mirrorManager.MirrorUDP(addr.String(), targetHost, data)
	}
	
	// Read response and send back (UDP response handling would need port manager support)
	response := make([]byte, 65536)
	targetConn.SetReadDeadline(time.Now().Add(30 * time.Second))
	n, err := targetConn.Read(response)
	if err != nil {
		log.Debugf("No response from target %s (normal for UDP)", targetHost)
		return
	}
	
	log.Debugf("Received %d bytes response from target %s", n, targetHost)
}

// proxyTCPData proxies data between two TCP connections
func (s *ProxyServer) proxyTCPData(src, dst net.Conn, direction string) {
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
		if s.mirrorManager != nil {
			go s.mirrorManager.MirrorTCP(src.RemoteAddr().String(), dst.RemoteAddr().String(), buffer[:n])
		}
	}
}

// Helper methods for extracting data from packets (reuse existing implementations)
func (s *ProxyServer) extractJWTFromTCPPacket(data []byte) string {
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

func (s *ProxyServer) extractTargetFromTCPPacket(data []byte) string {
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

func (s *ProxyServer) extractJWTFromUDPPacket(data []byte) string {
	return s.extractJWTFromTCPPacket(data) // Same implementation
}

func (s *ProxyServer) extractTargetFromUDPPacket(data []byte) string {
	return s.extractTargetFromTCPPacket(data) // Same implementation
}