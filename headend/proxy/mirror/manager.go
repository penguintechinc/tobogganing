package mirror

import (
    "bytes"
    "encoding/binary"
    "fmt"
    "net"
    "net/http"
    "sync"
    "time"

    "github.com/google/gopacket"
    "github.com/google/gopacket/layers"
    log "github.com/sirupsen/logrus"
)

type Manager struct {
    destinations []string
    protocol     string
    bufferSize   int
    queue        chan *MirrorPacket
    wg           sync.WaitGroup
    stopCh       chan struct{}
    connections  map[string]net.Conn
    mu           sync.RWMutex
    stats        *Stats
}

type MirrorPacket struct {
    Timestamp   time.Time
    Source      net.IP
    Destination net.IP
    Protocol    string
    Data        []byte
    Metadata    map[string]interface{}
}

type Stats struct {
    PacketsSent    uint64
    PacketsDropped uint64
    BytesSent      uint64
    Errors         uint64
    mu             sync.RWMutex
}

func NewManager(destinations []string, protocol string, bufferSize int) *Manager {
    if protocol == "" {
        protocol = "VXLAN"
    }
    
    return &Manager{
        destinations: destinations,
        protocol:     protocol,
        bufferSize:   bufferSize,
        queue:        make(chan *MirrorPacket, bufferSize),
        stopCh:       make(chan struct{}),
        connections:  make(map[string]net.Conn),
        stats:        &Stats{},
    }
}

func (m *Manager) Start() error {
    log.Infof("Starting mirror manager with protocol %s to %v", m.protocol, m.destinations)
    
    // Establish connections to mirror destinations
    for _, dest := range m.destinations {
        conn, err := m.createConnection(dest)
        if err != nil {
            log.Errorf("Failed to connect to mirror destination %s: %v", dest, err)
            continue
        }
        m.connections[dest] = conn
    }
    
    if len(m.connections) == 0 {
        return fmt.Errorf("no mirror destinations available")
    }
    
    // Start worker goroutines
    workerCount := 4
    for i := 0; i < workerCount; i++ {
        m.wg.Add(1)
        go m.worker()
    }
    
    // Start stats reporter
    go m.reportStats()
    
    return nil
}

func (m *Manager) Stop() {
    log.Info("Stopping mirror manager")
    close(m.stopCh)
    
    // Wait for workers to finish
    m.wg.Wait()
    
    // Close connections
    m.mu.Lock()
    for dest, conn := range m.connections {
        conn.Close()
        delete(m.connections, dest)
    }
    m.mu.Unlock()
}

func (m *Manager) createConnection(dest string) (net.Conn, error) {
    switch m.protocol {
    case "VXLAN":
        return net.Dial("udp", dest)
    case "GRE":
        return net.Dial("ip4:47", dest)
    case "ERSPAN":
        return net.Dial("udp", dest)
    default:
        return net.Dial("udp", dest)
    }
}

func (m *Manager) MirrorHTTP(req *http.Request, statusCode int, body []byte) {
    packet := &MirrorPacket{
        Timestamp: time.Now(),
        Protocol:  "HTTP",
        Data:      m.encodeHTTP(req, statusCode, body),
        Metadata: map[string]interface{}{
            "method":      req.Method,
            "url":         req.URL.String(),
            "status_code": statusCode,
            "user_agent":  req.UserAgent(),
        },
    }
    
    select {
    case m.queue <- packet:
        // Packet queued successfully
    default:
        // Queue full, drop packet
        m.stats.incrementDropped()
        log.Warn("Mirror queue full, dropping packet")
    }
}

func (m *Manager) MirrorTCP(src, dst string, data []byte) {
    packet := &MirrorPacket{
        Timestamp: time.Now(),
        Protocol:  "TCP",
        Data:      data,
        Metadata: map[string]interface{}{
            "src": src,
            "dst": dst,
            "protocol": "tcp",
        },
    }
    
    select {
    case m.queue <- packet:
        // Packet queued successfully
    default:
        // Queue full, drop packet
        m.stats.incrementDropped()
        log.Warn("Mirror queue full, dropping TCP packet")
    }
}

func (m *Manager) MirrorUDP(src, dst string, data []byte) {
    packet := &MirrorPacket{
        Timestamp: time.Now(),
        Protocol:  "UDP", 
        Data:      data,
        Metadata: map[string]interface{}{
            "src": src,
            "dst": dst,
            "protocol": "udp",
        },
    }
    
    select {
    case m.queue <- packet:
        // Packet queued successfully
    default:
        // Queue full, drop packet
        m.stats.incrementDropped()
        log.Warn("Mirror queue full, dropping UDP packet")
    }
}

func (m *Manager) MirrorRaw(data []byte, metadata map[string]interface{}) {
    packet := &MirrorPacket{
        Timestamp: time.Now(),
        Protocol:  "RAW",
        Data:      data,
        Metadata:  metadata,
    }
    
    select {
    case m.queue <- packet:
        // Packet queued successfully
    default:
        // Queue full, drop packet
        m.stats.incrementDropped()
    }
}

func (m *Manager) worker() {
    defer m.wg.Done()
    
    for {
        select {
        case packet := <-m.queue:
            m.sendPacket(packet)
        case <-m.stopCh:
            // Drain remaining packets
            for len(m.queue) > 0 {
                select {
                case packet := <-m.queue:
                    m.sendPacket(packet)
                default:
                    return
                }
            }
            return
        }
    }
}

