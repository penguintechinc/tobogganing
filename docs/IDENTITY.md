# Identity-Aware Networking — v0.2.0

This document describes the identity architecture introduced in Tobogganing v0.2.0. The identity
layer transforms Tobogganing from a VPN-centric connectivity platform into a full identity-aware
networking system where every connection, service, and API call carries a cryptographically-verified
identity that gates authorization decisions.

---

## 1. Overview

v0.2.0 introduces a three-layer identity mesh:

1. **OIDC Management Plane** — hub-api acts as a built-in OpenID Connect provider. All users,
   services, and external IdP integrations produce a uniform Tobogganing JWT that carries tenant,
   team, and scope claims. Authorization at every API endpoint is scope-based (RFC 9068), never
   role-string-based.

2. **SPIFFE/SPIRE Workload Identity** — services running inside Kubernetes clusters receive
   X.509 SVIDs (SPIFFE Verifiable Identity Documents) from a SPIRE agent. For cloud-managed
   environments, cloud-native providers (EKS Pod Identity, GCP Workload Identity Federation, Azure
   Workload Identity) are used in preference to SPIRE. A priority-based provider chain ensures the
   strongest available attestation is always used.

3. **Cross-Cloud Connectivity via hub-router Mesh** — hub-routers form a WireGuard mesh between
   sites. Cilium Cluster Mesh API traffic rides over these WireGuard tunnels, enabling identity-aware
   east-west networking across cloud providers and on-premises data centers. Hub-api orchestrates
   peering based on tenant and team membership; each side of a peering presents its workload identity
   and hub-api validates before establishing the tunnel.

Together these three layers mean that by the time a request reaches a Tobogganing-protected service,
its identity has been attested at the hardware level (TPM or cloud hypervisor), translated to a
SPIFFE SVID or cloud workload token, exchanged for a Tobogganing JWT, and scoped to the minimum
permissions required.

---

## 2. OIDC Claim Model

All Tobogganing JWTs conform to RFC 9068 (JSON Web Token Profile for OAuth 2.0 Access Tokens) and
carry a fixed set of mandatory claims.

### 2.1 Mandatory Claims

| Claim    | Type            | Description |
|----------|-----------------|-------------|
| `sub`    | string          | Subject identifier. For users: user UUID. For workloads: SPIFFE ID. |
| `iss`    | string          | Issuer URL of the Tobogganing OIDC provider (`https://<hub-api-host>/oidc`). |
| `aud`    | string or array | Audience. Must include the resource server identifier. |
| `scope`  | string          | Space-delimited list of granted scopes (RFC 9068 §2.2.3). |
| `tenant` | string          | Tenant slug. All authorization and DB queries are scoped to this value. |
| `teams`  | array[string]   | Team slugs the subject belongs to within the tenant. |
| `roles`  | array[string]   | Informational role names. Never used for authorization decisions. |
| `iat`    | integer         | Issued-at time (Unix epoch). |
| `exp`    | integer         | Expiry time (Unix epoch). |
| `jti`    | string          | JWT ID. Unique per token for revocation tracking. |
| `type`   | string          | Token type: `access`, `refresh`, or `workload`. |

### 2.2 Scope is the Authorization Source

`roles` is present for display purposes only (e.g., the WebUI can show "Admin" in the user
profile). All middleware, all policy checks, and all gating logic reads only the `scope` claim.
This prevents role-name drift across versions and makes authorization auditable from the token alone.

### 2.3 Scope Format

Scopes use a `resource:action` format:

```
policies:read
users:admin
*:read
*:*
```

The colon separator is mandatory. The left side is the resource noun; the right side is the
action verb. Wildcard `*` matches all values in that position.

---

## 3. Scope Vocabulary

### 3.1 Per-Resource Scopes

