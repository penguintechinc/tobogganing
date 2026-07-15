# Enterprise External KMS (AWS/GCP)

Tobogganing supports pluggable key management providers for cryptographic operations. This guide covers setup and deployment of external KMS backends for Enterprise-tier deployments.

## Overview

### Default: In-App KMS

By default, Tobogganing uses an in-app key provider for RS256 JWT signing and AES-256 data encryption. This is suitable for development and Community deployments:

- **JWT Signing**: In-app RSA-2048 private key loaded from `JWT_PRIVATE_KEY_PEM` or `JWT_PRIVATE_KEY_PATH`
- **Data Encryption**: 32-byte symmetric key from `DATA_ENCRYPTION_KEY` environment variable
- **No external dependencies**: boto3 and google-cloud-kms are optional; Community installs run without them

### Enterprise: External KMS

Enterprise deployments can offload cryptographic operations to AWS KMS or Google Cloud KMS:

- **AWS KMS**: Asymmetric RSA-2048 key for signing + symmetric key for data encryption
- **GCP Cloud KMS**: Equivalent asymmetric RSA-2048 + symmetric key setup
- **Operation-based design**: Keys never leave KMS; only signatures and unwrapped DEKs are returned
- **No plaintext exports**: Private key material is never transmitted or logged
- **Licensing gate**: Requires Enterprise tier + `core.external_kms` entitlement

## Operation-Based Crypto Design

### Why "Operations" Not "Exports"

Real KMS providers do not export private key material. Instead, Tobogganing uses an operation-based protocol:

| Operation | Private Key Used | Returns | Use Case |
|-----------|------------------|---------|----------|
| **Sign** | KMS side | Raw bytes signature | JWT issuance (once per token) |
| **Decrypt** (Unwrap) | KMS side | 32-byte plaintext DEK | Boot-time key derivation (once per deploy) |
| **GetPublicKey** | N/A (public) | PEM public key | JWT verification (cached locally, no KMS call per request) |

### Request Path: Zero KMS Calls

1. **JWT Verification**: Local, against cached public key — no KMS call
2. **Data Decryption**: Local, with unwrapped DEK cached at boot — no KMS call per decrypt
3. **Signing**: KMS call (once per token issuance)

Result: Latency overhead only on token issuance; zero overhead on verification/decryption.

## AWS KMS Setup

### Key Creation

Create two AWS KMS keys: one for signing, one for data encryption.

**Signing key** (asymmetric RSA-2048):

```bash
aws kms create-key \
  --description "Tobogganing JWT signing (RS256)" \
  --key-usage SIGN_VERIFY \
  --origin AWS_KMS \
  --region us-east-1
```

Capture the `KeyId` (UUID) from the response; this becomes your `AWS_KMS_SIGNING_KEY_ARN`:

```
arn:aws:kms:us-east-1:ACCOUNT_ID:key/UUID
```

**Data encryption key** (symmetric AES-256):

```bash
aws kms create-key \
  --description "Tobogganing data encryption (AES-256)" \
  --key-usage ENCRYPT_DECRYPT \
  --origin AWS_KMS \
  --region us-east-1
```

Capture `AWS_KMS_DATA_KEY_ARN` similarly.

### Least-Privilege IAM

Create a policy scoped to these two keys only:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kms:Sign",
        "kms:GetPublicKey"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT_ID:key/SIGNING_KEY_UUID"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT_ID:key/DATA_KEY_UUID"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT_ID:key/DATA_KEY_UUID"
    }
  ]
}
```

Attach this policy to the Tobogganing service role/user. Never grant wildcard KMS permissions.

### AWS Environment Variables

```bash
AWS_KMS_SIGNING_KEY_ARN="arn:aws:kms:us-east-1:ACCOUNT_ID:key/SIGNING_KEY_UUID"
AWS_KMS_DATA_KEY_ARN="arn:aws:kms:us-east-1:ACCOUNT_ID:key/DATA_KEY_UUID"
KMS_PROVIDER="aws"
```

AWS credentials are resolved via standard AWS SDK mechanisms (IAM role, `~/.aws/credentials`, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`).

## GCP Cloud KMS Setup

### Key Creation

Create two keys: asymmetric RSA-2048 for signing, symmetric for data encryption.

**Signing key**:

```bash
# Create key ring (if not present)
gcloud kms keyrings create tobogganing --location=us-central1

# Create asymmetric signing key
gcloud kms keys create jwt-signing \
  --location=us-central1 \
  --keyring=tobogganing \
  --purpose=asymmetric-sign \
  --default-algorithm=rsa-sign-pkcs1-2048-sha256

# Create version (optional; latest is default)
gcloud kms keys versions create \
  --key=jwt-signing \
  --location=us-central1 \
  --keyring=tobogganing
```

Capture the full resource name:

```
projects/PROJECT_ID/locations/us-central1/keyRings/tobogganing/cryptoKeys/jwt-signing/cryptoKeyVersions/1
```

