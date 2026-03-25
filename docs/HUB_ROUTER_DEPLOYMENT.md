# Hub-Router Deployment Models

## Deployment Options

| Model | XDP Needed? | Notes |
|---|---|---|
| **In-cluster (Cilium)** | No | Cilium eBPF handles L3/L4 filtering |
| **Bare Metal / VMs** | **Yes** | No CNI protection; rebuild with `-tags xdp` |
| **Spoke K8s (basic CNI)** | **Yes** | flannel/calico without eBPF need XDP |

## XDP Build

```bash
cd services/hub-router
make build-xdp  # Requires clang, libbpf headers
```

### Prerequisites
- Linux kernel 5.10+
- clang (BPF target support)
- libbpf development headers
- Capabilities: `CAP_BPF`, `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`

## Configuration

```yaml
xdp:
  enabled: true
  interface: eth0
  rate_limit_pps: 10000
  syn_rate_limit_pps: 1000
  udp_rate_limit_pps: 5000
  blocklist_sync_url: http://hub-api:8080/api/v1/security/blocklist
```

## NUMA Considerations

For multi-socket servers, XDP/AF_XDP automatically detects the NUMA node of the NIC
and allocates buffers on the same node for optimal memory locality.