| Resource       | Actions available               | Notes |
|----------------|---------------------------------|-------|
| `policies`     | `read`, `write`, `delete`       | Firewall / access rules |
| `hubs`         | `read`, `write`, `delete`       | Hub-router instances |
| `clusters`     | `read`, `write`, `delete`       | Kubernetes clusters registered with Tobogganing |
| `clients`      | `read`, `write`, `delete`       | WireGuard client registrations |
| `users`        | `read`, `write`, `delete`, `admin` | User accounts; `admin` includes password reset, MFA management |
| `tenants`      | `read`, `write`, `admin`        | Tenant management; global-scope only |
| `teams`        | `read`, `write`, `delete`       | Team CRUD within a tenant |
| `identity`     | `read`, `write`                 | Identity bridge mappings |
| `spiffe`       | `read`, `write`, `delete`       | SPIFFE entry management |
| `certificates` | `read`, `write`, `delete`       | X.509 certificates and CA operations |
| `settings`     | `read`, `write`                 | System-level configuration |
| `audit`        | `read`                          | Audit log access; no write action exists |

### 3.2 Role Bundles

Role bundles are pre-defined scope sets seeded at startup. They are stored in the
`role_scope_bundles` table and can be customized per tenant.

**admin**
```
*:read  *:write  *:admin  *:delete  settings:write  users:admin  tenants:admin
```

**maintainer**
```
*:read  *:write  teams:read
```

**viewer**
```
*:read
```

When a token is minted, the user's effective role bundle is resolved into explicit scope strings and
placed directly in the `scope` claim. The role name is echoed into `roles` for display.

### 3.3 Layer Narrowing

Scopes obey a narrowing hierarchy. Each layer can only restrict scopes from the layer above — it
can never expand them.

```
Global scope (platform-level defaults)
    └── Tenant scope (tenant-level cap applied at login)
            └── Team scope (team-role further restricts)
                    └── Resource scope (per-object grants, future)
```

If a user is a global `admin` but joins a tenant as a `viewer`, their token for that tenant carries
only `*:read`. If they are a `maintainer` in Team A and a `viewer` in Team B, their team-scoped
tokens reflect the appropriate subset.

---

## 4. Tenant Isolation

### 4.1 JWT Tenant Claim

Every JWT carries a `tenant` claim containing the tenant slug (e.g., `acme-corp`). This claim is
validated by hub-api middleware before any handler logic executes. A request with a mismatched or
absent `tenant` claim is rejected with HTTP 401.

### 4.2 Database Filtering

All PyDAL queries that touch tenant-owned resources include a `tenant_id` filter at the ORM layer.
The filter is applied in the base query builder, not in individual route handlers, so it cannot be
accidentally omitted. Raw SQL is prohibited for tenant-owned tables.

### 4.3 Default Tenant

On first startup (or when no tenants exist), hub-api seeds a `default` tenant. This allows
single-tenant deployments to function without explicit tenant configuration while preserving the
same code paths as multi-tenant deployments.

### 4.4 Cross-Tenant Access

Cross-tenant access is architecturally impossible through the normal token path. A token minted for
`acme-corp` cannot access `beta-inc` resources. A superadmin performing cross-tenant management
does so via a dedicated global-scope token (`iss` set to the platform issuer, `tenant` set to
`__global__`) that is only accessible via service accounts with `tenants:admin` scope.

### 4.5 Global Policies

Policy rules with `tenant_id = NULL` are global policies visible to all tenants. These are
platform-operator-managed rules (e.g., block known malicious CIDRs). Tenant users can read but
not modify global policies.

---

## 5. Team Hierarchy

### 5.1 Structure

Teams are owned by a tenant. A user may belong to multiple teams within a tenant and may hold a
different role in each team. Team membership does not grant cross-tenant access.

```
Tenant: acme-corp
    ├── Team: network-ops    (user alice: admin,  user bob: maintainer)
    ├── Team: app-team       (user alice: viewer, user carol: maintainer)
    └── Team: audit-team     (user dave: viewer)
```

### 5.2 Role-in-Team

The `user_team_memberships` table stores `(user_id, team_id, role)`. Role is one of:
`admin`, `maintainer`, `viewer`.

When a token is minted for a user acting within a specific team context, the team role cap is
applied. The resulting scopes in the JWT are the intersection of the user's tenant-level scopes and
the team's role bundle.

### 5.3 Team Scope as Subset

