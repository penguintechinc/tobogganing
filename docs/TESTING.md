# Testing Guide — Tobogganing

This document describes the testing strategy, categories, and execution order for Tobogganing.
All tests are invocable via the unified test controller.

---

## Test Controller

```bash
./scripts/test-controller.sh <type> [container]
```

Types: `build`, `unit`, `integration`, `functional`, `e2e`, `security`, `api`, `performance`, `smoke`

Container is optional; omit to run a test type across all containers.

---

## Test Categories

### Build Tests

Verify that each service compiles without errors.

```bash
make test-build
# or
./scripts/test-controller.sh build hub-api
./scripts/test-controller.sh build hub-router
./scripts/test-controller.sh build hub-webui
```

### Unit Tests

Per-service unit tests with no external dependencies.

```bash
make test-unit
./scripts/test-controller.sh unit hub-api      # pytest services/hub-api/
./scripts/test-controller.sh unit hub-router   # go test ./... services/hub-router/
./scripts/test-controller.sh unit hub-webui    # jest services/hub-webui/
```

#### Overlay and XDP Unit Tests (v0.3.0+)

```bash
# Hub-router overlay provider tests
go test ./internal/overlay/ -v           # services/hub-router/

# Policy engine OverlayScope tests
go test ./internal/policy/ -v -run TestOverlay  # services/hub-router/

# XDP stub tests (default build, no BPF)
go test ./internal/xdp/ -v              # services/hub-router/

# Client overlay tests (WG, OpenZiti, dual-mode)
go test ./internal/overlay/ -v           # clients/native/
```

### Integration Tests

Tests requiring a running database, Redis, or gRPC server. Spun up via Docker Compose test profile.

```bash
make test-integration
./scripts/test-controller.sh integration hub-api
./scripts/test-controller.sh integration hub-router
```

### Functional Tests

Tests that exercise APIs, pages, tabs, modals, and buttons end-to-end against a running dev stack.

```bash
make test-functional
./scripts/test-controller.sh functional hub-api    # API contract tests
./scripts/test-controller.sh functional hub-webui  # Page/component tests
```

### E2E Tests

Full-stack Playwright tests against the running application.

```bash
make test-e2e
./scripts/test-controller.sh e2e hub-webui
```

### Security Tests

Static analysis and vulnerability scanning.

```bash
make test-security
./scripts/test-controller.sh security hub-api      # bandit + safety
./scripts/test-controller.sh security hub-router   # gosec
./scripts/test-controller.sh security hub-webui    # npm audit
# trivy image scan runs in CI on all containers
```

### Performance Tests

Benchmark and load tests. Not included in the default `make test` target.

```bash
./scripts/test-controller.sh performance hub-router  # go benchmark
./scripts/test-controller.sh performance hub-api     # locust load test
```

### Smoke Tests

Curated subset of critical tests that run in under 2 minutes. Mandatory before every commit.

```bash
make smoke-test
./scripts/test-controller.sh smoke
```

Smoke tests include:
- Service build verification (all three containers)
- Hub-api `/health` endpoint returns 200
- Hub-router `/healthz` endpoint returns 200
- Login flow returns a valid JWT
- Policy rules list endpoint returns envelope `{"status":"success"}`
- Hub-webui loads the root page without JS errors

#### Overlay and XDP Smoke Tests (v0.3.0+)

```bash
# Hub-router builds without XDP tag
./tests/smoke/test_hub_router_build.sh

# Client builds with overlay support
./tests/smoke/test_client_build.sh

# Hub-router overlay config (wireguard/openziti startup)
./tests/smoke/test_overlay_config.sh

# XDP stub is safe no-op in default build
./tests/smoke/test_xdp_stub.sh
```

#### Overlay and XDP E2E Tests (v0.3.0+)

```bash
# WireGuard full path with OverlayScope
./tests/e2e/test_wireguard_overlay_e2e.sh

# OpenZiti dark service path (requires Ziti controller)
./tests/e2e/test_openziti_overlay_e2e.sh

# Dual-mode client: WG + Ziti simultaneously
./tests/e2e/test_dual_mode_e2e.sh

# Policy scope filtering (openziti vs wireguard rules)
./tests/e2e/test_overlay_scope_policy.sh

# XDP rate limiting (requires -tags xdp and root/CAP_BPF)
./tests/e2e/test_xdp_rate_limiting.sh
```

