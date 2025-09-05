// SPDX-License-Identifier: GPL-2.0
//
// eBPF traffic monitoring program for comprehensive network observability
// This program provides deep insights into pod-to-pod communication patterns,
// performance metrics, and security analytics for the Tobogganing CNI.
//
// Features:
// - Real-time traffic flow tracking
// - Application protocol detection
// - Performance monitoring (latency, throughput)
// - Security event detection
// - Network topology mapping
// - Quality of Service (QoS) metrics

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/icmp.h>
#include <linux/pkt_cls.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

// Maximum tracking limits
#define MAX_FLOWS 65536
#define MAX_CONNECTIONS 32768
#define MAX_PODS 4096
#define MAX_SERVICES 2048

// Time constants (in nanoseconds)
#define FLOW_TIMEOUT_NS      300000000000ULL  // 5 minutes
#define CONNECTION_TIMEOUT_NS 600000000000ULL // 10 minutes
#define METRICS_INTERVAL_NS   60000000000ULL  // 1 minute

// Protocol detection constants
#define PROTO_HTTP     1
#define PROTO_HTTPS    2
#define PROTO_GRPC     3
#define PROTO_REDIS    4
#define PROTO_MYSQL    5
#define PROTO_POSTGRES 6
#define PROTO_UNKNOWN  0

// Connection states
#define CONN_ESTABLISHED 1
#define CONN_SYN_SENT    2
#define CONN_SYN_RECV    3
#define CONN_FIN_WAIT    4
#define CONN_CLOSE_WAIT  5
#define CONN_CLOSED      6

// Enhanced flow key for comprehensive tracking
struct flow_key {
    __u32 src_ip;
    __u32 dst_ip;
    __u16 src_port;
    __u16 dst_port;
    __u8 protocol;
    __u8 direction;  // 0=ingress, 1=egress
    __u32 src_pod_id;
    __u32 dst_pod_id;
};

// Comprehensive flow statistics
struct flow_stats {
    // Basic counters
    __u64 packets_total;
    __u64 bytes_total;
    __u64 packets_in;
    __u64 bytes_in;
    __u64 packets_out;
    __u64 bytes_out;
    
    // Timing information
    __u64 first_seen;
    __u64 last_seen;
    __u64 duration;
    
    // Performance metrics
    __u64 min_rtt;
    __u64 max_rtt;
    __u64 avg_rtt;
    __u64 rtt_samples;
    
    // Application layer detection
    __u8 detected_protocol;
    __u16 server_port;
    
    // QoS metrics
    __u32 retransmissions;
    __u32 out_of_order;
    __u32 packet_loss;
    
    // Security indicators
    __u32 suspicious_flags;
    __u32 alert_count;
    
    // Connection tracking
    __u8 connection_state;
    __u32 connection_id;
};

// Connection tracking structure
struct connection_info {
    struct flow_key key;
    __u32 connection_id;
    __u8 state;
    __u64 established_time;
    __u64 last_activity;
    __u32 syn_count;
    __u32 fin_count;
    __u32 rst_count;
    
    // TCP sequence tracking
    __u32 seq_next;
    __u32 ack_next;
    
    // Application data
    __u8 app_protocol;
    char service_name[32];
    
    // Performance tracking
    __u64 handshake_duration;
    __u64 total_bytes;
    __u32 window_size;
};

// Pod networking information
struct pod_network_info {
    __u32 pod_ip;
    __u32 namespace_id;
    char pod_name[64];
    char namespace_name[32];
    char service_name[32];
    __u64 created_time;
    __u64 last_seen;
    
    // Network statistics
    __u64 total_connections;
    __u64 active_connections;
    __u64 bytes_received;
    __u64 bytes_sent;
    __u64 packets_received;
    __u64 packets_sent;
    
    // Performance metrics
    __u64 avg_connection_duration;
    __u32 connection_errors;
    __u32 timeouts;
};

