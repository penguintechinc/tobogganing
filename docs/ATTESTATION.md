# System Attestation Guide

**Version**: v0.3.0
**Last Updated**: 2026-02-28

## Overview

System attestation is a cryptographic mechanism that verifies the identity and integrity of infrastructure clients (servers, VMs, bare metal) connecting to the Tobogganing cluster. Instead of relying solely on credentials, attestation collects hardware and cloud identity signals to establish a confidence level that a client is genuinely the system it claims to be.

**Why It Matters:**
- Prevents VM/instance theft and lateral movement attacks
- Enables policy binding to specific hardware or cloud instances
- Detects unauthorized hardware modifications or OS tampering
- Provides forensic trail of client identity over time
- Integrates with fleet management tools (FleetDM) for cross-reference validation

Attestation is enabled by default on infrastructure clients. All JWT access tokens include attestation confidence scores and methods, allowing policy engines to make identity-aware decisions.

---

## Confidence Model

Attestation combines multiple signals into a weighted scoring system. Each signal contributes a fixed weight if present, summing to a maximum possible score of **115 points**.

### Signal Weights

| Signal | Weight | Source | Proves |
|--------|--------|--------|--------|
| TPM 2.0 PCR quote (challenge-response) | 40 | `/dev/tpmrm0` or `/dev/tpm0` | Hardware root of trust |
| Cloud Instance Identity Document | 35 | AWS/GCP/Azure IMDS | Cloud-native identity |
| DMI `product_uuid` | 10 | SMBIOS DMI | System uniqueness |
| DMI `board_serial` | 8 | SMBIOS DMI | Motherboard identity |
| FleetDM cross-reference | 7 | FleetDM API (optional) | Fleet enrollment validation |
| Network MAC addresses | 5 | Network interfaces | Physical hardware presence |
| Disk serials | 4 | Block devices | Storage hardware identity |
| DMI `sys_vendor` + `product_name` | 3 | SMBIOS DMI | Hardware model consistency |
| CPU model + count | 3 | `/proc/cpuinfo` | Processor hardware match |

**Total Max Score**: 115 points

### Confidence Levels

Confidence percentage is calculated as: `min(score / 115 * 100, 100)`

| Confidence Range | Level | Token Claims | Policy Use |
|------------------|-------|--------------|-----------|
| >= 90% | HIGH | Allows all policy bindings | Trusted for sensitive ops |
| >= 60% | MEDIUM | Allows most bindings | Standard enforcement |
| >= 30% | LOW | Limited bindings | Restricted access |
| < 30% | MINIMAL | Fingerprint-only | Monitoring/alerting only |

**JWT Claim**: `attest_conf` (integer 0-100) and `attest_method` (string: `tpm`, `cloud_iid`, `fingerprint`, `minimal`)

---

## Signals

### TPM 2.0 PCR Quote (Weight: 40)

**Availability**: Linux systems with TPM 2.0 chip (`/dev/tpmrm0` or `/dev/tpm0`)

**How It Works:**
1. Hub-api sends 32-byte challenge (nonce) via `POST /api/v1/attestation/challenge`
2. Client signs nonce with TPM2_Sign using PCR quote (banks 0, 1, 2, 7)
3. Client includes signature, PCR values, and nonce in attestation payload
4. Hub-api verifies signature and PCR consistency

**What It Proves:** Hardware-level root of trust; PCR values attest kernel/bootloader integrity

**Build Requirement**: Compile with `-tags tpm` to enable TPM support

---

### Cloud Instance Identity Document (Weight: 35)

**Availability**: AWS EC2, GCP Compute, Azure VMs via Instance Metadata Service (IMDS)

**Detection Process:**
1. Client attempts HTTP requests to `http://169.254.169.254/...` with 500ms timeout
2. Tries in sequence: AWS → GCP → Azure
3. AWS success: `GET /latest/dynamic/instance-identity/document` → signed JSON
4. GCP success: `GET /computeMetadata/v1/instance/service-accounts/default/identity?audience=...`
5. Azure success: `GET /metadata/identity/oauth2/token` → JWT with hardware profile

**What It Proves:** System is running on verified cloud infrastructure; identity document contains instance ID, region, account, signature

---

### DMI Identifiers (Weights: 10, 8, 3)

**Source**: SMBIOS DMI tables (`dmidecode`, `/sys/class/dmi/id/`)

