//go:build xdp

package xdp

import (
	"fmt"
	"net"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/link"
	log "github.com/sirupsen/logrus"
)

//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -cc clang -type xdp_stats bpf ../../bpf/xdp_ratelimit.c

// XDPProtection manages XDP programs attached to a network interface.
type XDPProtection struct {
	link     link.Link
	objs     bpfObjects
	cfg      XDPConfig
	attached bool
}

// New creates a new XDP protection instance.
func New(cfg XDPConfig) *XDPProtection {
	return &XDPProtection{cfg: cfg}
}

// Attach loads the BPF program and attaches it to the specified interface.
func (x *XDPProtection) Attach(interfaceName string) error {
	iface, err := net.InterfaceByName(interfaceName)
	if err != nil {
		return fmt.Errorf("xdp: interface %s not found: %w", interfaceName, err)
	}

	if err := loadBpfObjects(&x.objs, nil); err != nil {
		return fmt.Errorf("xdp: failed to load BPF objects: %w", err)
	}

	l, err := link.AttachXDP(link.XDPOptions{
		Program:   x.objs.XdpRatelimit,
		Interface: iface.Index,
	})
	if err != nil {
		x.objs.Close()
		return fmt.Errorf("xdp: failed to attach to %s: %w", interfaceName, err)
	}

	x.link = l
	x.attached = true

	log.WithField("interface", interfaceName).Info("XDP program attached")
	return nil
}

// SetRateLimit updates the general packets-per-second rate limit in the BPF map.
func (x *XDPProtection) SetRateLimit(pps int) {
	if !x.attached {
		return
	}
	x.setRateConfig(0, uint64(pps))
	log.WithField("pps", pps).Debug("XDP general rate limit updated")
}

// SetSYNRateLimit updates the SYN packets-per-second rate limit.
func (x *XDPProtection) SetSYNRateLimit(pps int) {
	if !x.attached {
		return
	}
	x.setRateConfig(1, uint64(pps))
}

// SetUDPRateLimit updates the UDP packets-per-second rate limit.
func (x *XDPProtection) SetUDPRateLimit(pps int) {
	if !x.attached {
		return
	}
	x.setRateConfig(2, uint64(pps))
}

func (x *XDPProtection) setRateConfig(index uint32, value uint64) {
	if err := x.objs.RateConfigMap.Put(index, value); err != nil {
		log.WithError(err).WithField("index", index).Error("Failed to update rate config")
	}
}

// BlockIP adds an IP to the blocklist for instant XDP_DROP.
func (x *XDPProtection) BlockIP(ip net.IP) {
	if !x.attached {
		return
	}
	ipv4 := ip.To4()
	if ipv4 == nil {
		return
	}
	var key [4]byte
	copy(key[:], ipv4)
	val := uint8(1)
	if err := x.objs.BlocklistMap.Put(key, val); err != nil {
		log.WithError(err).WithField("ip", ip).Error("Failed to add IP to blocklist")
	}
}

// UnblockIP removes an IP from the blocklist.
func (x *XDPProtection) UnblockIP(ip net.IP) {
	if !x.attached {
		return
	}
	ipv4 := ip.To4()
	if ipv4 == nil {
		return
	}
	var key [4]byte
	copy(key[:], ipv4)
	if err := x.objs.BlocklistMap.Delete(key); err != nil {
		log.WithError(err).WithField("ip", ip).Debug("Failed to remove IP from blocklist (may not exist)")
	}
}

// Stats reads the current XDP statistics from per-CPU counters.
func (x *XDPProtection) Stats() XDPStats {
	if !x.attached {
		return XDPStats{}
	}

	var key uint32
	var values []bpfXdpStats

	if err := x.objs.StatsMap.Lookup(key, &values); err != nil {
		log.WithError(err).Debug("Failed to read XDP stats")
		return XDPStats{}
	}

	// Sum per-CPU values
	var total XDPStats
	for _, v := range values {
		total.PacketsProcessed += v.PacketsProcessed
		total.PacketsDropped += v.PacketsDropped
		total.PacketsRateLimited += v.PacketsRateLimited
		total.SYNFloodDropped += v.SynFloodDropped
		total.UDPFloodDropped += v.UdpFloodDropped
	}

	return total
}

// BlocklistSize returns the current number of entries in the blocklist map.
func (x *XDPProtection) BlocklistSize() int {
	if !x.attached {
		return 0
	}

	count := 0
	var key [4]byte
	var val uint8
	iter := x.objs.BlocklistMap.Iterate()
	for iter.Next(&key, &val) {
		count++
	}
	return count
}

// Close detaches the XDP program and frees all BPF resources.
func (x *XDPProtection) Close() {
	if x.link != nil {
		if err := x.link.Close(); err != nil {
			log.WithError(err).Warn("Failed to detach XDP program")
		}
		x.link = nil
	}
	x.objs.Close()
	x.attached = false
	log.Info("XDP protection closed")
}

// Ensure ebpf package is used (referenced via loadBpfObjects and bpfObjects).
var _ = ebpf.Map{}
