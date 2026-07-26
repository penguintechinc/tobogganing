// SPDX-License-Identifier: GPL-2.0
//
// xdp_filter.c - XDP fast-path packet filter for the Tobogganing hub-router.
//
// This BPF program runs in the kernel XDP hook, providing line-rate packet
// filtering before packets reach the network stack. It implements:
//
// 1. IP CIDR allow/deny lists using BPF hash maps
// 2. Port and protocol filtering
// 3. Per-source-IP rate limiting using a token bucket algorithm
//
// Actions:
//   XDP_PASS  - Forward packet to AF_XDP socket for Go-level processing
//   XDP_DROP  - Silently drop the packet (blocked by policy)
//   XDP_TX    - Redirect packet back out the same interface
//
// This is a scaffold with the basic structure and comments. The actual
// implementation will be refined as the policy engine and AF_XDP integration
// are completed.
//
// Compile with:
//   clang -O2 -g -target bpf -D__TARGET_ARCH_x86 \
//     -I/usr/include/bpf -c xdp_filter.c -o xdp_filter.o

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/ipv6.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/icmp.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

// ============================================================================
// Constants
// ============================================================================

// Maximum number of entries in each BPF map
#define MAX_CIDR_ENTRIES    65536
#define MAX_PORT_ENTRIES    8192
#define MAX_RATE_ENTRIES    131072

// Rate limiter: token bucket parameters
// Tokens are replenished at RATE_TOKENS_PER_SEC per second.
// Burst capacity is RATE_BUCKET_SIZE tokens.
#define RATE_TOKENS_PER_SEC 1000
#define RATE_BUCKET_SIZE    5000

// Rate limiter time granularity (nanoseconds per token)
#define NS_PER_TOKEN (1000000000ULL / RATE_TOKENS_PER_SEC)

// ============================================================================
// BPF Map Definitions
// ============================================================================

// cidr_allow_map: Hash map of allowed IP CIDR ranges.
// Key: __be32 (network address in network byte order, masked to prefix length)
// Value: __u8 (prefix length)
//
// This is a simplified representation. In production, a longest-prefix-match
// (LPM) trie map would be more appropriate for CIDR matching.
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_CIDR_ENTRIES);
    __type(key, __be32);    // IPv4 address (network order)
    __type(value, __u8);    // 1 = allow, 0 = deny
} cidr_allow_map SEC(".maps");

// cidr_deny_map: Hash map of denied IP CIDR ranges.
// Deny rules are checked before allow rules (deny overrides).
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_CIDR_ENTRIES);
    __type(key, __be32);    // IPv4 address (network order)
    __type(value, __u8);    // 1 = active deny rule
} cidr_deny_map SEC(".maps");

// Port/protocol filter value
struct port_filter_val {
    __u8 action;    // 1 = allow, 0 = deny
    __u8 protocol;  // IPPROTO_TCP, IPPROTO_UDP, or 0 for any
    __u16 pad;
};

// port_filter_map: Hash map for port/protocol filtering.
// Key: destination port number (host byte order)
// Value: port_filter_val with action and optional protocol constraint
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_PORT_ENTRIES);
    __type(key, __u16);                     // destination port
    __type(value, struct port_filter_val);   // filter action
} port_filter_map SEC(".maps");

// Token bucket state for rate limiting
struct rate_limit_val {
    __u64 tokens;       // Current token count
    __u64 last_refill;  // Last refill timestamp (nanoseconds)
};

// rate_limit_map: Per-source-IP rate limiter using token bucket algorithm.
// Key: source IPv4 address
// Value: token bucket state (current tokens + last refill time)
//
// When a packet arrives:
// 1. Look up the source IP in the map
// 2. Refill tokens based on elapsed time since last refill
// 3. If tokens > 0: decrement and allow (XDP_PASS)
// 4. If tokens == 0: rate limited (XDP_DROP)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_RATE_ENTRIES);
    __type(key, __be32);                    // source IPv4 address
    __type(value, struct rate_limit_val);    // token bucket state
} rate_limit_map SEC(".maps");

// xdp_stats_map: Per-CPU array for tracking XDP action statistics.
// Index 0 = XDP_PASS count, 1 = XDP_DROP count, 2 = XDP_TX count
struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 4);
    __type(key, __u32);
    __type(value, __u64);
} xdp_stats_map SEC(".maps");

// ============================================================================
// Helper Functions
// ============================================================================

// update_stats increments the per-CPU statistics counter for the given action.
static __always_inline void update_stats(__u32 action)
{
    __u64 *count = bpf_map_lookup_elem(&xdp_stats_map, &action);
    if (count)
        __sync_fetch_and_add(count, 1);
}