A team's effective scope is always a subset of the tenant scope. An admin at the tenant level who
joins a team as a viewer receives viewer-level scopes in team-context tokens.

---

## 6. SPIFFE Trust Domain Mapping

### 6.1 Trust Domain Convention

Each tenant maps to exactly one SPIFFE trust domain:

```
spiffe://<tenant-slug>.tobogganing.io/<cluster-name>/<k8s-namespace>/<service-name>
```

Examples:
```
spiffe://acme-corp.tobogganing.io/prod-eks/payments/payment-processor
spiffe://acme-corp.tobogganing.io/on-prem-dc1/infra/router-agent
spiffe://beta-inc.tobogganing.io/gke-central/frontend/web-server
```

The trust domain is the tenant isolation boundary in the workload identity layer. An SVID from
`acme-corp.tobogganing.io` is never accepted as valid for resources owned by `beta-inc`.

### 6.2 Trust Domain CA

Each tenant's trust domain is backed by a dedicated intermediate CA, signed by the Tobogganing
platform root CA. SVID validation uses the trust-domain-specific CA bundle, not the platform root,
so a compromised tenant CA cannot forge SVIDs for other tenants.

### 6.3 SVID Rotation

SVIDs are short-lived (default TTL: 1 hour). SPIRE agents rotate SVIDs proactively before
expiry. The hub-api OIDC token exchange endpoint accepts near-expiry SVIDs up to a 5-minute
grace window.

---

## 7. Workload Identity Architecture

Tobogganing supports three workload identity providers in a priority-based chain. The chain is
evaluated at token exchange time; the first available and valid provider wins.

### 7.1 Provider Priority

| Priority | Provider                        | Conditions |
|----------|---------------------------------|------------|
| 10       | Cloud-native (EKS / GCP / Azure) | Running on a supported cloud provider with native WI enabled |
| 50       | SPIRE                           | SPIRE agent reachable on unix socket; SVID valid |
| 90       | Kubernetes Service Account      | Fallback; projected SA token present |

Lower numbers win. A workload on EKS with Pod Identity enabled will always use the EKS path; SPIRE
is never contacted. A workload on a bare-metal host that has a SPIRE agent will use SPIRE. The K8s
SA fallback exists for development clusters that have neither.

### 7.2 Cloud-Native Providers

**AWS EKS Pod Identity**
- IRSA (IAM Roles for Service Accounts) and Pod Identity Association are both supported.
- The projected service account token is presented to the EKS Pod Identity agent.
- hub-api receives an AWS STS token and calls `sts:GetCallerIdentity` to verify the ARN.
- ARN is mapped to a Tobogganing SPIFFE ID via the `identity_mappings` table.

**GCP Workload Identity Federation**
- Workload Identity Pool bindings are used.
- The service account's GCP identity token is presented to hub-api.
- hub-api validates the token against Google's OIDC discovery endpoint.
- Subject is mapped to a Tobogganing SPIFFE ID.

**Azure Workload Identity**
- Azure AD federated credentials are used (no client secrets).
- The workload presents an Azure AD token.
- hub-api validates via Azure AD OIDC discovery and maps the managed identity to a SPIFFE ID.

### 7.3 SPIRE Provider

Used when cloud-native identity is unavailable:
- On-premises deployments
- Bare-metal servers
- Smaller cloud providers without native workload identity
- Environments requiring hardware-rooted attestation (TPM DevID)

The SPIRE agent is configured per cluster and registered with the tenant's SPIRE server. SVIDs are
issued per workload using Kubernetes or TPM attestation.

### 7.4 Token Exchange Flow

All providers funnel through a single token exchange endpoint on hub-api:

```
POST /api/v1/identity/exchange
Authorization: Bearer <provider-token>
X-Provider: eks | gcp | azure | spire | k8s-sa

Response:
{
  "access_token": "<tobogganing-jwt>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "policies:read hubs:read"
}
```

Downstream services receive only Tobogganing JWTs. They never need to know which provider the
workload used for attestation.

---

## 8. Node Attestation Chain

### 8.1 Hardware Root of Trust