**Fields**:
- `product_uuid`: System UUID (10 pts) — highly unique, rarely changes
- `board_serial`: Motherboard serial (8 pts) — stable, hardware-specific
- `sys_vendor` + `product_name`: Manufacturer and model (3 pts) — consistency check

**What It Proves:** Physical hardware model and identity; used as fallback when TPM/cloud unavailable

---

### Network MAC Addresses (Weight: 5)

**Source**: Interface hardware addresses from `ip link`, `/sys/class/net/*/address`

**Stored As**: Canonical sorted list (IPv4 MAC format)

**What It Proves:** Physical network hardware presence; useful for detecting VM clones

---

### Disk Serial Numbers (Weight: 4)

**Source**: Block device serials from `lsblk -d -o SERIAL`, `udevadm info`

**Stored As**: Canonical sorted list of primary storage device serials

**What It Proves:** Storage hardware identity; detects when OS is cloned to different hardware

---

### CPU Model and Count (Weight: 3)

**Source**: `/proc/cpuinfo` (model name, count)

**What It Proves**: CPU hardware consistency; useful for detecting environment changes (VirtualBox → KVM)

---

### FleetDM Integration (Weight: 7)

**Availability**: Optional, requires `FLEETDM_URL` and `FLEETDM_API_KEY` on hub-api

**Cross-Reference Logic:**
1. Client sends `fleetdm_host_uuid` in attestation config (optional)
2. Hub-api queries FleetDM for host record by UUID or hostname
3. Compares fields:
   - `hardware_serial` ↔ `board_serial` (exact match)
   - `hardware_model` ↔ `product_name` (substring match)
   - `primary_mac` ↔ `mac_addresses[0]` (case-insensitive)
4. Requires >= 2/3 field matches to award points

**What It Proves**: System is enrolled in official fleet; provides audit trail

---

## Composite Hash

A SHA-256 digest of the attestation fingerprint identifies a system across multiple tokens.

**Stable Fields** (included in hash):
- `product_uuid`
- `board_serial`
- `sys_vendor`
- `product_name`
- `cpu_model`
- `mac_addresses` (sorted)
- `disk_serials` (sorted)

**Volatile Fields** (stored but excluded from hash):
- `kernel_version`
- `os_release_name`
- `tpm_pcr_*`
- `cloud_iid_*`

**Calculation**: `SHA256(canonical_json_of_sorted_stable_fields)`

**Purpose**: Detect hardware changes over time; used in drift detection on token refresh

---

## TPM Attestation

### Prerequisites

- Linux kernel with TPM support
- `/dev/tpmrm0` (preferred) or `/dev/tpm0` available
- Compile hub-router client with `-tags tpm`
- TPM 2.0 (TPM 1.2 not supported)

### Flow

1. **Challenge Request**
   ```
   POST /api/v1/attestation/challenge
   Response: {
     "nonce": "a1b2c3d4...",  // 32-byte hex
     "ttl_seconds": 300,
     "banks": [0, 1, 2, 7]
   }
   ```

2. **Client Signs Nonce**
   - Read PCR values from banks 0, 1, 2, 7
   - Use TPM2_Sign with nonce as input
   - Include signature and PCR state in attestation payload

3. **Hub-API Verification**
   - Verify TPM signature (public key from TPM_CERT_NAME)
   - Validate PCR banks match expected bootloader/kernel state
   - Confirm nonce matches and within TTL
   - Award 40 points if successful

---

## Cloud Identity Detection

### Auto-Detection

Client automatically detects cloud provider on startup:

1. **Timeout**: 500ms per provider attempt (fail-fast)
2. **Sequence**: AWS → GCP → Azure (first success wins)
3. **No Error**: If all fail, continue with local attestation (TPM + DMI)

### AWS EC2

```
GET http://169.254.169.254/latest/dynamic/instance-identity/document
Authorization: (none)
```

**Response**: JSON document including `instanceId`, `region`, `accountId`, signed by AWS

**Stored As**: `cloud_iid_provider=aws`, `cloud_iid_instance_id`, `cloud_iid_region`

### GCP Compute Engine

```
GET http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/identity?audience=tobogganing-hub
Metadata-Flavor: Google
```

**Response**: JWT signed by GCP, includes `google/compute_engine` claims

