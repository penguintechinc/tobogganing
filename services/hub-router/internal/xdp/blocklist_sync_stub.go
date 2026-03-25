//go:build !xdp

package xdp

import (
	"context"
	"time"
)

// BlocklistSyncer is a no-op stub when built without the xdp tag.
type BlocklistSyncer struct{}

// NewBlocklistSyncer creates a no-op blocklist syncer.
func NewBlocklistSyncer(_ *XDPProtection, _ string, _ time.Duration) *BlocklistSyncer {
	return &BlocklistSyncer{}
}

// Start is a no-op without XDP build tag.
func (b *BlocklistSyncer) Start(_ context.Context) {}

// SyncFromPolicies is a no-op without XDP build tag.
func (b *BlocklistSyncer) SyncFromPolicies(_ []string) {}