---

## v0.2.0 Identity and Authorization Tests

### Identity and Authorization Tests (hub-api)

These tests cover the OIDC provider, scope enforcement, and tenant isolation introduced in v0.2.0.

#### Scope Matching Tests

Located in `tests/unit/hub-api/test_scopes.py`.

| Test | Description |
|------|-------------|
| `test_exact_scope_match` | `policies:read` grants access to `policies:read` endpoint |
| `test_exact_scope_deny` | `policies:read` denies access to `policies:write` endpoint |
| `test_wildcard_resource` | `*:read` grants access to all `*:read` endpoints |
| `test_wildcard_action` | `policies:*` grants access to all `policies:*` endpoints |
| `test_superadmin_wildcard` | `*:*` grants access to all scoped endpoints |
| `test_missing_scope_returns_403` | Request with no scope claim returns HTTP 403 |
| `test_empty_scope_returns_403` | Request with `scope: ""` returns HTTP 403 |
| `test_scope_narrowing` | Team-context token cannot exceed tenant-level scopes |

#### Tenant Isolation Tests

Located in `tests/integration/hub-api/test_tenant_isolation.py`.

| Test | Description |
|------|-------------|
| `test_cross_tenant_resource_denied` | Token for tenant A cannot read resources of tenant B |
| `test_cross_tenant_policy_denied` | Token for tenant A cannot modify policies of tenant B |
| `test_global_policy_visible_all_tenants` | Policies with `tenant_id=NULL` visible to all tenant tokens |
| `test_global_policy_not_modifiable_by_tenant` | Tenant token cannot modify global policies |
| `test_default_tenant_seeded` | Fresh install always has `default` tenant |
| `test_tenant_claim_missing_returns_401` | JWT without `tenant` claim is rejected |
| `test_tenant_claim_mismatch_returns_401` | JWT `tenant` claim not matching request path is rejected |

#### OIDC Provider Tests

Located in `tests/functional/hub-api/test_oidc_provider.py`.

| Test | Description |
|------|-------------|
| `test_discovery_endpoint` | `GET /.well-known/openid-configuration` returns valid OIDC metadata |
| `test_jwks_endpoint` | `GET /oauth2/jwks` returns JWKS with at least one active key |
| `test_jwks_key_ids_match_jwt_header` | Tokens issued by hub-api reference a `kid` present in JWKS |
| `test_token_endpoint_password_grant` | `POST /oauth2/token` password grant returns valid JWT |
| `test_token_endpoint_client_credentials` | Client credentials grant returns workload token |
| `test_token_endpoint_invalid_credentials` | Invalid credentials return HTTP 401 |
| `test_token_scopes_match_role_bundle` | Minted token scopes match the user's role bundle |
| `test_userinfo_endpoint` | `GET /oauth2/userinfo` returns claims matching token |
| `test_token_revocation` | Revoked token is rejected on next use |
| `test_expired_token_rejected` | Token past `exp` returns HTTP 401 |

#### Token Exchange Tests

Located in `tests/integration/hub-api/test_token_exchange.py`.

| Test | Description |
|------|-------------|
| `test_spire_svid_exchange` | Valid SPIFFE SVID produces a Tobogganing workload JWT |
| `test_invalid_svid_rejected` | SVID with invalid signature is rejected |
| `test_wrong_trust_domain_rejected` | SVID from wrong trust domain returns HTTP 403 |
| `test_eks_token_exchange` | Mocked EKS token exchange returns valid JWT |
| `test_gcp_token_exchange` | Mocked GCP workload token exchange returns valid JWT |
| `test_azure_token_exchange` | Mocked Azure workload token exchange returns valid JWT |
| `test_external_oidc_exchange` | External OIDC token mapped via claim rules returns JWT |
| `test_claim_mapping_applied` | External IdP groups are mapped to Tobogganing teams |
| `test_exchange_missing_tenant_mapping_rejected` | Exchange with no resolvable tenant returns HTTP 400 |

#### Workload Identity Provider Tests

