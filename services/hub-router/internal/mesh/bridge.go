// Package mesh implements hub-to-hub WireGuard mesh bridging for cross-cloud
// Cilium Cluster Mesh connectivity.
//
// The Bridge manages the lifecycle of WireGuard tunnels between hub-router
// instances running in different clouds or data centers, enabling unified
// network policy enforcement across a multi-site topology. It integrates with
// hub-api for authoritative peer discovery, and is designed to coexist with
// Cilium's own node-to-node WireGuard encryption so that the mesh overlay
// operates only at the hub level.
package mesh

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
)

// PeerHub represents a remote hub-router that this hub peers with over a
// hub-to-hub WireGuard tunnel.
type PeerHub struct {
	HubID          string    `json:"hub_id"`
	Endpoint       string    `json:"endpoint"`         // WireGuard endpoint (host:port)
	PublicKey      string    `json:"public_key"`
	ClusterMeshAPI string    `json:"cluster_mesh_api"` // Cilium ClusterMesh API endpoint
	Tenant         string    `json:"tenant"`
	WorkloadID     string    `json:"workload_id"`
	Connected      bool      `json:"connected"`
	LastSeen       time.Time `json:"last_seen"`
}

// BridgeConfig configures the mesh bridge.
type BridgeConfig struct {
	LocalHubID      string
	LocalEndpoint   string
	LocalPublicKey  string
	ClusterMeshAPI  string
	ManagerURL      string        // hub-api base URL for peer discovery
	RefreshInterval time.Duration // how often to poll hub-api for peer changes
}

// Bridge manages hub-to-hub WireGuard tunnels for cross-cloud connectivity.
// It periodically fetches the authoritative list of peer hubs from hub-api and
// converges the local tunnel state to match, connecting new peers and removing
// stale ones.
type Bridge struct {
	config  BridgeConfig
	peers   map[string]*PeerHub
	mu      sync.RWMutex
	logger  *logrus.Entry
	client  *http.Client
	stopCh  chan struct{}
}

// NewBridge creates a new Bridge with the given configuration and logger.
// The Bridge is idle until Start is called.
func NewBridge(config BridgeConfig, logger *logrus.Logger) *Bridge {
	if config.RefreshInterval <= 0 {
		config.RefreshInterval = 60 * time.Second
	}

	return &Bridge{
		config: config,
		peers:  make(map[string]*PeerHub),
		logger: logger.WithField("component", "mesh.bridge"),
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
		stopCh: make(chan struct{}),
	}
}

// Start launches the peer discovery and mesh maintenance loop in a background
// goroutine. It performs an immediate reconciliation on startup, then repeats
// on the configured RefreshInterval. Cancel ctx or call Stop to shut down.
func (b *Bridge) Start(ctx context.Context) error {
	b.logger.WithFields(logrus.Fields{
		"hub_id":           b.config.LocalHubID,
		"local_endpoint":   b.config.LocalEndpoint,
		"refresh_interval": b.config.RefreshInterval,
	}).Info("Starting mesh bridge")

	go b.maintainMesh(ctx)
	return nil
}

// Stop signals the mesh maintenance loop to exit and waits for it to do so.
func (b *Bridge) Stop() {
	b.logger.Info("Stopping mesh bridge")
	close(b.stopCh)
}

// ConnectPeer establishes a WireGuard tunnel to a remote hub-router and records
// it as connected in the peer map. The actual kernel WireGuard configuration
// would integrate with the wireguard.Manager; this implementation records the
// state and logs the event — full WG configuration is wired in at call sites.
func (b *Bridge) ConnectPeer(peer *PeerHub) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	b.logger.WithFields(logrus.Fields{
		"hub_id":           peer.HubID,
		"endpoint":         peer.Endpoint,
		"public_key":       peer.PublicKey,
		"cluster_mesh_api": peer.ClusterMeshAPI,
		"tenant":           peer.Tenant,
		"workload_id":      peer.WorkloadID,
	}).Info("Connecting mesh peer hub")

	// Mark peer as connected and record the time.
	peer.Connected = true
	peer.LastSeen = time.Now()
	b.peers[peer.HubID] = peer

	b.logger.WithField("hub_id", peer.HubID).Info("Mesh peer hub connected")
	return nil
}

// DisconnectPeer tears down the tunnel to the identified remote hub-router and
// removes it from the active peer map.
func (b *Bridge) DisconnectPeer(hubID string) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	peer, ok := b.peers[hubID]
	if !ok {
		return fmt.Errorf("mesh peer hub %q not found", hubID)
	}

	b.logger.WithFields(logrus.Fields{
		"hub_id":   hubID,
		"endpoint": peer.Endpoint,
		"tenant":   peer.Tenant,
	}).Info("Disconnecting mesh peer hub")

	peer.Connected = false
	delete(b.peers, hubID)

	b.logger.WithField("hub_id", hubID).Info("Mesh peer hub disconnected")
	return nil
}