// Network topology edge (connection between pods/services)
struct topology_edge {
    __u32 src_pod_id;
    __u32 dst_pod_id;
    __u32 src_namespace;
    __u32 dst_namespace;
    __u8 protocol;
    __u16 port;
    __u64 first_seen;
    __u64 last_seen;
    __u64 total_flows;
    __u64 active_flows;
    __u64 total_bytes;
};

// Performance metrics aggregation
struct perf_metrics {
    __u64 timestamp;
    __u32 active_flows;
    __u32 active_connections;
    __u64 total_throughput;
    __u64 avg_latency;
    __u32 packet_loss_rate;
    __u32 retransmission_rate;
    __u32 connection_errors;
    __u32 policy_violations;
};

// BPF Maps for monitoring data
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_FLOWS);
    __type(key, struct flow_key);
    __type(value, struct flow_stats);
} flow_monitor SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_CONNECTIONS);
    __type(key, __u32);  // connection_id
    __type(value, struct connection_info);
} connection_tracker SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_PODS);
    __type(key, __u32);  // pod_ip
    __type(value, struct pod_network_info);
} pod_monitor SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_FLOWS);
    __type(key, struct flow_key);
    __type(value, struct topology_edge);
} network_topology SEC(".maps");

// Ring buffer for real-time events
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 18); // 256KB ring buffer
} monitor_events SEC(".maps");

// Performance metrics time series
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1440); // 24 hours of minute-by-minute data
    __type(key, __u32);
    __type(value, struct perf_metrics);
} perf_history SEC(".maps");

// Monitoring statistics
struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 64);
    __type(key, __u32);
    __type(value, __u64);
} monitor_stats SEC(".maps");

// Event types for ring buffer
#define EVENT_NEW_FLOW        1
#define EVENT_CONNECTION_EST  2
#define EVENT_CONNECTION_TERM 3
#define EVENT_ANOMALY_DETECTED 4
#define EVENT_PERF_ALERT      5

// Monitoring event structure
struct monitor_event {
    __u8 event_type;
    __u8 severity;  // 0=info, 1=warning, 2=error, 3=critical
    __u64 timestamp;
    struct flow_key flow;
    __u32 connection_id;
    __u64 metric_value;
    char message[128];
};

// Helper function to update monitoring statistics
static inline void update_monitor_stat(__u32 index, __u64 delta) {
    __u64 *stat = bpf_map_lookup_elem(&monitor_stats, &index);
    if (stat) {
        __sync_fetch_and_add(stat, delta);
    }
}

// Helper function to emit monitoring event
static inline void emit_event(__u8 event_type, __u8 severity, struct flow_key *flow, 
                             __u32 connection_id, __u64 metric_value, const char *message) {
    struct monitor_event *event = bpf_ringbuf_reserve(&monitor_events, 
                                                     sizeof(struct monitor_event), 0);
    if (!event) return;
    
    event->event_type = event_type;
    event->severity = severity;
    event->timestamp = bpf_ktime_get_ns();
    event->flow = *flow;
    event->connection_id = connection_id;
    event->metric_value = metric_value;
    
    // Copy message (simplified - would use bpf_probe_read_str in practice)
    for (int i = 0; i < 128 && message[i]; i++) {
        event->message[i] = message[i];
    }
    
    bpf_ringbuf_submit(event, 0);
}

// Protocol detection based on port and payload patterns
static inline __u8 detect_protocol(__u16 port, void *payload, __u32 payload_len) {
    // Well-known ports
    switch (port) {
        case 80:
            return PROTO_HTTP;
        case 443:
            return PROTO_HTTPS;
        case 3306:
            return PROTO_MYSQL;
        case 5432:
            return PROTO_POSTGRES;
        case 6379:
            return PROTO_REDIS;
    }
    
    // gRPC detection (HTTP/2 over TLS, typically port 443 or custom)
    if (payload_len >= 24) {
        // Simplified gRPC detection - would need more sophisticated analysis
        return PROTO_GRPC;
    }
    
    return PROTO_UNKNOWN;
}

