// SPDX-License-Identifier: GPL-2.0
//
// xdp_ratelimit.c - XDP rate limiter, blocklist, and flood protection for
// the Tobogganing hub-router.
//
// Enhancements over xdp_filter.c:
//   - Dedicated IP blocklist map (synced from policy engine deny rules)
//   - SYN flood protection (per-source-IP SYN rate limiting)
//   - UDP flood protection (per-source-IP UDP rate limiting, protects WG port 51820)
//   - Structured stats with per-category counters
//
// Compile with:
//   clang -O2 -g -target bpf -D__TARGET_ARCH_x86 \
//     -I/usr/include/bpf -c xdp_ratelimit.c -o xdp_ratelimit.o

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

// ============================================================================
// Constants
// ============================================================================

#define MAX_BLOCKLIST_ENTRIES  65536
#define MAX_RATE_ENTRIES       131072

// Default rate limits (can be overridden via BPF map from Go)
#define DEFAULT_PPS            10000
#define DEFAULT_SYN_PPS        1000
#define DEFAULT_UDP_PPS        5000
#define BUCKET_SIZE_MULTIPLIER 5

#define NS_PER_SEC 1000000000ULL

// ============================================================================
// BPF Maps
// ============================================================================

// IP blocklist — populated from policy engine deny-by-IP rules.
// Checked first, before any other processing. XDP_DROP at NIC level.
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_BLOCKLIST_ENTRIES);
    __type(key, __be32);
    __type(value, __u8);
} blocklist_map SEC(".maps");

// Per-source-IP general rate limiter (all protocols)
struct rate_limit_val {
    __u64 tokens;
    __u64 last_refill;
};

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_RATE_ENTRIES);
    __type(key, __be32);
    __type(value, struct rate_limit_val);
} rate_limit_map SEC(".maps");

// Per-source-IP SYN rate limiter
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_RATE_ENTRIES);
    __type(key, __be32);
    __type(value, struct rate_limit_val);
} syn_rate_limit_map SEC(".maps");

// Per-source-IP UDP rate limiter
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_RATE_ENTRIES);
    __type(key, __be32);
    __type(value, struct rate_limit_val);
} udp_rate_limit_map SEC(".maps");

// Rate limit configuration (set from Go userspace)
// Index 0: packets per second, Index 1: SYN PPS, Index 2: UDP PPS
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 4);
    __type(key, __u32);
    __type(value, __u64);
} rate_config_map SEC(".maps");

// Statistics
struct xdp_stats {
    __u64 packets_processed;
    __u64 packets_dropped;
    __u64 packets_rate_limited;
    __u64 syn_flood_dropped;
    __u64 udp_flood_dropped;
};

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct xdp_stats);
} stats_map SEC(".maps");

// ============================================================================
// Helpers
// ============================================================================

static __always_inline void update_stats_field(int field)
{
    __u32 key = 0;
    struct xdp_stats *stats = bpf_map_lookup_elem(&stats_map, &key);
    if (!stats)
        return;

    switch (field) {
    case 0: __sync_fetch_and_add(&stats->packets_processed, 1); break;
    case 1: __sync_fetch_and_add(&stats->packets_dropped, 1); break;
    case 2: __sync_fetch_and_add(&stats->packets_rate_limited, 1); break;
    case 3: __sync_fetch_and_add(&stats->syn_flood_dropped, 1); break;
    case 4: __sync_fetch_and_add(&stats->udp_flood_dropped, 1); break;
    }
}

static __always_inline __u64 get_rate_config(__u32 index, __u64 default_val)
{
    __u64 *val = bpf_map_lookup_elem(&rate_config_map, &index);
    if (val && *val > 0)
        return *val;
    return default_val;
}

// Generic token bucket rate check against a specific map
static __always_inline int check_rate(void *map, __be32 src_ip, __u64 pps)
{
    struct rate_limit_val *val;
    struct rate_limit_val new_val;
    __u64 now = bpf_ktime_get_ns();
    __u64 bucket_size = pps * BUCKET_SIZE_MULTIPLIER;
    __u64 ns_per_token = NS_PER_SEC / pps;

    val = bpf_map_lookup_elem(map, &src_ip);
    if (!val) {
        new_val.tokens = bucket_size - 1;
        new_val.last_refill = now;
        bpf_map_update_elem(map, &src_ip, &new_val, BPF_ANY);
        return 1;
    }

    __u64 elapsed = now - val->last_refill;
    __u64 new_tokens = elapsed / ns_per_token;

    new_val.tokens = val->tokens + new_tokens;
    if (new_val.tokens > bucket_size)
        new_val.tokens = bucket_size;

    new_val.last_refill = (new_tokens > 0) ? now : val->last_refill;

    if (new_val.tokens > 0) {
        new_val.tokens--;
        bpf_map_update_elem(map, &src_ip, &new_val, BPF_ANY);
        return 1;
    }

    bpf_map_update_elem(map, &src_ip, &new_val, BPF_ANY);
    return 0;
}

// ============================================================================
// XDP Program
// ============================================================================

SEC("xdp")
int xdp_ratelimit(struct xdp_md *ctx)
{
    void *data = (void *)(long)ctx->data;
    void *data_end = (void *)(long)ctx->data_end;

    // Parse Ethernet header
    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end)
        return XDP_DROP;

    if (eth->h_proto != bpf_htons(ETH_P_IP)) {
        update_stats_field(0);
        return XDP_PASS;
    }

    // Parse IP header
    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end)
        return XDP_DROP;

    __be32 src_ip = ip->saddr;

    // Step 1: Blocklist check (instant drop)
    __u8 *blocked = bpf_map_lookup_elem(&blocklist_map, &src_ip);
    if (blocked && *blocked) {
        update_stats_field(1);
        return XDP_DROP;
    }

    // Step 2: Protocol-specific flood protection
    if (ip->protocol == IPPROTO_TCP) {
        struct tcphdr *tcp = (void *)ip + (ip->ihl * 4);
        if ((void *)(tcp + 1) > data_end)
            return XDP_DROP;

        // SYN flood protection
        if (tcp->syn && !tcp->ack) {
            __u64 syn_pps = get_rate_config(1, DEFAULT_SYN_PPS);
            if (!check_rate(&syn_rate_limit_map, src_ip, syn_pps)) {
                update_stats_field(3);
                return XDP_DROP;
            }
        }
    } else if (ip->protocol == IPPROTO_UDP) {
        // UDP flood protection (protects WireGuard port 51820)
        __u64 udp_pps = get_rate_config(2, DEFAULT_UDP_PPS);
        if (!check_rate(&udp_rate_limit_map, src_ip, udp_pps)) {
            update_stats_field(4);
            return XDP_DROP;
        }
    }

    // Step 3: General per-source-IP rate limiting
    __u64 general_pps = get_rate_config(0, DEFAULT_PPS);
    if (!check_rate(&rate_limit_map, src_ip, general_pps)) {
        update_stats_field(2);
        return XDP_DROP;
    }

    // Passed all checks
    update_stats_field(0);
    return XDP_PASS;
}

char _license[] SEC("license") = "GPL";