**Data encryption key**:

```bash
gcloud kms keys create data-encryption \
  --location=us-central1 \
  --keyring=tobogganing \
  --purpose=encryption \
  --default-algorithm=google-symmetric-encryption
```

### Least-Privilege IAM (GCP)

Assign roles to the Tobogganing service account:

```bash
# Get service account
SERVICE_ACCOUNT="tobogganing@PROJECT_ID.iam.gserviceaccount.com"

# Grant sign/view-public-key on the signing key
gcloud kms keys add-iam-policy-binding jwt-signing \
  --location=us-central1 \
  --keyring=tobogganing \
  --member=serviceAccount:$SERVICE_ACCOUNT \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter \
  --role=roles/cloudkms.publicKeyViewer

# Grant decrypt on the data key
gcloud kms keys add-iam-policy-binding data-encryption \
  --location=us-central1 \
  --keyring=tobogganing \
  --member=serviceAccount:$SERVICE_ACCOUNT \
  --role=roles/cloudkms.cryptoKeyEncrypterDecrypter
```

Or use custom roles restricted to `cloudkms.cryptoKeyVersions.useToSign` + `viewPublicKey` + `useToDecrypt`.

### GCP Environment Variables

```bash
GCP_KMS_SIGNING_KEY="projects/PROJECT_ID/locations/us-central1/keyRings/tobogganing/cryptoKeys/jwt-signing/cryptoKeyVersions/1"
GCP_KMS_DATA_KEY="projects/PROJECT_ID/locations/us-central1/keyRings/tobogganing/cryptoKeys/data-encryption/cryptoKeyVersions/1"
KMS_PROVIDER="gcp"
```

GCP credentials are resolved via Application Default Credentials (ADC): service account key file, Workload Identity, or `GOOGLE_APPLICATION_CREDENTIALS`.

## Data Key Wrapping

The symmetric data-encryption key (DEK) must be wrapped before deployment. The plaintext 32-byte key is never stored or printed; only the wrapped ciphertext is kept.

### Wrap-Key Procedure

Run the wrap-data-key CLI tool locally (or in a secure bootstrap container):

```bash
# Set KMS environment (AWS or GCP)
export KMS_PROVIDER="aws"
export AWS_KMS_DATA_KEY_ARN="arn:aws:kms:us-east-1:ACCOUNT_ID:key/DATA_KEY_UUID"
export AWS_REGION="us-east-1"

# Run wrapper (plaintext DEK is generated internally; not printed)
python3 -m core.crypto.wrap_data_key

# Output: base64-encoded wrapped blob
# WRAPPED_DATA_KEY=agK7awEE...base64-encoded-blob...
```

**Important**: The plaintext DEK is never printed or exported. Only the wrapped ciphertext is displayed. Copy the `WRAPPED_DATA_KEY` value and set it in the deployment environment.

### Bootstrap Deployment

At service startup:

1. Read `WRAPPED_DATA_KEY` env variable
2. Call KMS `Decrypt`/`decrypt` to unwrap → get plaintext 32-byte DEK
3. Cache the plaintext DEK in memory for the lifetime of the process
4. Use cached DEK for all subsequent data encryption/decryption
5. Never write DEK to disk or logs

Result: The plaintext key is memory-resident only; KMS is called exactly once at boot.

## Environment Variable Matrix

### Required for All Setups

| Var | Value | Example |
|-----|-------|---------|
| `KMS_PROVIDER` | `inapp` \| `aws` \| `gcp` | `aws` |

### In-App (Default)

| Var | Source | Fallback |
|-----|--------|----------|
| `JWT_PRIVATE_KEY_PEM` | PEM-encoded RSA private key | Ephemeral key generated at boot (dev only) |
| `JWT_PRIVATE_KEY_PATH` | File path to PEM file | Fallback if `JWT_PRIVATE_KEY_PEM` not set |
| `DATA_ENCRYPTION_KEY` | Base64-encoded 32 bytes | Ephemeral key generated at boot (dev only); logs warning |

### AWS KMS

| Var | Required | Example |
|-----|----------|---------|
| `AWS_KMS_SIGNING_KEY_ARN` | Yes | `arn:aws:kms:us-east-1:123456789:key/abcd-1234...` |
| `AWS_KMS_DATA_KEY_ARN` | Yes | `arn:aws:kms:us-east-1:123456789:key/efgh-5678...` |
| `WRAPPED_DATA_KEY` | Yes | Base64-encoded wrapped blob |
| `AWS_REGION` | Optional | `us-east-1` (default) |
| `AWS_PROFILE` | Optional | `default` |

Missing ARNs → `ValueError` at boot (fail loud, not silent fallback).

### GCP Cloud KMS