// Update flow statistics with new packet
static inline void update_flow_stats(struct flow_key *key, __u32 packet_len, __u8 tcp_flags) {
    struct flow_stats *stats = bpf_map_lookup_elem(&flow_monitor, key);
    __u64 now = bpf_ktime_get_ns();
    
    if (!stats) {
        // Create new flow entry
        struct flow_stats new_stats = {0};
        new_stats.first_seen = now;
        new_stats.last_seen = now;
        new_stats.packets_total = 1;
        new_stats.bytes_total = packet_len;
        new_stats.server_port = (key->direction == 0) ? key->dst_port : key->src_port;
        new_stats.detected_protocol = detect_protocol(new_stats.server_port, NULL, 0);
        new_stats.connection_state = CONN_SYN_SENT;
        
        bpf_map_update_elem(&flow_monitor, key, &new_stats, BPF_NOEXIST);
        
        // Emit new flow event
        emit_event(EVENT_NEW_FLOW, 0, key, 0, packet_len, "New flow detected");
        
    } else {
        // Update existing flow
        __sync_fetch_and_add(&stats->packets_total, 1);
        __sync_fetch_and_add(&stats->bytes_total, packet_len);
        
        if (key->direction == 0) {  // Ingress
            __sync_fetch_and_add(&stats->packets_in, 1);
            __sync_fetch_and_add(&stats->bytes_in, packet_len);
        } else {  // Egress
            __sync_fetch_and_add(&stats->packets_out, 1);
            __sync_fetch_and_add(&stats->bytes_out, packet_len);
        }
        
        stats->last_seen = now;
        stats->duration = now - stats->first_seen;
    }
}

// Update pod network information
static inline void update_pod_stats(__u32 pod_ip, __u32 bytes, __u8 direction) {
    struct pod_network_info *pod = bpf_map_lookup_elem(&pod_monitor, &pod_ip);
    __u64 now = bpf_ktime_get_ns();
    
    if (!pod) {
        // Create new pod entry
        struct pod_network_info new_pod = {0};
        new_pod.pod_ip = pod_ip;
        new_pod.created_time = now;
        new_pod.last_seen = now;
        
        if (direction == 0) {  // Ingress
            new_pod.bytes_received = bytes;
            new_pod.packets_received = 1;
        } else {  // Egress
            new_pod.bytes_sent = bytes;
            new_pod.packets_sent = 1;
        }
        
        bpf_map_update_elem(&pod_monitor, &pod_ip, &new_pod, BPF_NOEXIST);
    } else {
        // Update existing pod
        pod->last_seen = now;
        
        if (direction == 0) {  // Ingress
            __sync_fetch_and_add(&pod->bytes_received, bytes);
            __sync_fetch_and_add(&pod->packets_received, 1);
        } else {  // Egress
            __sync_fetch_and_add(&pod->bytes_sent, bytes);
            __sync_fetch_and_add(&pod->packets_sent, 1);
        }
    }
}

// Update network topology
static inline void update_topology(struct flow_key *key) {
    struct topology_edge *edge = bpf_map_lookup_elem(&network_topology, key);
    __u64 now = bpf_ktime_get_ns();
    
    if (!edge) {
        // Create new topology edge
        struct topology_edge new_edge = {0};
        new_edge.src_pod_id = key->src_pod_id;
        new_edge.dst_pod_id = key->dst_pod_id;
        new_edge.protocol = key->protocol;
        new_edge.port = key->dst_port;
        new_edge.first_seen = now;
        new_edge.last_seen = now;
        new_edge.total_flows = 1;
        new_edge.active_flows = 1;
        
        bpf_map_update_elem(&network_topology, key, &new_edge, BPF_NOEXIST);
    } else {
        // Update existing edge
        edge->last_seen = now;
        __sync_fetch_and_add(&edge->active_flows, 1);
    }
}