Located in `tests/unit/hub-api/test_workload_identity.py`.

| Test | Description |
|------|-------------|
| `test_provider_priority_cloud_native_wins` | When EKS provider available, SPIRE is not called |
| `test_provider_priority_spire_over_k8s` | When SPIRE available and no cloud provider, K8s SA not used |
| `test_k8s_sa_fallback` | When no cloud or SPIRE available, K8s SA token accepted |
| `test_provider_chain_all_fail_returns_error` | All providers unavailable returns descriptive error |
| `test_cloud_native_detection_eks` | EKS IMDS reachable → provider type set to `eks` |
| `test_cloud_native_detection_gcp` | GCP metadata server reachable → provider type set to `gcp` |
| `test_cloud_native_detection_azure` | Azure IMDS reachable → provider type set to `azure` |
| `test_convention_based_subject_resolution` | SPIFFE ID without explicit mapping resolves via convention |

---

### Hub-Router Identity Tests

#### Policy Engine Identity Dimensions

Located in `tests/unit/hub-router/policy_engine_identity_test.go`.

| Test | Description |
|------|-------------|
| `TestIdentityDimension_TenantMatch` | Rule with `tenant=acme-corp` matches token with matching tenant |
| `TestIdentityDimension_TenantMismatch` | Rule with `tenant=acme-corp` denies token for `beta-inc` |
| `TestIdentityDimension_ScopeRequired` | Rule requiring `policies:read` denies token without that scope |
| `TestIdentityDimension_WildcardScope` | Rule requiring `policies:read` allows token with `*:read` |
| `TestIdentityDimension_SPIFFEIDMatch` | Rule with SPIFFE ID pattern matches workload token |
| `TestIdentityDimension_SPIFFEIDWildcard` | SPIFFE ID pattern with `*` matches multiple workloads |
| `TestIdentityDimension_NoIdentity` | Request with no identity context uses default-deny |

#### Identity Validator Tests

Located in `tests/unit/hub-router/identity_validator_test.go`.

| Test | Description |
|------|-------------|
| `TestValidateCloudNativeToken_EKS` | EKS-issued token passes validator |
| `TestValidateCloudNativeToken_GCP` | GCP-issued token passes validator |
| `TestValidateCloudNativeToken_Azure` | Azure-issued token passes validator |
| `TestValidateSPIFFEToken_Valid` | Valid SVID passes validator |
| `TestValidateSPIFFEToken_Expired` | Expired SVID fails validator |
| `TestValidateSPIFFEToken_WrongTrustDomain` | Wrong trust domain fails validator |
| `TestValidateK8sSA_Valid` | Valid K8s SA token passes validator |
| `TestValidateK8sSA_Invalid` | Tampered K8s SA token fails validator |

#### Scope Middleware Tests

Located in `tests/unit/hub-router/middleware_test.go`.

| Test | Description |
|------|-------------|
| `TestTenantRequired_MissingClaim_Returns401` | Request missing `tenant` claim returns 401 |
| `TestTenantRequired_ValidClaim_PassesThrough` | Request with valid tenant claim proceeds |
| `TestScopeRequired_ExactMatch_Passes` | Exact scope match allows request |
| `TestScopeRequired_WildcardMatch_Passes` | Wildcard scope `*:read` matches required `policies:read` |
| `TestScopeRequired_MissingScope_Returns403` | Required scope absent returns 403 |
| `TestScopeRequired_EmptyToken_Returns401` | No token at all returns 401 |

---

### WebUI Identity Tests

#### ScopeGate Component

Located in `services/hub-webui/src/__tests__/ScopeGate.test.tsx`.

| Test | Description |
|------|-------------|
| `renders_children_when_scope_present` | Children render when token has the required scope |
| `renders_fallback_when_scope_absent` | Fallback element renders when scope is missing |
| `renders_nothing_when_no_fallback_and_scope_absent` | No fallback prop → nothing rendered |
| `wildcard_resource_scope_grants_access` | `*:read` satisfies `policies:read` requirement |
| `wildcard_action_scope_grants_access` | `policies:*` satisfies `policies:read` requirement |
| `superadmin_scope_grants_access` | `*:*` satisfies any scope requirement |
| `empty_scope_string_denies_access` | Empty scope string renders fallback |
| `scope_check_is_case_sensitive` | `Policies:Read` does not satisfy `policies:read` |