**Stored As**: `cloud_iid_provider=gcp`, `cloud_iid_project_id`, `cloud_iid_zone`

### Azure VM

```
GET http://169.254.169.254/metadata/identity/oauth2/token?resource=https://management.azure.com
Metadata: true
```

**Response**: JWT with resource identifier and subscription info

**Stored As**: `cloud_iid_provider=azure`, `cloud_iid_subscription_id`

---

## FleetDM Integration (Optional)

### Configuration

On **hub-api**, set environment variables:
```bash
FLEETDM_URL=https://fleet.example.com
FLEETDM_API_KEY=<api-key>
```

### Lookup Process

1. Client includes `fleetdm_host_uuid` in attestation config
2. Hub-api queries FleetDM API: `GET /api/v1/fleet/hosts/{uuid}`
3. Compares:
   - `host.hardware.serial` vs `board_serial` (exact)
   - `host.hardware.model` vs `product_name` (substring match)
   - `host.primary_ip_mac` vs `mac_addresses[0]` (case-insensitive)
4. If >= 2/3 fields match, award 7 points

### Error Handling

- FleetDM timeout (5s): continue without FleetDM points
- Host not found: continue without FleetDM points
- Network error: continue without FleetDM points

No failure blocks attestation; FleetDM is advisory only.

---

## Drift Detection

When a client refreshes its access token, hub-api re-evaluates attestation and detects changes.

### Comparison Process

1. Client sends current attestation snapshot
2. Hub-api loads stored fingerprint from prior registration
3. Calculates per-field drift scores:

| Field | Drift Weight |
|-------|--------------|
| `product_uuid` | 1.0 |
| `board_serial` | 0.25 |
| `sys_vendor` | 0.1 |
| `product_name` | 0.1 |
| `cpu_model` | 0.05 |
| `mac_addresses` | 0.15 |
| `disk_serials` | 0.1 |

**Total Weight**: 1.85

4. **Drift Score**: `sum(field_weights * field_changed) / 1.85`

### Decision Matrix

| Drift Score | Action | Result |
|-------------|--------|--------|
| `product_uuid` changed | Immediate rejection | 403 Forbidden |
| > 0.6 | Reject token refresh | 403 Forbidden, event logged |
| > 0.3 | Allow with alert | Token issued, security event created |
| <= 0.3 | Allow, update fingerprint | Token issued, fingerprint updated |

---

## Configuration

### Client Config File

```yaml
attestation:
  enabled: true              # Default: true, disable to skip attestation
  tpm_enabled: true          # Default: true, requires -tags tpm build
  tpm_device: /dev/tpmrm0   # Default: /dev/tpmrm0, fallback /dev/tpm0
  cloud_detection_enabled: true  # Default: true
  cloud_imds_timeout_ms: 500  # Default: 500ms per provider
  fleetdm_enabled: false      # Default: false
  fleetdm_host_uuid: ""       # Optional, populated by fleet enrollment
```

### Hub-API Environment

```bash
# Attestation enforcement
ATTESTATION_ENABLED=true
ATTESTATION_MIN_CONFIDENCE=medium  # high|medium|low|minimal

# FleetDM integration (optional)
FLEETDM_URL=https://fleet.example.com
FLEETDM_API_KEY=<api-key>
FLEETDM_TIMEOUT_SECONDS=5

# Drift detection thresholds
ATTESTATION_DRIFT_REJECT_THRESHOLD=0.6
ATTESTATION_DRIFT_ALERT_THRESHOLD=0.3
```

---

## JWT Claims

All access tokens include attestation metadata:

```json
{
  "sub": "client-uuid",
  "attest_conf": 92,
  "attest_method": "tpm",
  "attest_hash": "sha256:a1b2c3d4...",
  "attest_composite_hash": "sha256:e5f6g7h8...",
  "attest_signals": {
    "tpm_pcr": true,
    "cloud_iid": false,
    "dmi_uuid": true,
    "dmi_board_serial": true,
    "fleetdm_matched": false,
    "mac_addresses": true,
    "disk_serials": true,
    "dmi_model": true,
    "cpu_match": true
  },
  "iat": 1709251234,
  "exp": 1709337634
}
```

**Claims**:
- `attest_conf`: Integer 0-100, confidence percentage
- `attest_method`: String, primary method (tpm, cloud_iid, fingerprint, minimal)
- `attest_hash`: SHA256 of all signals (stable + volatile)
- `attest_composite_hash`: SHA256 of stable fields only (for drift detection)
- `attest_signals`: Boolean map of signal availability

