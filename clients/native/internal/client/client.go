// Package client implements the core Tobogganing native client functionality.
//
// The client package provides:
// - WireGuard VPN tunnel management and lifecycle control
// - Manager service integration for configuration retrieval
// - Dual authentication with X.509 certificates and JWT tokens
// - Real-time connection monitoring and health checks
// - Automatic reconnection and failover capabilities
// - Certificate and configuration rotation with zero downtime
// - Cross-platform WireGuard interface management
// - Metrics collection and reporting to Manager service
//
// The client maintains persistent connections to headend servers and
// automatically handles authentication renewal, configuration updates,
// and network connectivity changes.
package client

import (
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "os"
    "os/exec"
    "runtime"
    "strings"
    "time"

    _ "github.com/golang-jwt/jwt/v5" // Used for JWT authentication
    "golang.zx2c4.com/wireguard/wgctrl"
    "golang.zx2c4.com/wireguard/wgctrl/wgtypes"

    "github.com/tobogganing/clients/native/internal/auth"
    "github.com/tobogganing/clients/native/internal/config"
    "github.com/tobogganing/clients/native/internal/overlay"
)

const (
    // Operating system constants
    platformWindows = "windows"
    platformDarwin  = "darwin"
    platformLinux   = "linux"

    // Connection state constants
    stateConnected    = "connected"
    stateDisconnected = "disconnected"
)

// wgDeviceClient abstracts the subset of wgctrl.Client used by Client,
// allowing tests to inject a mock without a real WireGuard kernel interface.
type wgDeviceClient interface {
    Device(name string) (*wgtypes.Device, error)
}

// cmdRunner abstracts exec.Cmd.CombinedOutput to allow test injection.
type cmdRunner func(cmd *exec.Cmd) ([]byte, error)

// defaultCmdRunner executes a command and returns its combined stdout+stderr.
func defaultCmdRunner(cmd *exec.Cmd) ([]byte, error) {
    return cmd.CombinedOutput()
}

// Client represents the Tobogganing native client
type Client struct {
    config          *config.Config
    auth            *auth.Manager
    wg              wgDeviceClient
    httpClient      *http.Client
    overlayProvider overlay.OverlayProvider

    // monitoringInterval controls how often healthCheck runs. Defaults to 30s;
    // tests may set it to a shorter value to exercise the ticker path.
    monitoringInterval time.Duration

    // runCmd executes an exec.Cmd and returns its output. Defaults to
    // defaultCmdRunner; tests may replace this to avoid invoking real binaries.
    runCmd cmdRunner

    // getInterfaceIPFn overrides interface IP lookup; nil means use the real implementation.
    // Tests set this to return a known IP without running system commands.
    getInterfaceIPFn func(name string) (string, error)

    // Current connection state
    clientID         string
    accessToken      string
    refreshToken     string
    headendURL       string
    wgPrivateKey     wgtypes.Key
    wgPublicKey      wgtypes.Key
    headendPublicKey wgtypes.Key
}

// ConnectionStatus represents the current connection status
type ConnectionStatus struct {
    State          string    `json:"state"`
    ClientID       string    `json:"client_id"`
    WireGuardIP    string    `json:"wireguard_ip"`
    HeadendURL     string    `json:"headend_url"`
    ConnectedSince time.Time `json:"connected_since"`
    BytesSent      int64     `json:"bytes_sent"`
    BytesReceived  int64     `json:"bytes_received"`
    LastHandshake  time.Time `json:"last_handshake"`
}

// New creates a new Tobogganing client
func New(cfg *config.Config) (*Client, error) {
    // Create WireGuard control client
    wgClient, err := wgctrl.New()
    if err != nil {
        return nil, fmt.Errorf("failed to create WireGuard client: %w", err)
    }

    // Create authentication manager
    authManager, err := auth.New(cfg.ManagerURL)
    if err != nil {
        return nil, fmt.Errorf("failed to create auth manager: %w", err)
    }

    return newWithDeps(cfg, wgClient, authManager), nil
}

// newWithDeps creates a Client with injected dependencies. Used by tests to avoid
// requiring a real WireGuard kernel interface or network-reachable auth service.
func newWithDeps(cfg *config.Config, wgDev wgDeviceClient, authMgr *auth.Manager) *Client {
    return &Client{
        config: cfg,
        auth:   authMgr,
        wg:     wgDev,
        httpClient: &http.Client{
            Timeout: 30 * time.Second,
        },
        runCmd: defaultCmdRunner,
    }
}

