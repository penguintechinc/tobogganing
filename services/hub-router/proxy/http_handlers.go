// Package main implements the SASEWaddle headend proxy server.
package main

import (
	"crypto/subtle"
	"crypto/tls"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	log "github.com/sirupsen/logrus"
	"github.com/spf13/viper"

	"github.com/tobogganing/headend/proxy/auth"
	"github.com/tobogganing/headend/proxy/middleware"
	"github.com/tobogganing/headend/proxy/mirror"
	"github.com/tobogganing/headend/proxy/syslog"
)

// tokensEqual is a constant-time comparison that always denies an empty expected token.
func tokensEqual(got, expected string) bool {
	if expected == "" {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(got), []byte(expected)) == 1
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
		"status":                "healthy",
		"service":               "headend-proxy",
		"mirror_enabled":        s.mirrorManager != nil,
		"firewall_enabled":      s.firewallManager != nil,
		"syslog_enabled":        s.syslogLogger != nil && s.syslogLogger.IsEnabled(),
		"syslog_queue_depth":    syslogQueueDepth,
		"dynamic_ports_enabled": s.portManager != nil,
		"port_listeners_count":  portListenerCount,
		"auth_provider":         s.authProvider != nil,
		"tcp_proxy":             s.tcpProxy != nil,
		"udp_proxy":             s.udpProxy != nil,
	})
}

func (s *ProxyServer) healthzHandler(c *gin.Context) {
	// Kubernetes-style health check
	healthy := s.authProvider != nil

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
		token := strings.TrimPrefix(authHeader, "Bearer ")
		expectedToken := viper.GetString("metrics.auth_token")
		if tokensEqual(token, expectedToken) {
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
	var allowed bool
	if s.firewallManager != nil {
		allowed = s.firewallManager.CheckAccess(user.ID, targetHost)
	} else {
		allowed = true
	}

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
			MinVersion:         tls.VersionTLS12,
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