#### hasScope Utility

Located in `services/hub-webui/src/__tests__/hasScope.test.ts`.

| Test | Description |
|------|-------------|
| `exact_match_returns_true` | `hasScope("policies:read", ["policies:read"])` is `true` |
| `exact_match_returns_false` | `hasScope("policies:write", ["policies:read"])` is `false` |
| `wildcard_resource_match` | `hasScope("policies:read", ["*:read"])` is `true` |
| `wildcard_action_match` | `hasScope("policies:read", ["policies:*"])` is `true` |
| `superadmin_match` | `hasScope("anything:anything", ["*:*"])` is `true` |
| `no_scopes_returns_false` | `hasScope("policies:read", [])` is `false` |
| `null_scopes_returns_false` | `hasScope("policies:read", null)` is `false` |
| `partial_wildcard_no_false_positive` | `hasScope("polic:read", ["policies:*"])` is `false` |

#### Tenant Management Page

Located in `services/hub-webui/src/__tests__/pages/TenantManagement.test.tsx`.

| Test | Description |
|------|-------------|
| `renders_tenant_list` | Page loads and displays tenant rows from API |
| `create_tenant_form_submits` | Create form POSTs to `/api/v1/tenants` with correct payload |
| `edit_tenant_form_submits` | Edit form PUTs to `/api/v1/tenants/{id}` |
| `delete_tenant_prompts_confirmation` | Delete shows confirmation modal before DELETE request |
| `hidden_for_non_admin_scope` | Page shows access-denied state when `tenants:admin` scope absent |

#### Team Management Page

Located in `services/hub-webui/src/__tests__/pages/TeamManagement.test.tsx`.

| Test | Description |
|------|-------------|
| `renders_team_list_for_tenant` | Teams displayed filtered to current tenant |
| `create_team_form_submits` | Create form POSTs to `/api/v1/teams` |
| `add_member_to_team` | Add member dialog POSTs to `/api/v1/teams/{id}/members` |
| `remove_member_from_team` | Remove member DELETEs from `/api/v1/teams/{id}/members/{uid}` |
| `role_dropdown_shows_valid_options` | Role selector shows admin, maintainer, viewer only |
| `hidden_for_viewer_scope` | Team management actions gated on `teams:write` scope |

#### Workload Identity Page

Located in `services/hub-webui/src/__tests__/pages/WorkloadIdentity.test.tsx`.

| Test | Description |
|------|-------------|
| `renders_identity_mappings` | Page lists mappings from `/api/v1/identity/mappings` |
| `create_mapping_form_submits` | Create mapping POSTs with provider type and external ID |
| `delete_mapping_prompts_confirmation` | Delete shows confirmation before removing mapping |
| `spiffe_entries_tab_renders` | SPIFFE entries sub-tab shows entries for tenant |
| `resolve_identity_debug_panel` | Debug panel calls `/api/v1/identity/resolve` and shows result |
| `hidden_for_missing_identity_scope` | Page shows access-denied when `identity:read` scope absent |

---

## Test Execution Order (Pre-Commit)

Run in this order before every commit:

```bash
make smoke-test              # 1. Fast sanity check (<2 min)
make test-security           # 2. Static analysis (bandit, gosec, npm audit)
make test-unit               # 3. Unit tests (no external deps)
make test-integration        # 4. Integration tests (requires Docker)
make test-functional         # 5. Functional API + page tests
```

E2E and performance tests are optional for standard feature commits. They are always run in CI.

---

## Mock Data

Seed 3-4 representative items per feature for manual testing:

```bash
make seed-mock-data
```

This script creates:
- 2 tenants (`default`, `acme-corp`)
- 3 teams in `acme-corp` (`network-ops`, `app-team`, `audit-team`)
- 4 users with varying role assignments
- 4 policy rules with different scopes
- 2 SPIFFE identity mappings
- 1 OIDC external IdP configuration

---

*Testing Guide | Tobogganing v0.2.0 | Penguin Tech Inc*
