# SASE Blocklist Enforcement Contract

**Status**: Design approved (Slice A, Task 5)  
**Date**: 2026-08-04

## Overview

This document specifies the contract for the Go/Rust Inspection Point (data plane) to enforce SASE blocklist verdicts at wire-speed. Inspection Points **READ** Valkey directly (not hub-api gRPC); check per-flow IOCs asynchronously; enforce on **future** traffic only; and **fail open** on miss/outage.

## Architecture

```
hub-api (control plane)          Inspection Point (data plane)
       |                                    |
       | → BlocklistStore.put              |
       | → sase:blocklist:ip:1.2.3.4       |
       | → sase:blocklist:domain:bad.com   |
       | → sase:blocklist:url:<sha256>     |
       | → sase:blocklist:hash:<sha256>    |
       |                                    |
       | Async, O(1) writes/dedup/TTL       |
       |                                    | ← Direct Valkey read (read-only ACL)
       |                         Each flow: |
       |                         • dest IP/domain
       |                         • requested URL
       |                         • downloaded file hash
       |                         → check sase:blocklist:*
       |                         → cache miss → ALLOW (fail open)
       |                         → cache miss/outage → ALLOW
```

## Read-Only Access Pattern

### Key Namespace

Inspection Points hold a **read-only** ACL on the `sase:blocklist:*` key prefix via service account:

```
COMMAND ACL CAT
COMMAND ACL SETUSER inspection-point >hash... ~sase:blocklist:* +get +@read -@write
```

- Service account `inspection-point` (or service-specific: `inspection-point-us-west-1`)
- Permissions: `+get +@read -@write`
- Key pattern: `~sase:blocklist:*` (exact prefix allowlist)
- No pub/sub, no admin operations

### Per-Flow Lookup

For each flow (connection, request, transfer):

1. **Extract IOC values**:
   - Destination IP: `flow.dest_ip`
   - Destination domain: DNS query results, SNI, HTTP `Host` header
   - URL: requested path if `flow.is_http`, compute `sha256(url)`
   - File hash: downloaded file, compute `sha256(content)` or use feed-provided hash

2. **Construct key**:
   ```
   ip key      = "sase:blocklist:ip:" + dest_ip
   domain key  = "sase:blocklist:domain:" + domain
   url key     = "sase:blocklist:url:" + sha256(url)
   hash key    = "sase:blocklist:hash:" + sha256_hex
   ```

3. **Read from Valkey**:
   ```rust
   // Pseudocode: Go/Rust Inspection Point
   async fn check_ioc(ioc_type: &str, value: &str) -> Option<Verdict> {
       let key = format!("sase:blocklist:{}:{}", ioc_type, value);
       match redis_client.get(&key).await {
           Ok(Some(json)) => serde_json::from_str(&json).ok(),
           Ok(None) => None,          // Not in blocklist → ALLOW
           Err(_) => None,            // Cache error → ALLOW (fail open)
       }
   }
   ```

4. **Return**: `Verdict | None` (no error)

## Verdict Schema (Enforcement View)

Read from cache as JSON; parse into typed struct:

```rust
#[derive(Deserialize)]
struct Verdict {
    ioc_type: String,           // "ip", "domain", "url", "hash"
    value: String,              // IOC value (url already sha256'd in key)
    severity: String,           // "low", "medium", "high", "critical"
    source: String,             // Feed name (e.g., "spamhaus", "urlhaus")
    stix_id: String,            // STIX Indicator ID (audit trail)
    first_seen: i64,            // Unix timestamp (context, not enforcement)
    expiry: Option<i64>,        // Unix timestamp, None = indefinite
}
```

- **No action field**: Verdict contains **only** the IOC + provenance. Action (drop/reject/soft-block/log-only) is **policy**, resolved separately (Slice B).
- **Expiry**: If set and `expiry < now()`, verdict is stale. Treat same as cache miss (ALLOW). Valkey TTL is the enforcement: entry auto-expires.

## Enforcement Rules

### Traffic Handling

- **Future traffic only**: Enforcement applies to NEW flows/requests initiated AFTER verdict lookup, not retroactive to in-flight connections.
- **Per-packet/flow decision**: Each packet/flow/stream makes a fresh lookup (no connection-level caching of the verdict lookup result itself, though Valkey handles cache semantics).

### Action Mapping (Slice B)

Verdict → Action is **policy-driven, not stored in the verdict**:

