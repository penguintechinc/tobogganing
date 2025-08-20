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

    "github.com/golang-jwt/jwt/v5"
    "golang.zx2c4.com/wireguard/wgctrl"
    "golang.zx2c4.com/wireguard/wgctrl/wgtypes"

    "github.com/sasewaddle/native-client/internal/config"
    "github.com/sasewaddle/native-client/internal/auth"
)

// Client represents the SASEWaddle native client
type Client struct {
    config       *config.Config
    auth         *auth.Manager
    wg           *wgctrl.Client
    httpClient   *http.Client
    
    // Current connection state
    clientID     string
    accessToken  string
    refreshToken string
    headendURL   string
    wgPrivateKey wgtypes.Key
    wgPublicKey  wgtypes.Key
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

// New creates a new SASEWaddle client
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

    client := &Client{
        config: cfg,
        auth:   authManager,
        wg:     wgClient,
        httpClient: &http.Client{
            Timeout: 30 * time.Second,
        },
    }

    return client, nil
}

// Connect establishes connection to the SASEWaddle network
func (c *Client) Connect(ctx context.Context) error {
    fmt.Println("Connecting to SASEWaddle network...")

    // Step 1: Register with Manager Service
    if err := c.register(); err != nil {
        return fmt.Errorf("registration failed: %w", err)
    }

    // Step 2: Obtain JWT authentication
    if err := c.authenticate(); err != nil {
        return fmt.Errorf("authentication failed: %w", err)
    }

    // Step 3: Get WireGuard configuration
    if err := c.setupWireGuard(); err != nil {
        return fmt.Errorf("WireGuard setup failed: %w", err)
    }

    // Step 4: Start WireGuard interface
    if err := c.startWireGuard(); err != nil {
        return fmt.Errorf("WireGuard start failed: %w", err)
    }

    // Step 5: Start monitoring and keep-alive
    return c.runMonitoring(ctx)
}

