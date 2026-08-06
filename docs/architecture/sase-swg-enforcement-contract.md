# SASE SWG Enforcement Contract

**Date**: 2026-08-06  
**Status**: Active  
**Scope**: Data-plane (client/headend/gateway) enforcement of SWG category policy

## Overview

The SWG (Secure Web Gateway) Tier-1 enforcement contract defines how the data plane performs inline domain categorization and applies enforcement actions. The control plane (hub-api) provides:

1. A serialized radix tree artifact (`GET /api/v1/sase/swg/radix`) — compiled domain→categories mapping
2. A unified `EnforcementAction` enum — consistent action semantics across all security layers
3. A cached policy store — category→action resolution per tenant/user/group

The data plane pulls these daily and performs O(k) inline lookups with fail-open behavior.

## Inspection Point

**Location**: Inline in the ingress gateway / client network stack (e.g., WireGuard headend, QUIC client interceptor).

**Trigger**: Every HTTP/HTTPS request on the user's flow.

**Inputs**:
- Domain extracted from HTTP `Host` header or SNI (TLS handshake)
- Tenant ID (from cluster/client metadata)
- User ID (from session/JWT)
- Group IDs (from session/JWT)
- Cached radix tree artifact
- Cached policy store (category→action mapping)

**Output**: `EnforcementAction` (allow, log_only, soft_block, block, drop)

## Enforcement Flow

```
Input: domain, tenant, user_id, group_ids
  ↓
[1] Radix lookup: domain → categories (O(k) subdomain-covering)
  ↓
  ├─ Found: proceed to [2]
  └─ Not found: proceed to [3]
  ↓
[2] Policy resolution (if categories found):
  Scope precedence: user > group > tenant
  Action selection: most-restrictive among domain's categories
  ↓
[3] No policy match / uncategorized:
  Use tenant default (allow or block, from config)
  Enqueue to Slice E for AI categorization (async hook)
  ↓
[4] Fail-open safety net:
  Any error in [1]–[3] → return allow
  Never block on cache miss or lookup timeout
  ↓
Output: EnforcementAction
  ↓
[5] Enforce action:
  ├─ allow:      Pass request to destination
  ├─ log_only:   Pass request, record event for audit
  ├─ soft_block: Serve interstitial (risky site warning), bypass on acknowledgment
  ├─ block:      Send TCP RST / HTTP 403 + block page, refuse request
  └─ drop:       Silently drop (no response to client)
```

## Artifact Format (Radix Tree)

**Endpoint**: `GET /api/v1/sase/swg/radix`

**Authentication**: Machine JWT with scope `swg:read` (issued to data-plane nodes)

**Response**:
```json
{
  "artifact": "<base64-encoded-serialized-radix>",
  "version": "1.0",
  "encoding": "base64"
}
```

**Artifact Contents**: JSON-encoded reverse-ordered domain trie.

**Deserialization**:
1. Decode base64 to bytes
2. Parse JSON
3. Rebuild trie structure in-memory
4. Use for daily lookups until next pull (24-hour refresh cycle)

**Subdomain Covering**: A node for `badsite.com` (stored as `com.badsite` in reverse order) matches lookups for:
- `badsite.com` (exact match)
- `a.badsite.com` (one-level subdomain)
- `a.b.badsite.com` (multi-level subdomain)
- Returns the **most-specific** (deepest) node's categories

## Policy Store Format

**Endpoint**: `GET /api/v1/sase/swg/policy?tenant=<id>`

**Authentication**: Standard JWT with scope `sase:read`

**Response**:
```json
{
  "policies": [
    {
      "id": "policy-uuid",
      "scope": "tenant",
      "scope_id": null,
      "category": "gambling",
      "action": "block"
    },
    {
      "id": "policy-uuid",
      "scope": "user",
      "scope_id": "user123",
      "category": "gambling",
      "action": "allow"
    }
  ]
}
```

**Caching**: The data plane caches this daily (same as radix pull).

**Resolution Algorithm**:
```python
def resolve(domain_categories, tenant, user_id, group_ids):
    # 1. Find policies matching domain's categories
    matching_policies = [p for p in tenant_policies if p.category in domain_categories]
    
    # 2. Apply scope precedence
    if matching_policy_for_user:
        return most_restrictive(user_policies)
    elif matching_policy_for_group:
        return most_restrictive(group_policies)
    elif matching_policy_for_tenant:
        return most_restrictive(tenant_policies)
    else:
        return DEFAULT_UNCATEGORIZED  # allow
```

## EnforcementAction Enum

**Shared across Slice B (SWG), Slice C (block pages), and data-plane enforcement.**

```python
class EnforcementAction(str, Enum):
    allow = "allow"              # Permit (no logging)
    log_only = "log_only"        # Permit + audit record (baseline monitoring)
    soft_block = "soft_block"    # Bypassable interstitial ("Continue at own risk?")
    block = "block"              # Deny with active response (TCP RST, HTTP 403)
    drop = "drop"                # Silent drop (no response to client)
    # isolate = "isolate"        # Reserved (not implemented) — requires network segmentation
```

**Severity Ordering** (for most-restrictive selection):
- allow < log_only < soft_block < block < drop

## Error Handling & Resilience

### Fail-Open Mandate

The data plane **must not block on infrastructure failure**. Any error during lookup or policy resolution returns `allow`:

| Error Scenario | Behavior |
|---|---|
| Radix tree miss (domain not categorized) | Return allow + enqueue for Slice E |
| Policy cache unavailable | Return allow + log miss |
| Policy resolution timeout (>100ms) | Return allow + fallback to tenant default |
| JSON parsing error in artifact | Return allow + log error |
| Malformed tenant/user/group IDs | Return allow + log warning |

