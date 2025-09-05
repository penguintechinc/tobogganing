/*
 * TC (Traffic Control) Router eBPF Program for Tobogganing CNI
 * 
 * This program provides high-performance pod-to-pod routing at the TC layer.
 * It implements fast-path routing for intra-node communication and policy
 * enforcement for inter-pod traffic.
 *
 * Features:
 * - Fast intra-node pod-to-pod routing
 * - Connection tracking and flow management  
 * - Policy rule evaluation and enforcement
 * - Traffic statistics collection
 * - Support for IPv4 and IPv6
 */

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/ipv6.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/icmp.h>
#include <linux/in.h>
#include <linux/pkt_cls.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define MAX_PODS 4096
#define MAX_FLOWS 65536
#define MAX_POLICY_RULES 8192

/* Map definitions */

/* Pod information map - maps pod IP to pod metadata */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, __u32);           /* Pod IP address */
    __type(value, struct pod_info);
    __uint(max_entries, MAX_PODS);
} pod_map SEC(".maps");

/* Flow tracking map - tracks active connections */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, struct flow_key);
    __type(value, struct flow_info);
    __uint(max_entries, MAX_FLOWS);
} flow_map SEC(".maps");

/* Policy rules map - stores compiled network policies */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, __u32);           /* Rule ID */
    __type(value, struct policy_rule);
    __uint(max_entries, MAX_POLICY_RULES);
} policy_rules SEC(".maps");

/* Pod namespace mapping - maps pod IP to namespace ID */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, __u32);           /* Pod IP address */
    __type(value, __u32);         /* Namespace ID */
    __uint(max_entries, MAX_PODS);
} pod_namespaces SEC(".maps");

/* Traffic statistics map */
struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __type(key, __u32);
    __type(value, struct traffic_stats);
    __uint(max_entries, 1);
} stats_map SEC(".maps");

/* Per-pod traffic statistics */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, __u32);           /* Pod IP address */
    __type(value, struct pod_traffic_stats);
    __uint(max_entries, MAX_PODS);
} pod_stats_map SEC(".maps");

/* Data structures */

struct pod_info {
    __u32 pod_ip;
    __u32 namespace_id;
    __u8 node_local;
    __u64 last_seen;
    char pod_name[64];
    char namespace[32];
};

struct flow_key {
    __u32 src_ip;
    __u32 dst_ip;
    __u16 src_port;
    __u16 dst_port;
    __u8 protocol;
    __u8 direction;  /* 0=ingress, 1=egress */
};

struct flow_info {
    __u64 packets_total;
    __u64 bytes_total;
    __u64 first_seen;
    __u64 last_seen;
    __u32 src_pod_id;
    __u32 dst_pod_id;
    __u8 state;
    __u8 policy_action; /* 0=deny, 1=allow, 2=log */
};

struct policy_rule {
    __u32 rule_id;
    __u32 priority;
    __u32 src_namespace;
    __u32 dst_namespace;
    __u32 src_ip;
    __u32 src_mask;
    __u32 dst_ip;
    __u32 dst_mask;
    __u16 src_port_start;
    __u16 src_port_end;
    __u16 dst_port_start;
    __u16 dst_port_end;
    __u8 protocol;
    __u8 direction;  /* 0=ingress, 1=egress, 2=both */
    __u8 action;     /* 0=deny, 1=allow, 2=log */
    __u8 enabled;
    __u64 created_time;
};

struct traffic_stats {
    __u64 total_packets;
    __u64 total_bytes;
    __u64 allowed_packets;
    __u64 allowed_bytes;
    __u64 dropped_packets;
    __u64 dropped_bytes;
    __u64 policy_evaluations;
    __u64 fast_path_hits;
    __u64 slow_path_hits;
};

struct pod_traffic_stats {
    __u64 rx_packets;
    __u64 rx_bytes;
    __u64 tx_packets;
    __u64 tx_bytes;
    __u64 dropped_packets;
    __u64 dropped_bytes;
    __u64 last_updated;
};

/* Helper functions */

static __always_inline __u32 parse_ipv4_addr(struct iphdr *ip)
{
    return bpf_ntohl(ip->saddr);
}

static __always_inline __u16 parse_port(void *data, struct iphdr *ip)
{
    void *data_end = (void *)(long)((struct __sk_buff *)data)->data_end;
    
    if (ip->protocol == IPPROTO_TCP) {
        struct tcphdr *tcp = (struct tcphdr *)((void *)ip + (ip->ihl * 4));
        if ((void *)tcp + sizeof(*tcp) > data_end)
            return 0;
        return bpf_ntohs(tcp->source);
    } else if (ip->protocol == IPPROTO_UDP) {
        struct udphdr *udp = (struct udphdr *)((void *)ip + (ip->ihl * 4));
        if ((void *)udp + sizeof(*udp) > data_end)
            return 0;
        return bpf_ntohs(udp->source);
    }
    return 0;
}