func (m *Manager) sendPacket(packet *MirrorPacket) {
    var encapsulated []byte
    var err error
    
    switch m.protocol {
    case "VXLAN":
        encapsulated, err = m.encapsulateVXLAN(packet)
    case "GRE":
        encapsulated, err = m.encapsulateGRE(packet)
    case "ERSPAN":
        encapsulated, err = m.encapsulateERSPAN(packet)
    default:
        encapsulated = packet.Data
    }
    
    if err != nil {
        log.Errorf("Failed to encapsulate packet: %v", err)
        m.stats.incrementErrors()
        return
    }
    
    m.mu.RLock()
    defer m.mu.RUnlock()
    
    for dest, conn := range m.connections {
        if _, err := conn.Write(encapsulated); err != nil {
            log.Errorf("Failed to send to mirror destination %s: %v", dest, err)
            m.stats.incrementErrors()
            
            // Try to reconnect
            go m.reconnect(dest)
        } else {
            m.stats.incrementSent(uint64(len(encapsulated)))
        }
    }
}

func (m *Manager) encapsulateVXLAN(packet *MirrorPacket) ([]byte, error) {
    // VXLAN header (8 bytes)
    vxlanHeader := make([]byte, 8)
    vxlanHeader[0] = 0x08 // Flags (I flag set)
    // VNI (VXLAN Network Identifier) - use 1000 as default
    vni := uint32(1000)
    binary.BigEndian.PutUint32(vxlanHeader[4:], vni<<8)
    
    // Combine VXLAN header with packet data
    return append(vxlanHeader, packet.Data...), nil
}

func (m *Manager) encapsulateGRE(packet *MirrorPacket) ([]byte, error) {
    // Simplified GRE encapsulation
    greHeader := make([]byte, 4)
    binary.BigEndian.PutUint16(greHeader[2:], 0x0800) // Protocol type: IPv4
    
    return append(greHeader, packet.Data...), nil
}

func (m *Manager) encapsulateERSPAN(packet *MirrorPacket) ([]byte, error) {
    // ERSPAN Type II header
    erspanHeader := make([]byte, 8)
    
    // Version (4 bits) | VLAN (12 bits)
    binary.BigEndian.PutUint16(erspanHeader[0:], 0x1000) // Version 1, VLAN 0
    
    // COS (3 bits) | EN (2 bits) | T (1 bit) | Session ID (10 bits)
    binary.BigEndian.PutUint16(erspanHeader[2:], 0x0001) // Session ID 1
    
    // Reserved (12 bits) | Index (20 bits)
    binary.BigEndian.PutUint32(erspanHeader[4:], uint32(time.Now().Unix()&0xFFFFF))
    
    return append(erspanHeader, packet.Data...), nil
}

func (m *Manager) encodeHTTP(req *http.Request, statusCode int, body []byte) []byte {
    var buf bytes.Buffer
    
    // Write request line
    fmt.Fprintf(&buf, "%s %s %s\r\n", req.Method, req.URL.Path, req.Proto)
    
    // Write headers
    for key, values := range req.Header {
        for _, value := range values {
            fmt.Fprintf(&buf, "%s: %s\r\n", key, value)
        }
    }
    
    // Write status
    fmt.Fprintf(&buf, "\r\nHTTP/1.1 %d\r\n", statusCode)
    
    // Write body length
    fmt.Fprintf(&buf, "Content-Length: %d\r\n\r\n", len(body))
    
    // Write body
    buf.Write(body)
    
    return buf.Bytes()
}

func (m *Manager) reconnect(dest string) {
    m.mu.Lock()
    defer m.mu.Unlock()
    
    // Close existing connection
    if conn, exists := m.connections[dest]; exists {
        conn.Close()
        delete(m.connections, dest)
    }
    
    // Try to reconnect
    conn, err := m.createConnection(dest)
    if err != nil {
        log.Errorf("Failed to reconnect to mirror destination %s: %v", dest, err)
        return
    }
    
    m.connections[dest] = conn
    log.Infof("Reconnected to mirror destination %s", dest)
}

func (m *Manager) reportStats() {
    ticker := time.NewTicker(60 * time.Second)
    defer ticker.Stop()
    
    for {
        select {
        case <-ticker.C:
            m.stats.mu.RLock()
            log.WithFields(log.Fields{
                "packets_sent":    m.stats.PacketsSent,
                "packets_dropped": m.stats.PacketsDropped,
                "bytes_sent":      m.stats.BytesSent,
                "errors":          m.stats.Errors,
            }).Info("Mirror statistics")
            m.stats.mu.RUnlock()
        case <-m.stopCh:
            return
        }
    }
}

func (s *Stats) incrementSent(bytes uint64) {
    s.mu.Lock()
    s.PacketsSent++
    s.BytesSent += bytes
    s.mu.Unlock()
}

func (s *Stats) incrementDropped() {
    s.mu.Lock()
    s.PacketsDropped++
    s.mu.Unlock()
}

func (s *Stats) incrementErrors() {
    s.mu.Lock()
    s.Errors++
    s.mu.Unlock()
}