// Connect establishes connection to the Tobogganing network
func (c *Client) Connect(ctx context.Context) error {
    fmt.Println("Connecting to Tobogganing network...")

    // Step 1: Register with Manager Service
    if err := c.register(); err != nil {
        return fmt.Errorf("registration failed: %w", err)
    }

    // Step 2: Obtain JWT authentication
    if err := c.authenticate(); err != nil {
        return fmt.Errorf("authentication failed: %w", err)
    }

    // Step 3-4: Set up overlay based on configuration
    switch c.config.OverlayType {
    case "openziti":
        zitiProvider := overlay.NewOpenZitiProvider(overlay.OpenZitiConfig{
            IdentityFile: c.config.OpenZiti.IdentityFile,
            ServiceName:  c.config.OpenZiti.ServiceName,
        })
        zitiProvider.SetJWTToken(c.accessToken)
        c.overlayProvider = zitiProvider
    case "dual":
        wgProvider := overlay.NewWireGuardProvider(
            func() error {
                if err := c.setupWireGuard(); err != nil {
                    return err
                }
                return c.startWireGuard()
            },
            c.stopWireGuard,
        )
        zitiProvider := overlay.NewOpenZitiProvider(overlay.OpenZitiConfig{
            IdentityFile: c.config.OpenZiti.IdentityFile,
            ServiceName:  c.config.OpenZiti.ServiceName,
        })
        zitiProvider.SetJWTToken(c.accessToken)
        c.overlayProvider = overlay.NewDualProvider(wgProvider, zitiProvider)
    default: // "wireguard" or ""
        wgProvider := overlay.NewWireGuardProvider(
            func() error {
                if err := c.setupWireGuard(); err != nil {
                    return err
                }
                return c.startWireGuard()
            },
            c.stopWireGuard,
        )
        c.overlayProvider = wgProvider
    }

    if err := c.overlayProvider.Connect(ctx); err != nil {
        return fmt.Errorf("overlay connect failed: %w", err)
    }

    // Step 5: Start monitoring and keep-alive
    return c.runMonitoring(ctx)
}

// Disconnect safely disconnects from the Tobogganing network
func (c *Client) Disconnect() error {
    fmt.Println("Disconnecting from Tobogganing network...")

    // Disconnect overlay provider
    if c.overlayProvider != nil {
        if err := c.overlayProvider.Disconnect(context.Background()); err != nil {
            return fmt.Errorf("overlay disconnect failed: %w", err)
        }
    }

    // Clean up authentication tokens
    c.accessToken = ""
    c.refreshToken = ""
    c.clientID = ""

    fmt.Println("Disconnected successfully")
    return nil
}

// Status returns current connection status
func (c *Client) Status() (*ConnectionStatus, error) {
    status := &ConnectionStatus{
        State:    stateDisconnected,
        ClientID: c.clientID,
        HeadendURL: c.headendURL,
    }

    // Check WireGuard interface
    interfaceName := c.getWireGuardInterface()
    device, err := c.wg.Device(interfaceName)
    if err != nil {
        return status, nil // Interface not found, client is disconnected
    }

    status.State = stateConnected

    // Get interface IP
    ipFn := c.getInterfaceIPFn
    if ipFn == nil {
        ipFn = c.getInterfaceIP
    }
    if ip, err := ipFn(interfaceName); err == nil {
        status.WireGuardIP = ip
    }

    // Get peer statistics
    if len(device.Peers) > 0 {
        peer := device.Peers[0]
        status.BytesSent = peer.TransmitBytes
        status.BytesReceived = peer.ReceiveBytes
        status.LastHandshake = peer.LastHandshakeTime
    }

    return status, nil
}

func (c *Client) register() error {
    fmt.Println("Registering client with Manager Service...")

    if err := c.generateWireGuardKeys(); err != nil {
        return err
    }

    regReq := c.buildRegistrationRequest()
    
    regResp, err := c.sendRegistrationRequest(regReq)
    if err != nil {
        return err
    }

    return c.processRegistrationResponse(regResp)
}

func (c *Client) generateWireGuardKeys() error {
    privateKey, err := wgtypes.GeneratePrivateKey()
    if err != nil {
        return fmt.Errorf("failed to generate WireGuard keys: %w", err)
    }

    c.wgPrivateKey = privateKey
    c.wgPublicKey = privateKey.PublicKey()
    return nil
}