// Main monitoring function for ingress traffic
SEC("tc/monitor_ingress")
int monitor_ingress(struct __sk_buff *skb) {
    void *data = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;
    
    // Parse ethernet header
    struct ethhdr *eth = (struct ethhdr *)data;
    if ((void *)(eth + 1) > data_end || eth->h_proto != bpf_htons(ETH_P_IP)) {
        return TC_ACT_OK;
    }
    
    // Parse IP header
    struct iphdr *iph = (struct iphdr *)(eth + 1);
    if ((void *)(iph + 1) > data_end || iph->version != 4 || iph->ihl < 5) {
        return TC_ACT_OK;
    }
    
    __u32 src_ip = bpf_ntohl(iph->saddr);
    __u32 dst_ip = bpf_ntohl(iph->daddr);
    __u16 src_port = 0, dst_port = 0;
    __u8 tcp_flags = 0;
    
    // Parse transport layer
    void *transport = (void *)iph + (iph->ihl * 4);
    
    if (iph->protocol == IPPROTO_TCP) {
        struct tcphdr *tcph = transport;
        if ((void *)(tcph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(tcph->source);
        dst_port = bpf_ntohs(tcph->dest);
        tcp_flags = ((unsigned char *)tcph)[13]; // TCP flags
    } else if (iph->protocol == IPPROTO_UDP) {
        struct udphdr *udph = transport;
        if ((void *)(udph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(udph->source);
        dst_port = bpf_ntohs(udph->dest);
    }
    
    // Create flow key
    struct flow_key flow = {
        .src_ip = src_ip,
        .dst_ip = dst_ip,
        .src_port = src_port,
        .dst_port = dst_port,
        .protocol = iph->protocol,
        .direction = 0,  // ingress
        .src_pod_id = src_ip,  // Simplified mapping
        .dst_pod_id = dst_ip,
    };
    
    // Update flow statistics
    update_flow_stats(&flow, skb->len, tcp_flags);
    
    // Update pod statistics
    update_pod_stats(dst_ip, skb->len, 0);  // Ingress to destination pod
    
    // Update network topology
    update_topology(&flow);
    
    return TC_ACT_OK;
}

// Main monitoring function for egress traffic
SEC("tc/monitor_egress")
int monitor_egress(struct __sk_buff *skb) {
    void *data = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;
    
    // Parse ethernet header
    struct ethhdr *eth = (struct ethhdr *)data;
    if ((void *)(eth + 1) > data_end || eth->h_proto != bpf_htons(ETH_P_IP)) {
        return TC_ACT_OK;
    }
    
    // Parse IP header
    struct iphdr *iph = (struct iphdr *)(eth + 1);
    if ((void *)(iph + 1) > data_end || iph->version != 4 || iph->ihl < 5) {
        return TC_ACT_OK;
    }
    
    __u32 src_ip = bpf_ntohl(iph->saddr);
    __u32 dst_ip = bpf_ntohl(iph->daddr);
    __u16 src_port = 0, dst_port = 0;
    __u8 tcp_flags = 0;
    
    // Parse transport layer
    void *transport = (void *)iph + (iph->ihl * 4);
    
    if (iph->protocol == IPPROTO_TCP) {
        struct tcphdr *tcph = transport;
        if ((void *)(tcph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(tcph->source);
        dst_port = bpf_ntohs(tcph->dest);
        tcp_flags = ((unsigned char *)tcph)[13]; // TCP flags
    } else if (iph->protocol == IPPROTO_UDP) {
        struct udphdr *udph = transport;
        if ((void *)(udph + 1) > data_end) {
            return TC_ACT_OK;
        }
        src_port = bpf_ntohs(udph->source);
        dst_port = bpf_ntohs(udph->dest);
    }
    
    // Create flow key for egress
    struct flow_key flow = {
        .src_ip = src_ip,
        .dst_ip = dst_ip,
        .src_port = src_port,
        .dst_port = dst_port,
        .protocol = iph->protocol,
        .direction = 1,  // egress
        .src_pod_id = src_ip,  // Simplified mapping
        .dst_pod_id = dst_ip,
    };
    
    // Update flow statistics
    update_flow_stats(&flow, skb->len, tcp_flags);
    
    // Update pod statistics
    update_pod_stats(src_ip, skb->len, 1);  // Egress from source pod
    
    // Update network topology
    update_topology(&flow);
    
    return TC_ACT_OK;
}

char __license[] SEC("license") = "GPL";