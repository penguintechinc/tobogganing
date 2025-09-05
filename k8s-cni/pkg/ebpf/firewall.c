// SPDX-License-Identifier: GPL-2.0
//
// eBPF firewall program for Kubernetes CNI network policy enforcement
// This program implements stateless firewall rules with TC hooks for
// high-performance packet filtering and policy enforcement.
//
// Features:
// - Namespace-aware policy enforcement
// - Protocol-specific rules (TCP, UDP, ICMP)
// - Port-based filtering with ranges
// - Priority-based rule processing
// - Real-time policy updates without pod restart
// - Audit logging for policy violations

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/icmp.h>
#include <linux/pkt_cls.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

// Maximum number of policy rules and namespaces
#define MAX_POLICY_RULES 8192
#define MAX_NAMESPACES 256
#define MAX_PODS 4096

// Policy rule actions
#define POLICY_DENY  0
#define POLICY_ALLOW 1
#define POLICY_LOG   2

// Protocol constants
#define PROTO_ANY  0
#define PROTO_TCP  6
#define PROTO_UDP  17
#define PROTO_ICMP 1

// Direction constants
#define DIR_INGRESS 0
#define DIR_EGRESS  1
#define DIR_BOTH    2

// Policy rule structure - matches Manager firewall system
struct firewall_rule {
    __u32 rule_id;
    __u32 priority;        // Lower number = higher priority
    __u32 src_namespace;   // Source namespace hash (0 = any)
    __u32 dst_namespace;   // Destination namespace hash (0 = any)
    __u32 src_ip;          // Source IP (0 = any)
    __u32 src_mask;        // Source netmask
    __u32 dst_ip;          // Destination IP (0 = any)
    __u32 dst_mask;        // Destination netmask
    __u16 src_port_start;  // Source port range start (0 = any)
    __u16 src_port_end;    // Source port range end (0 = any)
    __u16 dst_port_start;  // Destination port range start (0 = any)
    __u16 dst_port_end;    // Destination port range end (0 = any)
    __u8 protocol;         // IP protocol (0 = any)
    __u8 direction;        // Traffic direction
    __u8 action;           // Policy action
    __u8 enabled;          // Rule enabled flag
    __u64 created_time;    // Rule creation timestamp
    __u64 match_count;     // Number of packets matched
    __u64 byte_count;      // Number of bytes matched
};

// Pod namespace mapping
struct pod_namespace {
    __u32 pod_ip;
    __u32 namespace_hash;
    char namespace_name[32];
    char pod_name[64];
    __u64 last_updated;
};

// Policy violation log entry
struct policy_violation {
    __u32 src_ip;
    __u32 dst_ip;
    __u16 src_port;
    __u16 dst_port;
    __u8 protocol;
    __u8 direction;
    __u32 rule_id;        // Rule that caused the violation
    __u64 timestamp;
    __u32 src_namespace;
    __u32 dst_namespace;
};

// BPF Maps for firewall data
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, MAX_POLICY_RULES);
    __type(key, __u32);
    __type(value, struct firewall_rule);
} policy_rules SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_PODS);
    __type(key, __u32);  // Pod IP
    __type(value, struct pod_namespace);
} pod_namespaces SEC(".maps");

// Ring buffer for policy violation events
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 16); // 64KB ring buffer
} violation_events SEC(".maps");

// Firewall statistics
struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 32);
    __type(key, __u32);
    __type(value, __u64);
} firewall_stats SEC(".maps");

// Firewall statistics indices
#define FW_STAT_PACKETS_PROCESSED 0
#define FW_STAT_PACKETS_ALLOWED   1
#define FW_STAT_PACKETS_DENIED    2
#define FW_STAT_POLICY_VIOLATIONS 3
#define FW_STAT_RULES_MATCHED     4
#define FW_STAT_DEFAULT_ALLOWS    5
#define FW_STAT_DEFAULT_DENIES    6
#define FW_STAT_PROCESSING_TIME   7

// Configuration flags
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 8);
    __type(key, __u32);
    __type(value, __u32);
} firewall_config SEC(".maps");

#define CONFIG_DEFAULT_POLICY 0  // 0=deny, 1=allow
#define CONFIG_LOG_VIOLATIONS 1  // 0=disabled, 1=enabled
#define CONFIG_AUDIT_MODE     2  // 0=enforce, 1=audit only
#define CONFIG_RULE_COUNT     3  // Number of active rules

// Helper function to update firewall statistics
static inline void update_fw_stat(__u32 index, __u64 delta) {
    __u64 *stat = bpf_map_lookup_elem(&firewall_stats, &index);
    if (stat) {
        __sync_fetch_and_add(stat, delta);
    }
}

// Helper function to get configuration value
static inline __u32 get_config(__u32 key) {
    __u32 *value = bpf_map_lookup_elem(&firewall_config, &key);
    return value ? *value : 0;
}