// check_rate_limit implements the token bucket rate limiter for a source IP.
// Returns 1 if the packet is allowed, 0 if rate-limited.
static __always_inline int check_rate_limit(__be32 src_ip)
{
    struct rate_limit_val *val;
    struct rate_limit_val new_val;
    __u64 now = bpf_ktime_get_ns();

    val = bpf_map_lookup_elem(&rate_limit_map, &src_ip);
    if (!val) {
        // First packet from this source - initialize bucket
        new_val.tokens = RATE_BUCKET_SIZE - 1;  // Consume one token
        new_val.last_refill = now;
        bpf_map_update_elem(&rate_limit_map, &src_ip, &new_val, BPF_ANY);
        return 1;  // Allow
    }

    // Refill tokens based on elapsed time
    __u64 elapsed = now - val->last_refill;
    __u64 new_tokens = elapsed / NS_PER_TOKEN;

    new_val.tokens = val->tokens + new_tokens;
    if (new_val.tokens > RATE_BUCKET_SIZE)
        new_val.tokens = RATE_BUCKET_SIZE;

    if (new_tokens > 0)
        new_val.last_refill = now;
    else
        new_val.last_refill = val->last_refill;

    // Try to consume a token
    if (new_val.tokens > 0) {
        new_val.tokens--;
        bpf_map_update_elem(&rate_limit_map, &src_ip, &new_val, BPF_ANY);
        return 1;  // Allow
    }

    // No tokens available - rate limited
    bpf_map_update_elem(&rate_limit_map, &src_ip, &new_val, BPF_ANY);
    return 0;  // Drop
}

// ============================================================================
// XDP Program Entry Point
// ============================================================================

// xdp_filter is the main XDP program entry point.
// It is attached to a network interface and runs for every incoming packet.
//
// Processing pipeline:
// 1. Parse Ethernet header - drop non-IP packets
// 2. Parse IP header - extract source/destination IPs
// 3. Check deny CIDR map - deny overrides all
// 4. Check allow CIDR map - if configured, only allowed CIDRs pass
// 5. Parse transport header - extract ports
// 6. Check port/protocol filter map
// 7. Apply rate limiting per source IP
// 8. XDP_PASS to AF_XDP socket for Go-level processing
SEC("xdp")
int xdp_filter(struct xdp_md *ctx)
{
    void *data = (void *)(long)ctx->data;
    void *data_end = (void *)(long)ctx->data_end;

    // Step 1: Parse Ethernet header
    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end) {
        update_stats(XDP_DROP);
        return XDP_DROP;
    }

    // Only process IPv4 packets (IPv6 support to be added)
    if (eth->h_proto != bpf_htons(ETH_P_IP)) {
        // Pass non-IPv4 traffic through to the stack
        update_stats(XDP_PASS);
        return XDP_PASS;
    }

    // Step 2: Parse IP header
    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end) {
        update_stats(XDP_DROP);
        return XDP_DROP;
    }

    __be32 src_ip = ip->saddr;
    __be32 dst_ip = ip->daddr;

    // Step 3: Check deny CIDR map (deny overrides everything)
    __u8 *deny_val = bpf_map_lookup_elem(&cidr_deny_map, &src_ip);
    if (deny_val && *deny_val) {
        update_stats(XDP_DROP);
        return XDP_DROP;
    }

    deny_val = bpf_map_lookup_elem(&cidr_deny_map, &dst_ip);
    if (deny_val && *deny_val) {
        update_stats(XDP_DROP);
        return XDP_DROP;
    }

    // Step 4: Check allow CIDR map
    // If the allow map has entries, only explicitly allowed IPs pass.
    // If the allow map is empty, all non-denied IPs pass (open policy).
    __u8 *allow_val = bpf_map_lookup_elem(&cidr_allow_map, &dst_ip);
    // Note: In a full implementation, we would check if the allow map
    // is non-empty and enforce allow-listing. For the scaffold, we
    // proceed to further checks.

    // Step 5: Parse transport header for port/protocol filtering
    __u16 dst_port = 0;
    __u8 protocol = ip->protocol;

    if (protocol == IPPROTO_TCP) {
        struct tcphdr *tcp = (void *)ip + (ip->ihl * 4);
        if ((void *)(tcp + 1) > data_end) {
            update_stats(XDP_DROP);
            return XDP_DROP;
        }
        dst_port = bpf_ntohs(tcp->dest);
    } else if (protocol == IPPROTO_UDP) {
        struct udphdr *udp = (void *)ip + (ip->ihl * 4);
        if ((void *)(udp + 1) > data_end) {
            update_stats(XDP_DROP);
            return XDP_DROP;
        }
        dst_port = bpf_ntohs(udp->dest);
    }

    // Step 6: Check port/protocol filter map
    if (dst_port > 0) {
        struct port_filter_val *pf = bpf_map_lookup_elem(&port_filter_map, &dst_port);
        if (pf) {
            // Check protocol constraint if specified
            if (pf->protocol == 0 || pf->protocol == protocol) {
                if (pf->action == 0) {
                    // Port is explicitly denied
                    update_stats(XDP_DROP);
                    return XDP_DROP;
                }
                // Port is explicitly allowed - continue to rate limiting
            }
        }
        // Port not in filter map - default: allow (pass to userspace for policy)
    }

    // Step 7: Apply rate limiting per source IP
    if (!check_rate_limit(src_ip)) {
        // Rate limited - drop the packet
        update_stats(XDP_DROP);
        return XDP_DROP;
    }

    // Step 8: Pass to AF_XDP socket for Go-level processing
    // The packet has passed all fast-path checks and will be delivered
    // to userspace via the AF_XDP socket for policy evaluation, logging,
    // and forwarding.
    update_stats(XDP_PASS);
    return XDP_PASS;
}

// License declaration required for BPF programs
char _license[] SEC("license") = "GPL";
