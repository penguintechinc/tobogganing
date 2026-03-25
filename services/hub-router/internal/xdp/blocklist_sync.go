//go:build xdp

package xdp

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"sync"
	"time"

	log "github.com/sirupsen/logrus"
)

// BlocklistSyncer synchronizes the XDP blocklist from policy rules and hub-api.
// It supports two sync models:
//   - Push: SyncFromPolicies() is called directly when policies refresh
//   - Pull: Start() periodically fetches the blocklist from hub-api
type BlocklistSyncer struct {
	xdp        *XDPProtection
	apiClient  *http.Client
	syncURL    string
	interval   time.Duration
	currentIPs map[string]bool
	mu         sync.Mutex
}

// NewBlocklistSyncer creates a blocklist syncer.
func NewBlocklistSyncer(xdp *XDPProtection, syncURL string, interval time.Duration) *BlocklistSyncer {
	if interval == 0 {
		interval = 30 * time.Second
	}
	return &BlocklistSyncer{
		xdp:        xdp,
		apiClient:  &http.Client{Timeout: 10 * time.Second},
		syncURL:    syncURL,
		interval:   interval,
		currentIPs: make(map[string]bool),
	}
}

// Start begins periodic blocklist sync from hub-api.
func (b *BlocklistSyncer) Start(ctx context.Context) {
	go func() {
		ticker := time.NewTicker(b.interval)
		defer ticker.Stop()

		// Initial sync
		b.syncFromAPI()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				b.syncFromAPI()
			}
		}
	}()

	log.WithFields(log.Fields{
		"url":      b.syncURL,
		"interval": b.interval,
	}).Info("XDP blocklist syncer started")
}

// SyncFromPolicies extracts deny-by-IP rules from policies and pushes them
// to the BPF blocklist map. This is the push model — called when the policy
// engine refreshes rules.
func (b *BlocklistSyncer) SyncFromPolicies(denyIPs []string) {
	b.mu.Lock()
	defer b.mu.Unlock()

	newIPs := make(map[string]bool, len(denyIPs))
	for _, ipStr := range denyIPs {
		newIPs[ipStr] = true
	}

	// Add new IPs
	for ipStr := range newIPs {
		if !b.currentIPs[ipStr] {
			ip := net.ParseIP(ipStr)
			if ip != nil {
				b.xdp.BlockIP(ip)
			}
		}
	}

	// Remove IPs no longer in deny list
	for ipStr := range b.currentIPs {
		if !newIPs[ipStr] {
			ip := net.ParseIP(ipStr)
			if ip != nil {
				b.xdp.UnblockIP(ip)
			}
		}
	}

	b.currentIPs = newIPs
	SetBlocklistSize(len(b.currentIPs))

	log.WithField("count", len(denyIPs)).Debug("XDP blocklist synced from policies")
}

func (b *BlocklistSyncer) syncFromAPI() {
	if b.syncURL == "" {
		return
	}

	resp, err := b.apiClient.Get(b.syncURL)
	if err != nil {
		log.WithError(err).Warn("Failed to fetch blocklist from hub-api")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		log.WithFields(log.Fields{
			"status": resp.StatusCode,
			"body":   string(body),
		}).Warn("Blocklist API returned non-200")
		return
	}

	var result struct {
		IPs []string `json:"ips"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		log.WithError(err).Warn("Failed to decode blocklist response")
		return
	}

	b.SyncFromPolicies(result.IPs)
}

// PolicyDenyRule is a minimal representation of a deny-action policy rule
// used by ExtractDenyIPs to derive blocklist entries.
type PolicyDenyRule struct {
	Action string
	CIDRs  []string
}

// ExtractDenyIPs extracts IP addresses from deny rules in a policy list.
// Only /32 host-route CIDRs are promoted to the blocklist; broader prefixes
// are enforced via the kernel routing/firewall layer instead.
func ExtractDenyIPs(rules []PolicyDenyRule) []string {
	var ips []string
	for _, rule := range rules {
		if rule.Action != "deny" {
			continue
		}
		for _, cidr := range rule.CIDRs {
			// For /32 CIDRs, extract the IP for blocklist
			ip, ipNet, err := net.ParseCIDR(cidr)
			if err != nil {
				continue
			}
			ones, bits := ipNet.Mask.Size()
			if ones == bits { // /32 for IPv4, /128 for IPv6
				ips = append(ips, ip.String())
			}
		}
	}
	return ips
}