// Helper function to check if IP is in subnet
static inline int ip_in_subnet(__u32 ip, __u32 subnet, __u32 mask) {
    if (mask == 0) return 1; // Any IP matches
    return (ip & mask) == (subnet & mask);
}

// Helper function to check if port is in range
static inline int port_in_range(__u16 port, __u16 start, __u16 end) {
    if (start == 0 && end == 0) return 1; // Any port matches
    if (end == 0) end = start; // Single port
    return port >= start && port <= end;
}

// Helper function to get namespace for pod IP
static inline __u32 get_pod_namespace(__u32 pod_ip) {
    struct pod_namespace *pod_ns = bpf_map_lookup_elem(&pod_namespaces, &pod_ip);
    return pod_ns ? pod_ns->namespace_hash : 0;
}

// Helper function to log policy violation
static inline void log_violation(__u32 src_ip, __u32 dst_ip, __u16 src_port, __u16 dst_port, 
                                __u8 protocol, __u8 direction, __u32 rule_id) {
    if (!get_config(CONFIG_LOG_VIOLATIONS)) return;
    
    struct policy_violation *violation = bpf_ringbuf_reserve(&violation_events, 
                                                           sizeof(struct policy_violation), 0);
    if (!violation) return;
    
    violation->src_ip = src_ip;
    violation->dst_ip = dst_ip;
    violation->src_port = src_port;
    violation->dst_port = dst_port;
    violation->protocol = protocol;
    violation->direction = direction;
    violation->rule_id = rule_id;
    violation->timestamp = bpf_ktime_get_ns();
    violation->src_namespace = get_pod_namespace(src_ip);
    violation->dst_namespace = get_pod_namespace(dst_ip);
    
    bpf_ringbuf_submit(violation, 0);
    update_fw_stat(FW_STAT_POLICY_VIOLATIONS, 1);
}

// Main firewall policy evaluation function
static inline int evaluate_policy(__u32 src_ip, __u32 dst_ip, __u16 src_port, __u16 dst_port,
                                 __u8 protocol, __u8 direction) {
    __u32 src_namespace = get_pod_namespace(src_ip);
    __u32 dst_namespace = get_pod_namespace(dst_ip);
    __u32 rule_count = get_config(CONFIG_RULE_COUNT);
    
    // Iterate through policy rules in priority order
    for (__u32 i = 0; i < rule_count && i < MAX_POLICY_RULES; i++) {
        struct firewall_rule *rule = bpf_map_lookup_elem(&policy_rules, &i);
        if (!rule || !rule->enabled) continue;
        
        // Check direction
        if (rule->direction != DIR_BOTH && rule->direction != direction) continue;
        
        // Check protocol
        if (rule->protocol != PROTO_ANY && rule->protocol != protocol) continue;
        
        // Check source namespace
        if (rule->src_namespace != 0 && rule->src_namespace != src_namespace) continue;
        
        // Check destination namespace
        if (rule->dst_namespace != 0 && rule->dst_namespace != dst_namespace) continue;
        
        // Check source IP/subnet
        if (!ip_in_subnet(src_ip, rule->src_ip, rule->src_mask)) continue;
        
        // Check destination IP/subnet
        if (!ip_in_subnet(dst_ip, rule->dst_ip, rule->dst_mask)) continue;
        
        // Check source port range
        if (!port_in_range(src_port, rule->src_port_start, rule->src_port_end)) continue;
        
        // Check destination port range
        if (!port_in_range(dst_port, rule->dst_port_start, rule->dst_port_end)) continue;
        
        // Rule matches - update statistics
        __sync_fetch_and_add(&rule->match_count, 1);
        update_fw_stat(FW_STAT_RULES_MATCHED, 1);
        
        // Apply action
        if (rule->action == POLICY_DENY) {
            log_violation(src_ip, dst_ip, src_port, dst_port, protocol, direction, rule->rule_id);
            return 0; // Deny
        } else if (rule->action == POLICY_ALLOW) {
            return 1; // Allow
        }
        // POLICY_LOG continues to next rule
    }
    
    // No matching rule - apply default policy
    __u32 default_policy = get_config(CONFIG_DEFAULT_POLICY);
    if (default_policy == POLICY_ALLOW) {
        update_fw_stat(FW_STAT_DEFAULT_ALLOWS, 1);
        return 1;
    } else {
        update_fw_stat(FW_STAT_DEFAULT_DENIES, 1);
        log_violation(src_ip, dst_ip, src_port, dst_port, protocol, direction, 0);
        return 0;
    }
}