**Rationale**: Blocking on infrastructure failure (cache down, network slow) degrades user experience and creates a DoS vector. Allowing through and logging is the safe default.

### Uncategorized Domains

1. **At lookup time**: Domain not in radix tree + no cached policy match
2. **Action**: Use tenant default (allow or block, configurable)
3. **Enqueue hook**: Async fire-and-forget to Slice E: `_enqueue_uncategorized(domain, tenant)`
4. **Slice E** (future):
   - AI categorization model processes domain
   - Writes result to `sase:catcache:<domain>` + database
   - Rebuilds radix for next daily pull
   - Future requests find category and apply policy

**Note**: Slice B leaves the enqueue hook as a no-op stub. Slice E implements the actual categorization.

## Radix Tree Build Process (Control Plane)

**Frequency**: Daily (freshclam-style schedule).

**Steps**:
1. Fetch category feeds from external sources (UT1/CC, blocklistproject, HaGeZi/OISD, StevenBlack, URLhaus/PhishTank, Cipher)
2. Parse domain→category pairs, store in `domain_categories` table
3. Write to Valkey `sase:catcache:*` for instant queries
4. **Custom-wins-on-conflict**: Admin-defined categories (source="custom") override feed entries
5. Build reverse-ordered trie: `domain.split('.')[::-1]` → tree structure
6. Serialize to JSON bytes
7. Serve via `GET /radix` endpoint

**Performance**: O(n log n) to build, O(k) to lookup where n=domains, k=label depth (typically <10).

## Cache Hierarchy

| Layer | Purpose | TTL | Fallback |
|---|---|---|---|
| 1. Radix tree (in-memory) | O(k) exact lookup | 24 hours (daily pull) | None (cache miss → uncategorized) |
| 2. Valkey `sase:catcache:*` | Hot query cache for frequent domains | 24 hours | Radix tree on cache error |
| 3. Policy store (in-memory) | Category→action mapping per tenant | 24 hours (daily pull) | Default allow on miss |

## Integration Points

**Slice B** (this specification):
- Defines the contract and action enum
- Builds and serves radix + policies
- Leaves uncategorized hook for Slice E

**Slice C** (block pages, Slice D):
- Receives `action: EnforcementAction` from Slice B lookup
- Renders page based on action (soft_block interstitial, block error page)
- Routes soft_block user acknowledgment back to ingress for log update

**Slice D** (analysis adapters):
- Receives events tagged with domain, category, action, outcome
- Feeds into analytics / reporting / threat intelligence

**Slice E** (AI categorization, future):
- Consumes `_enqueue_uncategorized` hook
- Categorizes via ML model
- Writes back to `sase:catcache:*` and database
- Radix rebuild picks up new category for next daily run

## Security Properties

1. **Fail-open**: Never blocks on infra failure → DoS-resistant, user-friendly
2. **Subdomain covering**: Single entry for `badsite.com` covers all subdomains (O(k) trie property)
3. **Most-specific wins**: `evil.shop.com` → malware overrides `shop.com` → shopping
4. **Scope precedence**: User policy beats group beats tenant (principle of least surprise)
5. **Custom-wins**: Admin overrides feed data (no data loss, intentional policy takes priority)
6. **Atomic policy load**: Daily pull is atomic—never partial/corrupted state mid-day
7. **No credential in cache**: Radix/policy are computed on-the-fly, no secrets cached

## Testing Checklist (Data Plane)

- [ ] Radix tree deserialization round-trips (serialize → deserialize == original)
- [ ] Subdomain-covering lookup: `lookup("a.b.badsite.com")` matches `badsite.com` entry
- [ ] Most-specific node: `lookup("evil.shop.com")` returns evil's category, not shop's
- [ ] Fail-open on miss: uncategorized domain → allow + enqueue (not block/error)
- [ ] Fail-open on cache error: `GET /radix` timeout → allow (not block)
- [ ] Policy scope precedence: user > group > tenant (user policy applied first match)
- [ ] Most-restrictive action: domain in [news, malware] → picks block if any rule says block
- [ ] Tenant default on no match: uncategorized + no policy → use tenant config (allow|block)
- [ ] Action enum serialization: JSON action strings map to enum members (allow ↔ "allow", etc.)
- [ ] Lookup latency: sub-millisecond on typical domains (trie depth <10 labels)
- [ ] Cache miss graceful degradation: policy cache down → radix lookup still works
- [ ] Radix cache miss graceful degradation: domain not in tree → uncategorized + enqueue (not crash)

## Notes

- **EnforcementAction** is the single source of truth for all enforcement semantics. Slice C (block pages) and Slice E (categorization feedback) both reference this enum.
- **No state in radix**: The radix tree is a read-only snapshot. Policy changes don't live-reload; they take effect on the next daily pull.
- **Slice B ↔ Slice E coupling**: The `_enqueue_uncategorized` hook and write-back to `sase:catcache:*` are the integration points. Slice B leaves them as a no-op stub; Slice E implements the AI-powered categorization loop.
- **Backward compatibility**: The artifact format and enum are locked. Future enhancements (e.g., new actions like `isolate`) require a new major version of the contract.

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-06 | Initial release: radix tree artifact, policy store, EnforcementAction enum, fail-open semantics, uncategorized hook. |

---

**Contract Status**: STABLE  
**Last Updated**: 2026-08-06