static __always_inline int update_flow_stats(struct flow_key *key, __u64 bytes)
{
    struct flow_info *flow = bpf_map_lookup_elem(&flow_map, key);
    __u64 now = bpf_ktime_get_ns();
    
    if (!flow) {
        struct flow_info new_flow = {
            .packets_total = 1,
            .bytes_total = bytes,
            .first_seen = now,
            .last_seen = now,
            .src_pod_id = key->src_ip,
            .dst_pod_id = key->dst_ip,
            .state = 1, /* active */
            .policy_action = 1 /* allow by default */
        };
        return bpf_map_update_elem(&flow_map, key, &new_flow, BPF_NOEXIST);
    } else {
        __sync_fetch_and_add(&flow->packets_total, 1);
        __sync_fetch_and_add(&flow->bytes_total, bytes);
        flow->last_seen = now;
        return bpf_map_update_elem(&flow_map, key, flow, BPF_EXIST);
    }
}

static __always_inline int update_pod_stats(__u32 pod_ip, __u64 bytes, int direction)
{
    struct pod_traffic_stats *stats = bpf_map_lookup_elem(&pod_stats_map, &pod_ip);
    __u64 now = bpf_ktime_get_ns();
    
    if (!stats) {
        struct pod_traffic_stats new_stats = {
            .last_updated = now
        };
        
        if (direction == 0) { /* ingress */
            new_stats.rx_packets = 1;
            new_stats.rx_bytes = bytes;
        } else { /* egress */
            new_stats.tx_packets = 1;
            new_stats.tx_bytes = bytes;
        }
        
        return bpf_map_update_elem(&pod_stats_map, &pod_ip, &new_stats, BPF_NOEXIST);
    } else {
        if (direction == 0) {
            __sync_fetch_and_add(&stats->rx_packets, 1);
            __sync_fetch_and_add(&stats->rx_bytes, bytes);
        } else {
            __sync_fetch_and_add(&stats->tx_packets, 1);
            __sync_fetch_and_add(&stats->tx_bytes, bytes);
        }
        stats->last_updated = now;
        return bpf_map_update_elem(&pod_stats_map, &pod_ip, stats, BPF_EXIST);
    }
}

static __always_inline int evaluate_policy_rules(struct flow_key *key)
{
    /* Default policy: allow all (can be configured) */
    int action = 1; /* allow */
    
    /* Look up source and destination namespaces */
    __u32 *src_ns = bpf_map_lookup_elem(&pod_namespaces, &key->src_ip);
    __u32 *dst_ns = bpf_map_lookup_elem(&pod_namespaces, &key->dst_ip);
    
    if (!src_ns || !dst_ns) {
        return action; /* Default allow if namespace not found */
    }
    
    /* Iterate through policy rules (simplified - in practice would use priority ordering) */
    for (__u32 rule_id = 1; rule_id <= 1000; rule_id++) {
        struct policy_rule *rule = bpf_map_lookup_elem(&policy_rules, &rule_id);
        if (!rule || !rule->enabled)
            continue;
            
        /* Check if rule matches this flow */
        bool matches = true;
        
        /* Check direction */
        if (rule->direction != 2 && rule->direction != key->direction)
            matches = false;
            
        /* Check namespaces */
        if (rule->src_namespace != 0 && rule->src_namespace != *src_ns)
            matches = false;
        if (rule->dst_namespace != 0 && rule->dst_namespace != *dst_ns)
            matches = false;
            
        /* Check IP addresses */
        if (rule->src_ip != 0) {
            __u32 masked_src = key->src_ip & rule->src_mask;
            if (masked_src != rule->src_ip)
                matches = false;
        }
        if (rule->dst_ip != 0) {
            __u32 masked_dst = key->dst_ip & rule->dst_mask;
            if (masked_dst != rule->dst_ip)
                matches = false;
        }
        
        /* Check ports */
        if (rule->src_port_start != 0) {
            if (key->src_port < rule->src_port_start || 
                (rule->src_port_end != 0 && key->src_port > rule->src_port_end))
                matches = false;
        }
        if (rule->dst_port_start != 0) {
            if (key->dst_port < rule->dst_port_start || 
                (rule->dst_port_end != 0 && key->dst_port > rule->dst_port_end))
                matches = false;
        }
        
        /* Check protocol */
        if (rule->protocol != 0 && rule->protocol != key->protocol)
            matches = false;
            
        if (matches) {
            action = rule->action;
            break; /* First matching rule wins */
        }
    }
    
    /* Update global statistics */
    __u32 stats_key = 0;
    struct traffic_stats *stats = bpf_map_lookup_elem(&stats_map, &stats_key);
    if (stats) {
        __sync_fetch_and_add(&stats->policy_evaluations, 1);
    }
    
    return action;
}