// TC ingress firewall handler
SEC("tc/fw_ingress")
int firewall_ingress(struct __sk_buff *skb) {
    __u64 start_time = bpf_ktime_get_ns();
    void *data = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;
    
    update_fw_stat(FW_STAT_PACKETS_PROCESSED, 1);
    
    // Parse ethernet header
    struct ethhdr *eth = (struct ethhdr *)data;
    if ((void *)(eth + 1) > data_end) {
        return TC_ACT_OK;
    }
    
    if (eth->h_proto != bpf_htons(ETH_P_IP)) {
        return TC_ACT_OK; // Allow non-IP traffic
    }
    
    // Parse IP header
    struct iphdr *iph = (struct iphdr *)(eth + 1);
    if ((void *)(iph + 1) > data_end) {
        return TC_ACT_OK;
    }
    
    if (iph->version != 4 || iph->ihl < 5) {
        return TC_ACT_OK;
    }
    
    __u32 src_ip = bpf_ntohl(iph->saddr);
    __u32 dst_ip = bpf_ntohl(iph->daddr);
    __u16 src_port = 0, dst_port = 0;
    
    // Parse transport layer for port information
    void *transport = (void *)iph + (iph->ihl * 4);
    
    if (iph->protocol == IPPROTO_TCP) {
        struct tcphdr *tcph = transport;
        if ((void *)(tcph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(tcph->source);
        dst_port = bpf_ntohs(tcph->dest);
    } else if (iph->protocol == IPPROTO_UDP) {
        struct udphdr *udph = transport;
        if ((void *)(udph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(udph->source);
        dst_port = bpf_ntohs(udph->dest);
    }
    
    // Evaluate firewall policy
    int policy_result = evaluate_policy(src_ip, dst_ip, src_port, dst_port, 
                                       iph->protocol, DIR_INGRESS);
    
    // Update statistics and processing time
    __u64 processing_time = bpf_ktime_get_ns() - start_time;
    update_fw_stat(FW_STAT_PROCESSING_TIME, processing_time);
    
    // Apply policy decision
    if (policy_result) {
        update_fw_stat(FW_STAT_PACKETS_ALLOWED, 1);
        return TC_ACT_OK; // Allow packet
    } else {
        update_fw_stat(FW_STAT_PACKETS_DENIED, 1);
        
        // Check if in audit mode (log but don't drop)
        if (get_config(CONFIG_AUDIT_MODE)) {
            return TC_ACT_OK; // Allow in audit mode
        }
        
        return TC_ACT_SHOT; // Drop packet
    }
}

// TC egress firewall handler
SEC("tc/fw_egress")
int firewall_egress(struct __sk_buff *skb) {
    __u64 start_time = bpf_ktime_get_ns();
    void *data = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;
    
    update_fw_stat(FW_STAT_PACKETS_PROCESSED, 1);
    
    // Parse ethernet header
    struct ethhdr *eth = (struct ethhdr *)data;
    if ((void *)(eth + 1) > data_end) {
        return TC_ACT_OK;
    }
    
    if (eth->h_proto != bpf_htons(ETH_P_IP)) {
        return TC_ACT_OK; // Allow non-IP traffic
    }
    
    // Parse IP header
    struct iphdr *iph = (struct iphdr *)(eth + 1);
    if ((void *)(iph + 1) > data_end) {
        return TC_ACT_OK;
    }
    
    if (iph->version != 4 || iph->ihl < 5) {
        return TC_ACT_OK;
    }
    
    __u32 src_ip = bpf_ntohl(iph->saddr);
    __u32 dst_ip = bpf_ntohl(iph->daddr);
    __u16 src_port = 0, dst_port = 0;
    
    // Parse transport layer for port information
    void *transport = (void *)iph + (iph->ihl * 4);
    
    if (iph->protocol == IPPROTO_TCP) {
        struct tcphdr *tcph = transport;
        if ((void *)(tcph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(tcph->source);
        dst_port = bpf_ntohs(tcph->dest);
    } else if (iph->protocol == IPPROTO_UDP) {
        struct udphdr *udph = transport;
        if ((void *)(udph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(udph->source);
        dst_port = bpf_ntohs(udph->dest);
    }
    
    // Evaluate firewall policy for egress traffic
    int policy_result = evaluate_policy(src_ip, dst_ip, src_port, dst_port, 
                                       iph->protocol, DIR_EGRESS);
    
    // Update statistics and processing time
    __u64 processing_time = bpf_ktime_get_ns() - start_time;
    update_fw_stat(FW_STAT_PROCESSING_TIME, processing_time);
    
    // Apply policy decision
    if (policy_result) {
        update_fw_stat(FW_STAT_PACKETS_ALLOWED, 1);
        return TC_ACT_OK; // Allow packet
    } else {
        update_fw_stat(FW_STAT_PACKETS_DENIED, 1);
        
        // Check if in audit mode (log but don't drop)
        if (get_config(CONFIG_AUDIT_MODE)) {
            return TC_ACT_OK; // Allow in audit mode
        }
        
        return TC_ACT_SHOT; // Drop packet
    }
}

char __license[] SEC("license") = "GPL";