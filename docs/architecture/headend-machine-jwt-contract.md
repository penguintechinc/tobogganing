# Headend Machine-JWT Contract (Go ↔ Quart brain)

**Status**: Quart side implemented (auth redesign T1–T5, findings C+D). **Go headend change pending — separate session.**
**Cross-references**: `docs/superpowers/specs/2026-07-29-auth-redesign-cd-design.md`; hub-topology spec §8 #11/#12, §10.

## Purpose

The Quart brain now authenticates the Go headend (and clusters/clients) with **per-cluster machine-JWTs** carrying tenant + scope claims, replacing the global static `HEADEND_API_TOKEN` and the shared `ENROLLMENT_BOOTSTRAP_TOKEN` on the machine-plane routes. This document is the hand-off contract the Go headend must implement. Until it does, the transition flag stays **OFF** and the legacy static tokens keep working (dual-accept).

## What the Go headend must do

1. **Exchange its `CLUSTER_API_KEY` for a machine-JWT** at startup:
   `POST /api/v1/auth/token` with `{"node_id": "<cluster-id>", "node_type": "kubernetes_node", "api_key": "<CLUSTER_API_KEY>"}`.
   Response: `{"access_token": <1h JWT>, "refresh_token": <8h rotating JWT>, ...}`.
2. **Send `Authorization: Bearer <access_token>`** on every machine-plane route — this *replaces the current split* where the Go side used `authToken` (=`HEADEND_API_TOKEN`) for `firewall/rules`+`ports` and `CLUSTER_API_KEY` for `wireguard/peers` (spec §8 #11). One cluster identity now covers all of them:
   - `GET /api/v1/firewall/rules` (scope `firewall:read`)
   - `GET /api/v1/wireguard/peers` (scope `wireguard:read`)
   - `GET /api/v1/headend/<id>/ports` (scope `ports:read`)
   - `POST /api/v1/clients/headends/<id>/metrics` (scope `metrics:write` — **was the shared bootstrap token; now the cluster machine-JWT**, closing security-review Finding 2)
3. **Store the rotated refresh token and refresh before the access token expires** (`POST /api/v1/auth/refresh` with `{"refresh_token": <current>}`). Refresh is **single-use**: each call returns a NEW refresh token; the old one is immediately invalid. Persist the newest one; a replay of a superseded refresh token is treated as compromise and **revokes the cluster** (all its tokens).
4. **On `503 {"retry_with_credentials": true}`** from `/auth/refresh** (the brain's Valkey revocation store is unreachable — fail-closed), fall back to step 1: re-authenticate with `CLUSTER_API_KEY`. No hard outage.
5. **Cert issuance** (`POST /api/v1/certs/certificates`, scope `certs:issue`) remains the **enrollment** path: a bootstrapping node presents the `ENROLLMENT_BOOTSTRAP_TOKEN` (legacy) or a cluster with `certs:issue` in its machine-JWT scope issues client certs. The `HEADEND_API_TOKEN` can NOT issue certs.

## Scope model (what each identity is allowed)

Machine-JWT scopes are derived from `node_type` (least-privilege):

| node_type | scopes |
|-----------|--------|
| `kubernetes_node` / `raw_compute` / `headend` (clusters) | `firewall:read wireguard:read ports:read metrics:write certs:issue` |
| `client_docker` / `client_native` (clients) | `wireguard:read` |

During the dual-accept window (flag OFF), the two legacy static tokens map to fixed allowlists (a legacy token can only satisfy its own scopes):

| legacy token | allowed scopes |
|--------------|----------------|
| `HEADEND_API_TOKEN` | `firewall:read`, `wireguard:read`, `ports:read`, `metrics:write` |
| `ENROLLMENT_BOOTSTRAP_TOKEN` | `certs:issue` |

## Cutover

- Flag `tobogganing.core.machine_jwt_required` — **default OFF** = dual-accept (legacy static tokens + machine-JWTs both work). No lockstep deploy.
- Once the Go headend ships steps 1–4 and is deployed, flip the flag **ON** — legacy static tokens are then rejected (401), machine-JWT only. Verified by `test_flag_on_rejects_static_token`.
- Rollback: flip the flag OFF to restore legacy acceptance.

## Notes

- Tenant: the machine-JWT carries the cluster's real `tenant`; the brain scopes every machine-plane query to it (no more hardcoded `"default"`).
- Credential rotation: the brain exposes `ClusterManager.rotate_api_key` — rotating a cluster's `CLUSTER_API_KEY` invalidates the old key; the headend must re-run step 1 with the new key.
- Longer-term: this machine-JWT is the OIDC-machine-JWT **fallback** in the SPIFFE model — every service is built SPIFFE-ready (accepts an X.509-SVID as a first-class identity), so adopting SPIRE later is a config change, not a rewrite (see `security.md` Service-to-Service Auth, hub-topology §8 #4). The `require_machine_jwt` decorator isolates identity extraction in one place for exactly this.