func (c *Client) buildRegistrationRequest() map[string]interface{} {
    clientName := c.config.ClientName
    if clientName == "" {
        hostname, _ := os.Hostname()
        clientName = fmt.Sprintf("native-client-%s-%s", runtime.GOOS, hostname)
    }

    return map[string]interface{}{
        "name":       clientName,
        "type":       "client_native",
        "public_key": c.wgPublicKey.String(),
        "location": map[string]interface{}{
            "platform":     runtime.GOOS,
            "architecture": runtime.GOARCH,
        },
    }
}

func (c *Client) sendRegistrationRequest(regReq map[string]interface{}) (*registrationResponse, error) {
    reqBody, _ := json.Marshal(regReq)
    
    registerURL := c.config.ManagerURL + "/api/v1/clients/register"
    req, err := http.NewRequest("POST", registerURL, strings.NewReader(string(reqBody)))
    if err != nil {
        return nil, err
    }

    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+c.config.APIKey)

    resp, err := c.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("registration request failed: %w", err)
    }
    defer func() {
        _ = resp.Body.Close()
    }()

    if resp.StatusCode != http.StatusOK {
        body, _ := io.ReadAll(resp.Body)
        return nil, fmt.Errorf("registration failed with status %d: %s", resp.StatusCode, body)
    }

    var regResp registrationResponse
    if err := json.NewDecoder(resp.Body).Decode(&regResp); err != nil {
        return nil, fmt.Errorf("failed to parse registration response: %w", err)
    }

    return &regResp, nil
}

func (c *Client) processRegistrationResponse(regResp *registrationResponse) error {
    c.clientID = regResp.ClientID
    c.headendURL = regResp.Cluster.HeadendURL
    c.config.APIKey = regResp.APIKey

    // Save certificates
    err := c.saveCertificates(regResp.Certificates.Cert, regResp.Certificates.Key, regResp.Certificates.CA)
    if err != nil {
        return fmt.Errorf("failed to save certificates: %w", err)
    }

    fmt.Printf("Registration successful - Client ID: %s\n", c.clientID)
    return nil
}

// registrationResponse represents the response from the manager service
type registrationResponse struct {
    ClientID     string `json:"client_id"`
    APIKey       string `json:"api_key"`
    Cluster      struct {
        HeadendURL string `json:"headend_url"`
    } `json:"cluster"`
    Certificates struct {
        Cert string `json:"cert"`
        Key  string `json:"key"`
        CA   string `json:"ca"`
    } `json:"certificates"`
}

func (c *Client) authenticate() error {
    fmt.Println("Authenticating with JWT...")

    authReq := map[string]interface{}{
        "node_id":   c.clientID,
        "node_type": "client_native",
        "api_key":   c.config.APIKey,
    }

    reqBody, _ := json.Marshal(authReq)
    
    req, err := http.NewRequest("POST", c.config.ManagerURL+"/api/v1/auth/token", strings.NewReader(string(reqBody)))
    if err != nil {
        return err
    }

    req.Header.Set("Content-Type", "application/json")

    resp, err := c.httpClient.Do(req)
    if err != nil {
        return fmt.Errorf("authentication request failed: %w", err)
    }
    defer func() {
        _ = resp.Body.Close()
    }()

    if resp.StatusCode != http.StatusOK {
        body, _ := io.ReadAll(resp.Body)
        return fmt.Errorf("authentication failed with status %d: %s", resp.StatusCode, body)
    }

    var authResp struct {
        AccessToken  string `json:"access_token"`
        RefreshToken string `json:"refresh_token"`
        ExpiresAt    string `json:"expires_at"`
    }

    if err := json.NewDecoder(resp.Body).Decode(&authResp); err != nil {
        return fmt.Errorf("failed to parse authentication response: %w", err)
    }

    c.accessToken = authResp.AccessToken
    c.refreshToken = authResp.RefreshToken

    fmt.Println("JWT authentication successful")
    return nil
}

