// Package main implements the SASEWaddle headend proxy server.
package main

import (
	"fmt"
	"net"
	"net/http"
	"net/http/httputil"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	log "github.com/sirupsen/logrus"
	"github.com/spf13/viper"

	"github.com/tobogganing/headend/proxy/auth"
	"github.com/tobogganing/headend/proxy/firewall"
	"github.com/tobogganing/headend/proxy/mirror"
	"github.com/tobogganing/headend/proxy/ports"
	"github.com/tobogganing/headend/proxy/syslog"
)

// ProxyServer is the main server structure for the headend proxy.
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