```
Slice B (future) resolves:
  severity="critical" + source="spamhaus" → action=drop
  severity="high" + source="urlhaus"      → action=reject
  severity="low" + source="custom"        → action=log_only
  (etc. — policy engine, not data plane)
```

Slice A (blocklist) only stores the IOC + severity. Inspection Point consults the Verdict; the policy engine (running on-box or via control-plane push) maps `(severity, source, context...)` → action.

### Fail-Open Guarantee

On **any error, missing lookup, or outage**:

```rust
// Pseudocode
match check_ioc("ip", "1.2.3.4").await {
    Some(verdict) => { /* decide action via policy */ }
    None => { /* ALLOW: miss, cache error, expired TTL, all map to ALLOW */ }
}
```

- Cache unreachable: **ALLOW** (out-of-band mandate: never add latency)
- Key not found (IOC not in blocklist): **ALLOW**
- Verdict expired (Valkey TTL'd it): **ALLOW**
- Deserialization error: **ALLOW**, log at DEBUG
- No latency budget for retries/fallback: direct Valkey read, 1-shot, then move on

## Scope Boundaries

### In Scope (Slice A)

- ✅ IOC normalization + STIX canonical representation
- ✅ Valkey blocklist O(1) store
- ✅ Curator from `threat_indicators` feed table
- ✅ Read-only hub-api admin endpoint (`GET /api/v1/sase/blocklist/check`)
- ✅ Enforcement contract (this document)

### Out of Scope (Later Slices)

- ❌ Inspection Point binary (Slice C/D — Go/Rust, not hub-api)
- ❌ Action policy engine (`severity + source + context → action`) — **Slice B**
- ❌ Block page / user notification — **Slice C**
- ❌ Category cache (`sase:catcache:*`) for SWG filtering — **Slice B**
- ❌ Analysis adapter writers (Suricata, Strelka, CAPE) — **Slice D**

## Implementation Checklist (Data Plane)

- [ ] Service account with read-only `sase:blocklist:*` ACL configured in Valkey
- [ ] Per-flow IOC extraction (IP, domain, URL hash, file hash)
- [ ] Valkey key construction per IOC type
- [ ] Async read (`GET key`), fail open on error
- [ ] Verdict JSON deserialization (typed struct)
- [ ] Expiry check (if `verdict.expiry < now()`, treat as miss)
- [ ] Zero latency: 1-shot read, no retries, no fallback to gRPC
- [ ] Integration with policy engine (on-box or pushed) for action decision
- [ ] Observability: verdict cache hits/misses/errors logged at flow summary level

## Example: Flow Decision

```
Flow: TCP dst=1.2.3.4:80 src=203.0.113.1
  1. Extract IOC: ioc_type="ip", value="1.2.3.4"
  2. Check Valkey: GET "sase:blocklist:ip:1.2.3.4"
     Result: {"severity":"high", "source":"spamhaus", "stix_id":"...", ...}
  3. Verdict found: severity=high
  4. Policy engine: high + spamhaus → action=drop
  5. Enforce: RST/drop future packets on this flow
  6. Log: flow_id, verdict, action, duration=<ms>
```

```
Flow: DNS query qname=safe.example.com
  1. Extract IOC: ioc_type="domain", value="safe.example.com"
  2. Check Valkey: GET "sase:blocklist:domain:safe.example.com"
     Result: nil (cache miss)
  3. No verdict: action=allow
  4. Enforce: allow query to proceed
  5. Log: flow_id, "verdict_miss", action=allow
```

## Performance Notes

- **Latency**: ~1–5ms per Valkey read (local cluster, no cross-region hops)
- **Throughput**: Valkey can sustain 100K+ reads/sec (per instance)
- **Memory**: Verdict JSON ~200 bytes avg; 1M entries ≈ 200MB (shared with auth revocation cache)
- **TTL overhead**: Valkey background eviction, no on-box sweep needed

## Compliance & Audit

- **Audit trail**: `stix_id` links to canonical STIX Indicator in hub-api (audit log)
- **Provenance**: `source` field identifies feed origin (e.g., "spamhaus", "urlhaus")
- **Severity**: queryable in logs/metrics for compliance reporting
- **Expiry**: Verdicts older than feed retention are auto-dropped by Valkey TTL

---

**Next Steps**: Slice B (policy engine), Slice C (block pages), Slice D (analysis adapters).
