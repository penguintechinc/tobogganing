// SPDX-License-Identifier: GPL-2.0
//
// xdp_ratelimit.h - Shared type definitions for the XDP rate limiter.
// Used by both the BPF C program and Go (via bpf2go code generation).

#ifndef __XDP_RATELIMIT_H
#define __XDP_RATELIMIT_H

// rate_limit_key is the key for per-source-IP rate limiting maps.
struct rate_limit_key {
    __be32 src_ip;
};

// rate_limit_value holds the token bucket state for a source IP.
struct rate_limit_value {
    __u64 tokens;
    __u64 last_refill;
};

// blocklist_key is the key for the IP blocklist map.
struct blocklist_key {
    __be32 ip;
};

// xdp_stats holds per-action packet counters.
struct xdp_stats {
    __u64 packets_processed;
    __u64 packets_dropped;
    __u64 packets_rate_limited;
    __u64 syn_flood_dropped;
    __u64 udp_flood_dropped;
};

#endif // __XDP_RATELIMIT_H