| Var | Required | Example |
|-----|----------|---------|
| `GCP_KMS_SIGNING_KEY` | Yes | `projects/my-proj/locations/us-central1/keyRings/kms/cryptoKeys/signing/cryptoKeyVersions/1` |
| `GCP_KMS_DATA_KEY` | Yes | `projects/my-proj/locations/us-central1/keyRings/kms/cryptoKeys/data/cryptoKeyVersions/1` |
| `WRAPPED_DATA_KEY` | Yes | Base64-encoded wrapped blob |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional | Path to service account key file |

Missing key names → `ValueError` at boot.

## Feature Gating & Licensing

### Feature Flag

`tobogganing.core.external_kms` (via PostHog feature flags)

Default: `OFF` (in-app KMS enabled regardless)

### License Entitlement

`core.external_kms` (bare key, no `tobogganing.` prefix; see warning below)

Tier: **Enterprise** only

### Fallback Semantics

| Flag | Licensed | Outcome | Behavior |
|------|----------|---------|----------|
| OFF | Any | In-app KMS | Proceeds normally |
| ON | Yes (Enterprise) | Requested KMS (AWS/GCP) | Uses external provider |
| ON | No (Community/Pro) | Fallback to in-app | Logged warning; continues with in-app |
| ON, misconfigured | Any | Hard failure | `ValueError` at boot; does NOT fall back |

**Critical distinction**: Unlicensed/flag-off → silent fallback with warning. Misconfigured (ARN missing) → crashes on boot.

### Entitlement Key Naming

⚠️ **IMPORTANT**: The entitlement key is **bare** `core.external_kms`, NOT `tobogganing.core.external_kms`.

If you mistakenly use the prefixed key `tobogganing.core.external_kms` in the license server, the gate will silently degrade to Community (unlocked), defeating the paywall.

Always verify: `registry.entitlement_for("core.external_kms").tier == "enterprise"` (no prefix).

## Installation

### Community (Default)

No action needed. In-app KMS is built-in.

### Enterprise (AWS KMS)

```bash
# Install optional AWS KMS dependencies
uv pip install --require-hashes -r core/requirements-kms.txt

# Or manually
pip install boto3==1.43.48 google-cloud-kms==3.15.0
```

### Enterprise (GCP Cloud KMS)

```bash
# Same dependencies file supports both AWS and GCP
uv pip install --require-hashes -r core/requirements-kms.txt
```

### Docker / K8s

Add KMS dependencies to the runtime image:

```dockerfile
# Dockerfile
COPY core/requirements-kms.txt /app/
RUN uv pip install --require-hashes -r /app/core/requirements-kms.txt
```

**Or**, pin versions in main `requirements.txt` if deployment always uses external KMS:

```bash
# requirements.txt
boto3==1.43.48
google-cloud-kms==3.15.0
```

## Deployment Checklist

- [ ] KMS keys created (asymmetric RS256 + symmetric AES-256)
- [ ] Least-privilege IAM/roles assigned to service account
- [ ] Plaintext DEK wrapped: `python3 -m core.crypto.wrap_data_key`
- [ ] `WRAPPED_DATA_KEY` captured and stored securely (e.g., in secrets manager)
- [ ] Environment variables set: `KMS_PROVIDER`, `AWS_KMS_*` or `GCP_KMS_*`, `WRAPPED_DATA_KEY`
- [ ] License entitlement `core.external_kms` (bare key) set to Enterprise tier
- [ ] Feature flag `tobogganing.core.external_kms` enabled in PostHog
- [ ] Service started; check logs for "external_kms enabled" confirmation
- [ ] JWT token issuance works (token verifies against cached public key)
- [ ] Data encryption/decryption works end-to-end

## Troubleshooting

### "ValueError: AWS_KMS_SIGNING_KEY_ARN not set"

`KMS_PROVIDER=aws` is selected, but ARN env vars are missing. Set all required AWS vars or switch to `inapp`.

### "ValueError: GCP_KMS_SIGNING_KEY not set"

`KMS_PROVIDER=gcp` is selected, but key names are missing. Set all required GCP vars or switch to `inapp`.

### "external_kms_not_entitled_falling_back_inapp"

Feature flag is ON or entitlement is missing, but license tier is not Enterprise. Check:

1. Entitlement key is **bare** `core.external_kms` (no `tobogganing.` prefix)
2. License server returns `tier=enterprise` for this key
3. Feature flag `tobogganing.core.external_kms` is enabled

### KMS operation times out

- Verify IAM/permissions are correctly scoped
- Check network connectivity from Tobogganing to AWS/GCP
- Increase operation timeouts if latency is expected (e.g., cross-region KMS)

### Logs show "external_kms_enabled: false"

KMS provider is not active. Check:

1. `KMS_PROVIDER` env is set to `aws` or `gcp`
2. All required KMS env vars are present
3. License entitlement and feature flag are both enabled

---

**See Also:**
- [AWS KMS Documentation](https://docs.aws.amazon.com/kms/)
- [GCP Cloud KMS Documentation](https://cloud.google.com/kms/docs)
- [Tobogganing Security Architecture](security.md)