---

## API Endpoints

### Challenge Request

```
POST /api/v1/attestation/challenge
Content-Type: application/json

Response (200):
{
  "status": "success",
  "data": {
    "nonce": "a1b2c3d4e5f6...",
    "ttl_seconds": 300,
    "banks": [0, 1, 2, 7]
  },
  "meta": {}
}
```

**Purpose**: Obtain a TPM challenge nonce for signed attestation. Valid for 5 minutes.

### Registration with Attestation

```
POST /api/v1/register
Content-Type: application/json

{
  "hostname": "prod-web-01",
  "attestation": {
    "confidence_score": 85,
    "confidence_level": "high",
    "tpm_pcr_quote": "...",
    "tpm_signature": "...",
    "cloud_iid_provider": "aws",
    "cloud_iid_instance_id": "i-1234567890abcdef0",
    "dmi_product_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "dmi_board_serial": "LXKT123456",
    "dmi_sys_vendor": "Dell Inc.",
    "dmi_product_name": "PowerEdge R740",
    "mac_addresses": ["00:11:22:33:44:55", "00:11:22:33:44:56"],
    "disk_serials": ["SSDJ123456"],
    "cpu_model": "Intel(R) Xeon(R) Platinum 8280",
    "cpu_count": 28,
    "composite_hash": "sha256:e5f6g7h8..."
  }
}

Response (201):
{
  "status": "success",
  "data": {
    "client_id": "...",
    "token": "...",
    "attestation_confidence": "high"
  },
  "meta": {}
}
```

### Token Refresh with Attestation

```
POST /api/v1/token/refresh
Content-Type: application/json
Authorization: Bearer <current-token>

{
  "attestation": {
    "confidence_score": 85,
    "tpm_pcr_quote": "...",
    "dmi_product_uuid": "550e8400-e29b-41d4-a716-446655440000"
  }
}

Response (200):
{
  "status": "success",
  "data": {
    "token": "...",
    "attestation_confidence": "high",
    "drift_detected": false
  },
  "meta": {}
}
```

If drift_detected is true, the token includes a security event ID for audit purposes.

---

## Troubleshooting

### TPM Not Available

**Symptom**: Attestation confidence drops from HIGH to LOW

**Check**:
```bash
ls -la /dev/tpm* /dev/tpmrm*
```

**Solution**: Ensure TPM device is accessible; rebuild with `-tags tpm`

### Cloud IMDS Timeout

**Symptom**: 500ms delays on non-cloud systems

**Check**: This is normal behavior; client tries AWS→GCP→Azure then falls back to TPM+DMI

**Solution**: Disable cloud detection on on-prem systems:
```yaml
attestation:
  cloud_detection_enabled: false
```

### FleetDM Match Failure

**Symptom**: FleetDM points not awarded despite valid credentials

**Check**: Verify fields in FleetDM:
```bash
curl -H "Authorization: Bearer $FLEETDM_API_KEY" \
  https://fleet.example.com/api/v1/fleet/hosts \
  | jq '.[] | {uuid, hardware}'
```

**Solution**: Ensure hardware_serial and hardware_model are populated in FleetDM

### High Drift Score on Legitimate Change

**Symptom**: Token refresh rejected after hardware upgrade

**Cause**: Upgrade touched multiple fields (new CPU, new BIOS)

**Solution**: Re-register with new hardware fingerprint; document change in audit log

---

## Security Considerations

1. **Nonce Replay**: Challenge nonces are single-use, expire after 5 minutes
2. **TPM Key Protection**: Private keys remain in TPM; never exported
3. **IMDS Verification**: Cloud identity docs are cryptographically signed by cloud provider
4. **Drift Thresholds**: Conservative defaults prevent lockout; tune for your environment
5. **FleetDM Sync**: Run periodic audits comparing Tobogganing records to FleetDM source of truth

---

## References

- TPM 2.0 Spec: https://trustedcomputinggroup.org/
- Cloud IMDS Docs: [AWS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html), [GCP](https://cloud.google.com/compute/docs/metadata/overview), [Azure](https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service)
- FleetDM API: https://fleetdm.com/docs/api
- DMI Spec: https://www.dmtf.org/standards/smbios