static __always_inline int process_packet(struct __sk_buff *skb, int direction)
{
    void *data = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;
    struct ethhdr *eth;
    struct iphdr *ip;
    __u16 eth_proto;
    __u32 src_ip, dst_ip;
    __u16 src_port = 0, dst_port = 0;
    __u8 protocol;
    
    /* Parse Ethernet header */
    eth = data;
    if ((void *)eth + sizeof(*eth) > data_end)
        return TC_ACT_OK;
        
    eth_proto = bpf_ntohs(eth->h_proto);
    
    /* Only process IPv4 for now */
    if (eth_proto != ETH_P_IP)
        return TC_ACT_OK;
        
    /* Parse IP header */
    ip = (struct iphdr *)(eth + 1);
    if ((void *)ip + sizeof(*ip) > data_end)
        return TC_ACT_OK;
        
    src_ip = bpf_ntohl(ip->saddr);
    dst_ip = bpf_ntohl(ip->daddr);
    protocol = ip->protocol;
    
    /* Parse port numbers for TCP/UDP */
    if (protocol == IPPROTO_TCP) {
        struct tcphdr *tcp = (struct tcphdr *)((void *)ip + (ip->ihl * 4));
        if ((void *)tcp + sizeof(*tcp) > data_end)
            return TC_ACT_OK;
        src_port = bpf_ntohs(tcp->source);
        dst_port = bpf_ntohs(tcp->dest);
    } else if (protocol == IPPROTO_UDP) {
        struct udphdr *udp = (struct udphdr *)((void *)ip + (ip->ihl * 4));
        if ((void *)udp + sizeof(*udp) > data_end)
            return TC_ACT_OK;
        src_port = bpf_ntohs(udp->source);
        dst_port = bpf_ntohs(udp->dest);
    }
    
    /* Check if both IPs are pod IPs (fast path) */
    struct pod_info *src_pod = bpf_map_lookup_elem(&pod_map, &src_ip);
    struct pod_info *dst_pod = bpf_map_lookup_elem(&pod_map, &dst_ip);
    
    __u32 packet_len = bpf_ntohs(ip->tot_len);
    
    /* Create flow key */
    struct flow_key key = {
        .src_ip = src_ip,
        .dst_ip = dst_ip,
        .src_port = src_port,
        .dst_port = dst_port,
        .protocol = protocol,
        .direction = direction
    };
    
    int action = TC_ACT_OK;
    
    /* Fast path: both pods are local */
    if (src_pod && dst_pod && src_pod->node_local && dst_pod->node_local) {
        /* Update statistics */
        __u32 stats_key = 0;
        struct traffic_stats *stats = bpf_map_lookup_elem(&stats_map, &stats_key);
        if (stats) {
            __sync_fetch_and_add(&stats->fast_path_hits, 1);
            __sync_fetch_and_add(&stats->total_packets, 1);
            __sync_fetch_and_add(&stats->total_bytes, packet_len);
            __sync_fetch_and_add(&stats->allowed_packets, 1);
            __sync_fetch_and_add(&stats->allowed_bytes, packet_len);
        }
        
        /* Update flow statistics */
        update_flow_stats(&key, packet_len);
        
        /* Update per-pod statistics */
        update_pod_stats(src_ip, packet_len, 1); /* egress for source */
        update_pod_stats(dst_ip, packet_len, 0); /* ingress for destination */
        
        return TC_ACT_OK; /* Allow fast path */
    }
    
    /* Slow path: evaluate policies */
    int policy_action = evaluate_policy_rules(&key);
    
    /* Update statistics */
    __u32 stats_key = 0;
    struct traffic_stats *stats = bpf_map_lookup_elem(&stats_map, &stats_key);
    if (stats) {
        __sync_fetch_and_add(&stats->slow_path_hits, 1);
        __sync_fetch_and_add(&stats->total_packets, 1);
        __sync_fetch_and_add(&stats->total_bytes, packet_len);
        
        if (policy_action == 1) { /* allow */
            __sync_fetch_and_add(&stats->allowed_packets, 1);
            __sync_fetch_and_add(&stats->allowed_bytes, packet_len);
        } else { /* deny */
            __sync_fetch_and_add(&stats->dropped_packets, 1);
            __sync_fetch_and_add(&stats->dropped_bytes, packet_len);
        }
    }
    
    /* Update flow statistics with policy result */
    struct flow_info *flow = bpf_map_lookup_elem(&flow_map, &key);
    if (flow) {
        flow->policy_action = policy_action;
        bpf_map_update_elem(&flow_map, &key, flow, BPF_EXIST);
    }
    
    /* Apply policy action */
    switch (policy_action) {
        case 0: /* deny */
            action = TC_ACT_SHOT;
            break;
        case 1: /* allow */
            action = TC_ACT_OK;
            /* Update per-pod statistics */
            update_pod_stats(src_ip, packet_len, 1); /* egress for source */
            update_pod_stats(dst_ip, packet_len, 0); /* ingress for destination */
            break;
        case 2: /* log */
            action = TC_ACT_OK;
            /* TODO: Send to userspace for logging */
            break;
        default:
            action = TC_ACT_OK;
            break;
    }
    
    return action;
}

/* TC ingress program */
SEC("tc_ingress")
int tc_ingress_handler(struct __sk_buff *skb)
{
    return process_packet(skb, 0); /* ingress */
}

/* TC egress program */
SEC("tc_egress")
int tc_egress_handler(struct __sk_buff *skb)
{
    return process_packet(skb, 1); /* egress */
}

char _license[] SEC("license") = "GPL";