func (c *Client) setupWireGuard() error {
    fmt.Println("Setting up WireGuard configuration...")

    wgReq := map[string]interface{}{
        "node_id":   c.clientID,
        "node_type": "client_native",
        "api_key":   c.config.APIKey,
    }

    reqBody, _ := json.Marshal(wgReq)
    
    keysURL := c.config.ManagerURL + "/api/v1/wireguard/keys"
    req, err := http.NewRequest("POST", keysURL, strings.NewReader(string(reqBody)))
    if err != nil {
        return err
    }

    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+c.accessToken)

    resp, err := c.httpClient.Do(req)
    if err != nil {
        return fmt.Errorf("WireGuard config request failed: %w", err)
    }
    defer func() {
        _ = resp.Body.Close()
    }()

    if resp.StatusCode != http.StatusOK {
        body, _ := io.ReadAll(resp.Body)
        return fmt.Errorf("WireGuard config failed with status %d: %s", resp.StatusCode, body)
    }

    var wgResp struct {
        WireGuard struct {
            PrivateKey  string `json:"private_key"`
            PublicKey   string `json:"public_key"`
            IPAddress   string `json:"ip_address"`
            NetworkCIDR string `json:"network_cidr"`
        } `json:"wireguard"`
    }

    if err := json.NewDecoder(resp.Body).Decode(&wgResp); err != nil {
        return fmt.Errorf("failed to parse WireGuard response: %w", err)
    }

    // Update WireGuard keys if provided by server
    if wgResp.WireGuard.PrivateKey != "" {
        key, err := wgtypes.ParseKey(wgResp.WireGuard.PrivateKey)
        if err == nil {
            c.wgPrivateKey = key
            c.wgPublicKey = key.PublicKey()
        }
    }

    // Create WireGuard configuration file
    return c.createWireGuardConfig(wgResp.WireGuard.IPAddress, wgResp.WireGuard.NetworkCIDR)
}

func (c *Client) createWireGuardConfig(ipAddress, networkCIDR string) error {
    configPath := c.getWireGuardConfigPath()

    // Extract headend connection details
    headendHost := strings.TrimPrefix(c.headendURL, "https://")
    headendHost = strings.TrimPrefix(headendHost, "http://")
    headendHost = strings.Split(headendHost, ":")[0]

    config := fmt.Sprintf(`[Interface]
Address = %s
PrivateKey = %s
DNS = 10.200.0.1

[Peer]
PublicKey = %s
Endpoint = %s:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
`, ipAddress, c.wgPrivateKey.String(), c.headendPublicKey.String(), headendHost)

    return os.WriteFile(configPath, []byte(config), 0600)
}

// wireGuardUpCmd returns the OS-appropriate command to bring up a WireGuard config.
// Returns an error if goos is not a supported platform.
func wireGuardUpCmd(goos, configPath string) (*exec.Cmd, error) {
    switch goos {
    case platformDarwin, platformLinux:
        return exec.Command("wg-quick", "up", configPath), nil // #nosec G204
    case platformWindows:
        return exec.Command("wg-quick.exe", "up", configPath), nil // #nosec G204
    default:
        return nil, fmt.Errorf("unsupported platform: %s", goos)
    }
}

// wireGuardDownCmd returns the OS-appropriate command to bring down a WireGuard config.
// Returns an error if goos is not a supported platform.
func wireGuardDownCmd(goos, configPath string) (*exec.Cmd, error) {
    switch goos {
    case platformDarwin, platformLinux:
        return exec.Command("wg-quick", "down", configPath), nil // #nosec G204
    case platformWindows:
        return exec.Command("wg-quick.exe", "down", configPath), nil // #nosec G204
    default:
        return nil, fmt.Errorf("unsupported platform: %s", goos)
    }
}

func (c *Client) startWireGuard() error {
    fmt.Println("Starting WireGuard interface...")

    interfaceName := c.getWireGuardInterface()
    configPath := c.getWireGuardConfigPath()

    cmd, err := wireGuardUpCmd(runtime.GOOS, configPath)
    if err != nil {
        return err
    }

    if output, err := c.runCmd(cmd); err != nil {
        return fmt.Errorf("failed to start WireGuard: %v, output: %s", err, output)
    }

    fmt.Printf("WireGuard interface %s started successfully\n", interfaceName)
    return nil
}

func (c *Client) stopWireGuard() error {
    interfaceName := c.getWireGuardInterface()
    configPath := c.getWireGuardConfigPath()

    cmd, err := wireGuardDownCmd(runtime.GOOS, configPath)
    if err != nil {
        return err
    }

    if output, err := c.runCmd(cmd); err != nil {
        return fmt.Errorf("failed to stop WireGuard: %v, output: %s", err, output)
    }

    fmt.Printf("WireGuard interface %s stopped successfully\n", interfaceName)
    return nil
}

