# XDP Edge Protection Guide

## Overview

XDP (eXpress Data Path) provides kernel-level packet filtering at the NIC driver
layer, before packets enter the network stack. This gives line-rate protection
against DDoS, SYN floods, and UDP floods.

## Building with XDP

```bash
cd services/hub-router

# Compile BPF program
make bpf-generate

# Build Go binary with XDP support
make build-xdp
```

## BPF Programs

### xdp_ratelimit.c

Three-stage pipeline:
1. **IP Blocklist** — instant drop from BPF hash map (synced from policy engine)
2. **SYN/UDP Flood Protection** — per-source-IP token buckets for TCP SYN and UDP
3. **General Rate Limiting** — per-source-IP packet rate across all protocols

### AF_XDP Zero-Copy

AF_XDP sockets bypass the kernel network stack entirely, delivering packets
directly from NIC → userspace via shared UMEM rings.

### NUMA-Aware Allocation

Buffer pools are allocated on the same NUMA node as the NIC for optimal
memory locality on multi-socket servers.

## Prometheus Metrics

| Metric | Description |
|---|---|
| `tobogganing_xdp_packets_total{action}` | Packets by action (pass/drop/ratelimit) |
| `tobogganing_xdp_syn_flood_drops_total` | SYN flood drops |
| `tobogganing_xdp_udp_flood_drops_total` | UDP flood drops |
| `tobogganing_xdp_blocklist_size` | Current blocklist entries |

## Default Build (No XDP)

Without `-tags xdp`, all XDP operations are safe no-ops via stub implementations.
Setting `xdp.enabled: true` in a non-XDP build will not crash — it simply does nothing.