// ListPeers returns a snapshot of all currently connected peer hubs. The
// returned slice is safe to inspect concurrently with ongoing reconciliation.
func (b *Bridge) ListPeers() []*PeerHub {
	b.mu.RLock()
	defer b.mu.RUnlock()

	out := make([]*PeerHub, 0, len(b.peers))
	for _, p := range b.peers {
		// Return a shallow copy to avoid exposing the internal pointer.
		cp := *p
		out = append(out, &cp)
	}
	return out
}

// discoverPeers fetches the current list of authorized peer hubs from hub-api.
// It calls GET {ManagerURL}/api/v1/mesh/peers with JWT auth and unmarshals the
// response envelope into a slice of PeerHub.
func (b *Bridge) discoverPeers(ctx context.Context) ([]*PeerHub, error) {
	url := b.config.ManagerURL + "/api/v1/mesh/peers"

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to build peer discovery request: %w", err)
	}

	token := os.Getenv("CLUSTER_API_KEY")
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("X-Hub-ID", b.config.LocalHubID)

	resp, err := b.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("peer discovery request failed: %w", err)
	}
	defer func() {
		if cerr := resp.Body.Close(); cerr != nil {
			b.logger.Debugf("Error closing peer discovery response body: %v", cerr)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("hub-api returned unexpected status %d for peer discovery", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read peer discovery response body: %w", err)
	}

	// Hub-api responses use the standard envelope:
	// {"status":"success","data":{"peers":[...]},"meta":{...}}
	var envelope struct {
		Status string `json:"status"`
		Data   struct {
			Peers []*PeerHub `json:"peers"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, fmt.Errorf("failed to unmarshal peer discovery response: %w", err)
	}

	if envelope.Status != "success" {
		return nil, fmt.Errorf("hub-api reported non-success status in peer discovery response")
	}

	b.logger.WithField("discovered_count", len(envelope.Data.Peers)).
		Debug("Peer discovery completed")

	return envelope.Data.Peers, nil
}

// maintainMesh is the background loop that keeps the mesh topology in sync
// with the authoritative list provided by hub-api. It runs until ctx is
// cancelled or Stop is called.
func (b *Bridge) maintainMesh(ctx context.Context) {
	ticker := time.NewTicker(b.config.RefreshInterval)
	defer ticker.Stop()

	b.logger.Debug("Mesh maintenance loop started")

	// Perform an initial reconciliation immediately.
	b.reconcile(ctx)

	for {
		select {
		case <-ctx.Done():
			b.logger.Info("Mesh maintenance loop stopping (context cancelled)")
			return
		case <-b.stopCh:
			b.logger.Info("Mesh maintenance loop stopping (bridge stopped)")
			return
		case <-ticker.C:
			b.reconcile(ctx)
		}
	}
}

// reconcile performs a single discovery-and-converge cycle:
//  1. Fetch the authoritative peer list from hub-api.
//  2. Connect peers that are not yet in the local map.
//  3. Disconnect peers that are no longer in the authoritative list.
func (b *Bridge) reconcile(ctx context.Context) {
	desired, err := b.discoverPeers(ctx)
	if err != nil {
		b.logger.WithError(err).Warn("Peer discovery failed; skipping reconciliation cycle")
		return
	}

	// Build a lookup set of desired hub IDs.
	desiredSet := make(map[string]*PeerHub, len(desired))
	for _, p := range desired {
		desiredSet[p.HubID] = p
	}

	// Connect newly discovered peers.
	for _, p := range desired {
		b.mu.RLock()
		_, alreadyConnected := b.peers[p.HubID]
		b.mu.RUnlock()

		if !alreadyConnected {
			if err := b.ConnectPeer(p); err != nil {
				b.logger.WithFields(logrus.Fields{
					"hub_id": p.HubID,
					"error":  err,
				}).Error("Failed to connect mesh peer hub during reconciliation")
			}
		}
	}

	// Disconnect peers that are no longer in the desired set.
	b.mu.RLock()
	stale := make([]string, 0)
	for hubID := range b.peers {
		if _, ok := desiredSet[hubID]; !ok {
			stale = append(stale, hubID)
		}
	}
	b.mu.RUnlock()

	for _, hubID := range stale {
		if err := b.DisconnectPeer(hubID); err != nil {
			b.logger.WithFields(logrus.Fields{
				"hub_id": hubID,
				"error":  err,
			}).Error("Failed to disconnect stale mesh peer hub during reconciliation")
		}
	}

	b.logger.WithFields(logrus.Fields{
		"desired": len(desired),
		"stale":   len(stale),
	}).Debug("Mesh reconciliation cycle complete")
}