For bare-metal and on-premises deployments, Tobogganing supports TPM-rooted attestation:

```
TPM DevID Certificate
    └── SPIRE TPM Plugin attestation
            └── SPIRE Agent granted a trust bundle
                    └── Workload SVID issued
                            └── Cilium Identity assigned
```

The TPM DevID certificate binds the node identity to the physical hardware. Cloning a VM does not
clone the TPM — the attestation fails, preventing identity theft via VM snapshot.

### 8.2 Cloud Node Attestation

For cloud environments, cloud-provider instance attestors are used instead of TPM:

| Cloud  | Attestor               | Verification method |
|--------|------------------------|---------------------|
| AWS    | `aws_iid`              | Instance Identity Document signed by AWS |
| GCP    | `gcp_iit`              | Instance Identity Token signed by Google |
| Azure  | `azure_msi`            | Managed Service Identity token from IMDS |

### 8.3 Cilium Identity Integration

After SVID issuance, the SPIFFE ID is translated to a Cilium identity label:

```
spiffe://acme-corp.tobogganing.io/prod-eks/payments/payment-processor
    → cilium identity label: spiffe=acme-corp/payments/payment-processor
```

CiliumNetworkPolicy rules can reference this label, enabling L7-aware, identity-driven network
policies without relying on IP addresses.

---

## 9. Cross-Cloud Connectivity

### 9.1 Hub-Router WireGuard Mesh

Hub-routers form a WireGuard mesh between registered sites. Each site is a hub-router instance
associated with a tenant. Hub-api orchestrates peering: when two sites belonging to the same tenant
(or to tenants with an explicit peering agreement) need connectivity, hub-api negotiates the
WireGuard peer configuration and pushes it to both hub-routers via gRPC.

### 9.2 Cilium Cluster Mesh over WireGuard

Cilium Cluster Mesh requires API-server reachability between clusters. In Tobogganing, this
API traffic rides inside the hub-router WireGuard tunnels:

```
Cluster A (AWS us-east-1)              Cluster B (GCP europe-west1)
    Cilium Cluster Mesh API ──────────────────► Cilium Cluster Mesh API
    [traffic inside WireGuard tunnel between hub-router-A and hub-router-B]
```

This means cross-cloud east-west traffic benefits from both WireGuard encryption and Cilium
identity-aware policy enforcement at each end.

### 9.3 Identity-Aware Peering

When hub-api establishes a new peering, it validates the workload identity of both hub-router
instances before exchanging WireGuard public keys. Each hub-router presents its SVID (or cloud
workload token) to hub-api. Hub-api verifies:

1. The SVID trust domain matches the tenant.
2. The SVID subject matches the registered hub-router entry in the `hubs` table.
3. The hub-router has `hubs:write` scope in its workload token.

Only after all three checks pass does hub-api authorize the peering and distribute the peer
configuration.

### 9.4 Peering Lifecycle

```
1. Operator requests peering via API: POST /api/v1/hubs/{id}/peer
2. Hub-api validates both hub identities
3. Hub-api generates WireGuard peer stubs for both sides
4. Hub-api pushes config via gRPC to hub-router-A and hub-router-B
5. WireGuard handshake completes; tunnel is live
6. Hub-api records peering in DB; sets up health-check polling
7. On peering revocation: hub-api pushes removal config; tunnel torn down
```

---

## 10. External IdP Integration

### 10.1 OIDC Federation (Generally Available)

Any OIDC-compliant IdP can be configured as an external identity source:

```yaml
# Stored in identity_providers table
provider_type: oidc
issuer: https://accounts.google.com
client_id: <client-id>
client_secret: <stored-encrypted>
claim_mappings:
  sub: sub
  email: email
  groups: groups       # maps IdP groups to Tobogganing teams
  tenant: hd           # Google Workspace hosted domain → tenant
```

Token exchange flow:
1. User authenticates to external IdP, receives IdP access token.
2. User presents IdP token to `POST /oauth2/token` (grant_type: `urn:ietf:params:oauth:grant-type:token-exchange`).
3. hub-api validates the token against the IdP's OIDC discovery endpoint.
4. hub-api applies claim mappings to resolve tenant, teams, and scopes.
5. hub-api mints a Tobogganing JWT.