func (c *Client) runMonitoring(ctx context.Context) error {
    fmt.Println("Starting connection monitoring...")

    interval := c.monitoringInterval
    if interval <= 0 {
        interval = 30 * time.Second
    }
    ticker := time.NewTicker(interval)
    defer ticker.Stop()

    for {
        select {
        case <-ctx.Done():
            fmt.Println("Monitoring stopped")
            return c.Disconnect()
        case <-ticker.C:
            if err := c.healthCheck(); err != nil {
                fmt.Printf("Health check failed: %v\n", err)
            }
        }
    }
}

func (c *Client) healthCheck() error {
    // Check WireGuard interface
    interfaceName := c.getWireGuardInterface()
    if _, err := c.wg.Device(interfaceName); err != nil {
        return fmt.Errorf("WireGuard interface down: %w", err)
    }

    // Perform authentication checks
    if err := c.checkAuthentication(); err != nil {
        return fmt.Errorf("authentication check failed: %w", err)
    }

    return nil
}

func (c *Client) checkAuthentication() error {
    // Check JWT token expiry and refresh if needed
    // For now, this is a placeholder for proper authentication checks
    return nil
}

const (
	defaultWireGuardInterface = "wg0"
	darwinWireGuardInterface  = "utun1"
	windowsWireGuardInterface = "tobogganing"
)

// wireGuardInterfaceForOS returns the WireGuard interface name for the given OS.
func wireGuardInterfaceForOS(goos string) string {
    switch goos {
    case platformDarwin:
        return darwinWireGuardInterface
    case platformWindows:
        return windowsWireGuardInterface
    default:
        return defaultWireGuardInterface
    }
}

// wireGuardConfigPathForOS returns the WireGuard config file path for the given OS and interface.
func wireGuardConfigPathForOS(goos, interfaceName string) string {
    switch goos {
    case platformDarwin:
        return fmt.Sprintf("/usr/local/etc/wireguard/%s.conf", interfaceName)
    case platformWindows:
        return fmt.Sprintf("C:\\Program Files\\WireGuard\\Data\\Configurations\\%s.conf", interfaceName)
    default:
        return fmt.Sprintf("/etc/wireguard/%s.conf", interfaceName)
    }
}

// interfaceIPCmd returns the OS-appropriate command to query interface addresses.
func interfaceIPCmd(goos, interfaceName string) (*exec.Cmd, error) {
    switch goos {
    case platformDarwin, platformLinux:
        return exec.Command("ip", "addr", "show", interfaceName), nil // #nosec G204
    case platformWindows:
        return exec.Command("netsh", "interface", "ip", "show", "addresses", interfaceName), nil // #nosec G204
    default:
        return nil, fmt.Errorf("unsupported platform")
    }
}

// certificateDirForOS returns the certificate directory for the given OS.
func certificateDirForOS(goos string) string {
    switch goos {
    case platformWindows:
        return os.Getenv("APPDATA") + "\\Tobogganing\\certs"
    default:
        return os.Getenv("HOME") + "/.tobogganing/certs"
    }
}

func (c *Client) getWireGuardInterface() string {
    return wireGuardInterfaceForOS(runtime.GOOS)
}

func (c *Client) getWireGuardConfigPath() string {
    interfaceName := c.getWireGuardInterface()
    return wireGuardConfigPathForOS(runtime.GOOS, interfaceName)
}

func (c *Client) getInterfaceIP(interfaceName string) (string, error) {
    cmd, err := interfaceIPCmd(runtime.GOOS, interfaceName)
    if err != nil {
        return "", err
    }

    output, err := cmd.Output()
    if err != nil {
        return "", err
    }

    // Parse IP from output (basic implementation)
    lines := strings.Split(string(output), "\n")
    for _, line := range lines {
        if strings.Contains(line, "inet ") && !strings.Contains(line, "inet6") {
            fields := strings.Fields(line)
            for i, field := range fields {
                if field == "inet" && i+1 < len(fields) {
                    return strings.Split(fields[i+1], "/")[0], nil
                }
            }
        }
    }

    return "", fmt.Errorf("IP address not found")
}

func (c *Client) saveCertificates(cert, key, ca string) error {
    certDir := c.getCertificateDir()
    if err := os.MkdirAll(certDir, 0700); err != nil {
        return err
    }

    if err := os.WriteFile(certDir+"/client.crt", []byte(cert), 0600); err != nil {
        return err
    }

    if err := os.WriteFile(certDir+"/client.key", []byte(key), 0600); err != nil {
        return err
    }

    if err := os.WriteFile(certDir+"/ca.crt", []byte(ca), 0600); err != nil {
        return err
    }

    return nil
}

func (c *Client) getCertificateDir() string {
    return certificateDirForOS(runtime.GOOS)
}