// Disconnect safely disconnects from the SASEWaddle network
func (c *Client) Disconnect() error {
    fmt.Println("Disconnecting from SASEWaddle network...")

    // Stop WireGuard interface
    if err := c.stopWireGuard(); err != nil {
        return fmt.Errorf("WireGuard stop failed: %w", err)
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
        State:    "disconnected",
        ClientID: c.clientID,
        HeadendURL: c.headendURL,
    }

    // Check WireGuard interface
    interfaceName := c.getWireGuardInterface()
    device, err := c.wg.Device(interfaceName)
    if err != nil {
        return status, nil // Interface not found, client is disconnected
    }

    status.State = "connected"
    
    // Get interface IP
    if ip, err := c.getInterfaceIP(interfaceName); err == nil {
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

    // Generate WireGuard keys
    privateKey, err := wgtypes.GeneratePrivateKey()
    if err != nil {
        return fmt.Errorf("failed to generate WireGuard keys: %w", err)
    }

    c.wgPrivateKey = privateKey
    c.wgPublicKey = privateKey.PublicKey()

    // Prepare registration request
    clientName := c.config.ClientName
    if clientName == "" {
        hostname, _ := os.Hostname()
        clientName = fmt.Sprintf("native-client-%s-%s", runtime.GOOS, hostname)
    }

    regReq := map[string]interface{}{
        "name":       clientName,
        "type":       "client_native",
        "public_key": c.wgPublicKey.String(),
        "location": map[string]interface{}{
            "platform":     runtime.GOOS,
            "architecture": runtime.GOARCH,
        },
    }

    reqBody, _ := json.Marshal(regReq)
    
    req, err := http.NewRequest("POST", c.config.ManagerURL+"/api/v1/clients/register", strings.NewReader(string(reqBody)))
    if err != nil {
        return err
    }

    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+c.config.APIKey)

    resp, err := c.httpClient.Do(req)
    if err != nil {
        return fmt.Errorf("registration request failed: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        body, _ := io.ReadAll(resp.Body)
        return fmt.Errorf("registration failed with status %d: %s", resp.StatusCode, body)
    }

    var regResp struct {
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

    if err := json.NewDecoder(resp.Body).Decode(&regResp); err != nil {
        return fmt.Errorf("failed to parse registration response: %w", err)
    }

    c.clientID = regResp.ClientID
    c.headendURL = regResp.Cluster.HeadendURL
    c.config.APIKey = regResp.APIKey

    // Save certificates
    if err := c.saveCertificates(regResp.Certificates.Cert, regResp.Certificates.Key, regResp.Certificates.CA); err != nil {
        return fmt.Errorf("failed to save certificates: %w", err)
    }

    fmt.Printf("Registration successful - Client ID: %s\n", c.clientID)
    return nil
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
    defer resp.Body.Close()

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
    
    req, err := http.NewRequest("POST", c.config.ManagerURL+"/api/v1/wireguard/keys", strings.NewReader(string(reqBody)))
    if err != nil {
        return err
    }

    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+c.accessToken)

    resp, err := c.httpClient.Do(req)
    if err != nil {
        return fmt.Errorf("WireGuard config request failed: %w", err)
    }
    defer resp.Body.Close()

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
    interfaceName := c.getWireGuardInterface()
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
PublicKey = HEADEND_PUBLIC_KEY_PLACEHOLDER
Endpoint = %s:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
`, ipAddress, c.wgPrivateKey.String(), headendHost)

    return os.WriteFile(configPath, []byte(config), 0600)
}

func (c *Client) startWireGuard() error {
    fmt.Println("Starting WireGuard interface...")

    interfaceName := c.getWireGuardInterface()
    configPath := c.getWireGuardConfigPath()

    var cmd *exec.Cmd
    switch runtime.GOOS {
    case "darwin", "linux":
        cmd = exec.Command("wg-quick", "up", configPath)
    case "windows":
        // On Windows, we'd need to use WireGuard service
        return fmt.Errorf("Windows WireGuard integration not implemented yet")
    default:
        return fmt.Errorf("unsupported platform: %s", runtime.GOOS)
    }

    if output, err := cmd.CombinedOutput(); err != nil {
        return fmt.Errorf("failed to start WireGuard: %v, output: %s", err, output)
    }

    fmt.Printf("WireGuard interface %s started successfully\n", interfaceName)
    return nil
}

func (c *Client) stopWireGuard() error {
    interfaceName := c.getWireGuardInterface()
    configPath := c.getWireGuardConfigPath()

    var cmd *exec.Cmd
    switch runtime.GOOS {
    case "darwin", "linux":
        cmd = exec.Command("wg-quick", "down", configPath)
    case "windows":
        return fmt.Errorf("Windows WireGuard integration not implemented yet")
    default:
        return fmt.Errorf("unsupported platform: %s", runtime.GOOS)
    }

    if output, err := cmd.CombinedOutput(); err != nil {
        return fmt.Errorf("failed to stop WireGuard: %v, output: %s", err, output)
    }

    fmt.Printf("WireGuard interface %s stopped successfully\n", interfaceName)
    return nil
}

func (c *Client) runMonitoring(ctx context.Context) error {
    fmt.Println("Starting connection monitoring...")

    ticker := time.NewTicker(30 * time.Second)
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

    // TODO: Check JWT token expiry and refresh if needed
    // TODO: Check certificate expiry

    return nil
}

func (c *Client) getWireGuardInterface() string {
    switch runtime.GOOS {
    case "darwin":
        return "utun1"
    case "linux":
        return "wg0"  
    case "windows":
        return "sasewaddle"
    default:
        return "wg0"
    }
}

func (c *Client) getWireGuardConfigPath() string {
    interfaceName := c.getWireGuardInterface()
    
    switch runtime.GOOS {
    case "darwin":
        return fmt.Sprintf("/usr/local/etc/wireguard/%s.conf", interfaceName)
    case "linux":
        return fmt.Sprintf("/etc/wireguard/%s.conf", interfaceName)
    case "windows":
        return fmt.Sprintf("C:\\Program Files\\WireGuard\\Data\\Configurations\\%s.conf", interfaceName)
    default:
        return fmt.Sprintf("/etc/wireguard/%s.conf", interfaceName)
    }
}

func (c *Client) getInterfaceIP(interfaceName string) (string, error) {
    var cmd *exec.Cmd
    
    switch runtime.GOOS {
    case "darwin", "linux":
        cmd = exec.Command("ip", "addr", "show", interfaceName)
    case "windows":
        return "", fmt.Errorf("Windows IP detection not implemented")
    default:
        return "", fmt.Errorf("unsupported platform")
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

    if err := os.WriteFile(certDir+"/client.crt", []byte(cert), 0644); err != nil {
        return err
    }

    if err := os.WriteFile(certDir+"/client.key", []byte(key), 0600); err != nil {
        return err
    }

    if err := os.WriteFile(certDir+"/ca.crt", []byte(ca), 0644); err != nil {
        return err
    }

    return nil
}

func (c *Client) getCertificateDir() string {
    switch runtime.GOOS {
    case "darwin":
        return os.Getenv("HOME") + "/.sasewaddle/certs"
    case "linux": 
        return os.Getenv("HOME") + "/.sasewaddle/certs"
    case "windows":
        return os.Getenv("APPDATA") + "\\SASEWaddle\\certs"
    default:
        return "/tmp/sasewaddle/certs"
    }
}