### 10.2 SAML (Premium Feature — Placeholder)

SAML 2.0 SP-initiated flow is planned as a premium feature. The endpoint stubs exist at
`/saml/acs` and `/saml/metadata` but return HTTP 402 in the community edition.

### 10.3 SCIM (Premium Feature — Placeholder)

SCIM 2.0 user and group provisioning is planned as a premium feature. The endpoint stub exists at
`/scim/v2` but returns HTTP 402 in the community edition.

### 10.4 Claim Mapping Rules

Claim mappings are stored per IdP configuration in the `identity_providers` table. The mapping
engine evaluates rules in order:

1. Direct attribute mapping (IdP claim → Tobogganing claim).
2. Group-to-team mapping (IdP group name → Tobogganing team slug).
3. Scope derivation from team membership (team role → scope bundle).
4. Tenant derivation from a designated IdP claim (e.g., `hd` for Google Workspace).

If tenant derivation fails (e.g., the user's account has no matching claim), authentication is
rejected. The user must be pre-provisioned with a tenant mapping.

---

## 11. Identity Bridge

The Identity Bridge is the subsystem responsible for bidirectional mapping between identity
representations. It ensures that no matter how a subject is identified in any layer, it resolves
to a consistent Tobogganing identity.

### 11.1 Mapping Directions

```
SPIFFE ID  ◄──────────────────►  Tobogganing JWT sub
Cloud token (EKS/GCP/Azure)  ►  Tobogganing JWT sub
External OIDC sub  ────────────►  Tobogganing JWT sub
```

The bridge is unidirectional from external representations into Tobogganing's canonical subject.
Tobogganing JWTs are never reverse-mapped to provider-specific tokens.

### 11.2 DB-Backed Mappings

Explicit mappings are stored in the `identity_mappings` table:

| Column           | Description |
|------------------|-------------|
| `external_id`    | The external identity (SPIFFE ID, ARN, GCP service account email, etc.) |
| `provider_type`  | `spiffe`, `eks`, `gcp`, `azure`, `oidc` |
| `tobogganing_sub`| The canonical Tobogganing subject UUID |
| `tenant_id`      | Tenant this mapping belongs to |
| `metadata`       | JSON blob for provider-specific data |

### 11.3 Convention-Based Fallback

When no explicit DB mapping exists, the bridge applies convention-based resolution:

**SPIFFE → OIDC sub:**
```
spiffe://<tenant>.tobogganing.io/<cluster>/<namespace>/<service>
    → sub: workload:<tenant>:<cluster>:<namespace>:<service>
```

**EKS ARN → OIDC sub:**
```
arn:aws:iam::<account>:role/<role-name>
    → sub: aws:<account>:<role-name>
```

**GCP service account → OIDC sub:**
```
<sa-name>@<project>.iam.gserviceaccount.com
    → sub: gcp:<project>:<sa-name>
```

Convention-based subjects are prefixed with the provider type to prevent collisions. If convention
resolution produces a subject that does not match any user or service account in the `users` or
`spiffe_entries` tables, the exchange is rejected.

### 11.4 Bridge API

The Identity Bridge is accessible via:

```
GET  /api/v1/identity/mappings          # List mappings for tenant
POST /api/v1/identity/mappings          # Create explicit mapping
GET  /api/v1/identity/mappings/{id}     # Get specific mapping
PUT  /api/v1/identity/mappings/{id}     # Update mapping
DELETE /api/v1/identity/mappings/{id}  # Remove mapping

POST /api/v1/identity/resolve           # Resolve any external ID to Tobogganing sub (debug)
```

All endpoints require `identity:read` or `identity:write` scope as appropriate.

---

## 12. OIDC Provider Endpoints

Hub-api exposes a built-in OIDC provider. All endpoints are under the well-known discovery path.

| Endpoint                              | Description |
|---------------------------------------|-------------|
| `GET /.well-known/openid-configuration` | OIDC Discovery document |
| `GET /oauth2/jwks`                    | JSON Web Key Set (public keys for JWT verification) |
| `POST /oauth2/token`                  | Token endpoint (password, client_credentials, token-exchange) |
| `GET /oauth2/authorize`               | Authorization endpoint (code flow) |
| `GET /oauth2/userinfo`                | UserInfo endpoint (RFC 7662) |
| `POST /oauth2/revoke`                 | Token revocation endpoint |
| `POST /oauth2/introspect`             | Token introspection endpoint (RFC 7662) |

### 12.1 Key Rotation

Hub-api maintains two active signing keys at all times (current + previous). Keys are rotated on a
configurable schedule (default: 24 hours). Both keys are present in the JWKS endpoint during the
overlap window, ensuring in-flight tokens remain verifiable during rotation.

### 12.2 Token Lifetimes

| Token type   | Default TTL | Configurable |
|--------------|-------------|--------------|
| Access token | 1 hour      | Yes, per tenant |
| Refresh token| 7 days      | Yes, per tenant |
| Workload token | 1 hour    | Yes, per tenant |

Workload tokens are not issued refresh tokens. They re-exchange their provider credential for a new
access token when the current one nears expiry.

---

## 13. Deployment Notes

### 13.1 SPIRE Helm Chart

A Tobogganing-managed SPIRE Helm chart is provided at `k8s/helm/spire/`. It supports:

- **Cloud attestors**: `aws_iid`, `gcp_iit`, `azure_msi` (enabled via values overrides)
- **Bare-metal attestor**: TPM DevID plugin
- **K8s attestor**: Default for development environments
- **HA mode**: SPIRE server with etcd backend for production

Key values:

```yaml
spire:
  trustDomain: acme-corp.tobogganing.io    # must match tenant slug
  attestors:
    awsIID: true          # enable for EKS
    gcpIIT: false
    azureMSI: false
    tpm: false            # enable for bare-metal
  server:
    ha: true
    replicas: 3
```

### 13.2 Hub-api Configuration

Identity features are controlled via environment variables:

```bash
# OIDC provider
OIDC_ISSUER_URL=https://hub-api.example.com/oidc
OIDC_SIGNING_KEY_PATH=/secrets/oidc-signing-key.pem
OIDC_TOKEN_TTL=3600

# Workload identity
WI_PROVIDERS=eks,spire          # ordered by priority
WI_SPIRE_SOCKET=/run/spire/sockets/agent.sock
WI_EKS_REGION=us-east-1

# Tenant defaults
DEFAULT_TENANT_SLUG=default
MULTI_TENANT=false              # set true for multi-tenant deployments
```

### 13.3 Hub-router Identity Middleware

Hub-router reads `TOBOGGANING_HUB_API_URL` and `TOBOGGANING_WORKLOAD_TOKEN_PATH` at startup to
obtain and refresh its own workload token. All outbound API calls to hub-api include the token in
the `Authorization: Bearer` header. Incoming requests from peers are validated against the
hub-api JWKS endpoint (cached, refreshed on 401).

---

## 14. Security Considerations

- **Scope creep prevention**: Token minting code must assert that the final scope string is a
  subset of the user's maximum allowed scope. Any scope present in the minted token that is not
  in the user's maximum scope bundle is a security bug.
- **JWT revocation**: The `jti` claim is stored in Redis with TTL equal to `exp - now`. A revocation
  check against Redis is mandatory for sensitive operations (user:admin, tenants:admin). Standard
  API calls perform revocation checks probabilistically (10% of requests) to reduce latency.
- **Trust domain isolation**: Never configure two tenants to share a trust domain. The trust domain
  is the only cryptographic boundary between tenant SVIDs.
- **Token exchange rate limiting**: The `/api/v1/identity/exchange` endpoint is rate-limited per
  source IP and per SPIFFE ID to prevent SVID-based DoS.
- **Audit logging**: All token minting, scope elevation, and identity bridge mapping changes are
  written to the audit log with full claim details.

---

*Identity Architecture v0.2.0 | Tobogganing | Penguin Tech Inc*
