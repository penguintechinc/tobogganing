# Phase 4b — Enterprise External KMS (AWS/GCP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pluggable `core/crypto` key providers — in-app (default) plus Enterprise-gated AWS KMS and GCP KMS backends — for the RS256 JWT signing key and the at-rest data-encryption key, built around `sign()`/unwrap operations because a real KMS never exports private key material.

**Architecture:** The `KeyProvider` protocol changes from key-export (`private_pem`) to an operation interface (`async sign(data) -> bytes` + `public_pem` + `kid`). JWT issuance assembles the JWS manually and calls `provider.sign()`; verification stays local against the cached public key (no KMS call per request). At-rest encryption becomes envelope encryption: a `DataKeyProvider` supplies the 32-byte DEK — from env (in-app) or by KMS-unwrapping a wrapped blob at boot. Provider selection is config-driven (`KMS_PROVIDER`) and gated behind the Enterprise flag `tobogganing.core.external_kms` + entitlement `core.external_kms` (bare key!), falling back to in-app with a prominent warning when either is absent.

**Tech Stack:** Python 3.13, Quart, `cryptography`, PyJWT (verify only), boto3 (lazy/optional), google-cloud-kms (lazy/optional), pytest + pytest-asyncio.

## Global Constraints

- Every file ≤1000 lines; type hints on every function; PEP 257 docstrings; `@dataclass(slots=True)` where a dataclass fits.
- All async — `sign()` is `async def` on the protocol; KMS SDK calls wrapped in `asyncio.to_thread` *inside* the provider; in-app signs inline (fast local crypto).
- Flag key = `tobogganing.core.external_kms` (via `feature_enabled("core", "external_kms")`); entitlement key = **bare** `core.external_kms` — a `tobogganing.`-prefixed entitlement silently degrades the gate to community (locked-in trap).
- No secrets in logs ever; wrapped blobs may be logged length-only.
- boto3/google-cloud-kms are lazy imports — Community installs must run without them installed.
- Tests use fake KMS clients injected via constructor — no network, no moto.
- Run the full suite (`cd core && python3 -m pytest tests/`) at each commit checkpoint; never commit red.
- Branch: `feature/phase-4b-kms` (off `feature/phase-dal-async-fix`). Orchestrator commits; workers edit-and-test only.

---

### Task 1: Operation-based KeyProvider protocol + in-app sign

**Files:**
- Modify: `core/crypto/keys.py`
- Test: `core/tests/test_crypto_keys.py` (extend existing if present, else create)

**Interfaces:**
- Produces: `KeyProvider` protocol = `async def sign(self, data: bytes) -> bytes`, `public_pem: str` (property), `kid: str` (property). `InAppKeyProvider(private_key_pem, public_key_pem)` implementing it. `private_pem` REMOVED from the protocol (retained as a private attr on InApp only). `generate_rsa_key_pair()` and `build_key_provider()` signatures unchanged (Task 6 replaces `build_key_provider`'s selection logic).
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_crypto_keys.py (add)
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from core.crypto.keys import InAppKeyProvider, generate_rsa_key_pair


@pytest.mark.asyncio
async def test_inapp_sign_verifies_against_public_key() -> None:
    """InAppKeyProvider.sign produces a PKCS1v15/SHA256 signature verifiable with its public key."""
    priv, pub = generate_rsa_key_pair()
    provider = InAppKeyProvider(priv, pub)
    data = b"header.payload"
    sig = await provider.sign(data)
    public_key = serialization.load_pem_public_key(pub.encode())
    # Raises InvalidSignature on failure
    public_key.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())


def test_protocol_has_no_private_pem() -> None:
    """The KeyProvider protocol no longer exposes private key material."""
    from core.crypto.keys import KeyProvider
    assert "private_pem" not in getattr(KeyProvider, "__protocol_attrs__", set()) or True
    # Structural check: annotations/members on the Protocol class
    assert not hasattr(KeyProvider, "private_pem")
```

- [ ] **Step 2: Run to verify failure** — `cd core && python3 -m pytest tests/test_crypto_keys.py -v` → FAIL (`sign` missing).

- [ ] **Step 3: Implement** — in `core/crypto/keys.py`: protocol becomes

```python
class KeyProvider(Protocol):
    """Protocol for RS256 signing-key providers (operation-based; no private-key export)."""

    async def sign(self, data: bytes) -> bytes:
        """Sign data with RSASSA-PKCS1-v1_5 / SHA-256 and return the raw signature."""
        ...

    @property
    def public_pem(self) -> str:
        """Return the public key in PEM (SubjectPublicKeyInfo) format."""
        ...

    @property
    def kid(self) -> str:
        """Return the Key ID (sha256(public_pem)[:16])."""
        ...
```

`InAppKeyProvider` keeps `_private_key_pem` internally, parses it once in `__init__` to a private-key object, and implements:

```python
    async def sign(self, data: bytes) -> bytes:
        """Sign locally with the in-app RSA private key (fast; no thread hop needed)."""
        return self._private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())
```

Delete the `private_pem` property from `InAppKeyProvider` and the protocol. Leave the AWS/GCP stub classes for Tasks 3–4 to replace.

- [ ] **Step 4: Run tests** → PASS. Also run the full suite — expect failures ONLY in `core/auth/jwt.py` consumers (fixed in Task 2); if so, proceed to Task 2 before committing.

### Task 2: Manual JWS assembly — async `encode_access_token`

**Files:**
- Modify: `core/auth/jwt.py`
- Modify: `core/auth/service.py:340` (add `await`)
- Modify: `core/modules/sase/api/jwt.py:168,182,282` (add `await`)
- Test: `core/tests/test_auth_jwt.py` (existing jwt tests file — adapt)

**Interfaces:**
- Produces: `async def encode_access_token(claims, key_provider, ttl_hours=1) -> str`. `decode_token` unchanged (sync, local verify).
- Consumes: Task 1 `KeyProvider.sign`.

- [ ] **Step 1: Write/adapt failing test**

```python
@pytest.mark.asyncio
async def test_encode_access_token_signs_via_provider_and_verifies() -> None:
    """A token assembled via provider.sign() verifies with standard PyJWT decode."""
    priv, pub = generate_rsa_key_pair()
    provider = InAppKeyProvider(priv, pub)
    token = await encode_access_token(
        {"sub": "u1", "iss": "tobogganing", "aud": "api", "tenant": "t1"}, provider
    )
    claims = pyjwt.decode(token, pub, algorithms=["RS256"], options={"verify_aud": False})
    assert claims["sub"] == "u1"
    header = pyjwt.get_unverified_header(token)
    assert header["kid"] == provider.kid and header["alg"] == "RS256"
```

- [ ] **Step 2: Run** → FAIL (encode still uses `private_pem`).

- [ ] **Step 3: Implement** — replace the `pyjwt.encode` call:

```python
import base64
import json


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding (JWS serialization)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


async def encode_access_token(claims, key_provider, ttl_hours=1) -> str:
    ...  # keep required-claims validation + payload assembly exactly as-is
    header = {"alg": "RS256", "typ": "JWT", "kid": key_provider.kid}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = await key_provider.sign(signing_input.encode("ascii"))
    return signing_input + "." + _b64url(signature)
```

Add `await` at the four call sites (they are all already `async def` contexts). Keep full type hints + docstrings.

- [ ] **Step 4: Run full suite** — `cd core && python3 -m pytest tests/` → ALL PASS (616+).

- [ ] **Step 5: Commit** — `feat(crypto): operation-based KeyProvider; JWT issuance signs via provider.sign()`

### Task 3: AwsKmsKeyProvider

**Files:**
- Modify: `core/crypto/keys.py` (replace stub)
- Test: `core/tests/test_crypto_kms_aws.py` (create)

**Interfaces:**
- Produces: `AwsKmsKeyProvider(key_arn: str, client: Any | None = None)`. Lazy `import boto3` only when `client is None`. `public_pem`/`kid` from cached `GetPublicKey` (DER→PEM). `async sign()` = sha256 digest → `asyncio.to_thread(client.sign, KeyId=..., Message=digest, MessageType="DIGEST", SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256")` → `response["Signature"]`.
- Consumes: Task 1 protocol.

- [ ] **Step 1: Failing tests** — fake client backed by a REAL local RSA key so signatures are genuine:

```python
class FakeKmsClient:
    """Stands in for boto3 KMS at the SDK boundary; signs with a real local RSA key."""

    def __init__(self) -> None:
        priv_pem, pub_pem = generate_rsa_key_pair()
        self._key = serialization.load_pem_private_key(priv_pem.encode(), password=None)
        self._pub_der = self._key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.sign_calls: list[dict] = []

    def get_public_key(self, KeyId: str) -> dict:
        return {"PublicKey": self._pub_der, "SigningAlgorithms": ["RSASSA_PKCS1_V1_5_SHA_256"]}

    def sign(self, **kwargs) -> dict:
        self.sign_calls.append(kwargs)
        assert kwargs["MessageType"] == "DIGEST"
        sig = self._key.sign(
            kwargs["Message"],
            padding.PKCS1v15(),
            utils.Prehashed(hashes.SHA256()),
        )
        return {"Signature": sig}
```

Tests: (a) `public_pem` is valid PEM + `kid` = sha256(public_pem)[:16]; (b) `await provider.sign(b"data")` verifies against `public_pem`; (c) end-to-end: `encode_access_token` with this provider → `pyjwt.decode` against `provider.public_pem` succeeds; (d) `get_public_key` called exactly once across repeated property access (cached).

- [ ] **Step 2: Run** → FAIL (stub raises NotImplementedError).
- [ ] **Step 3: Implement** as per interface block; DER→PEM via `load_der_public_key(...).public_bytes(PEM, SubjectPublicKeyInfo)`; cache in `__init__`-triggered lazy attr; never log key material.
- [ ] **Step 4: Run** → PASS (incl. full suite).
- [ ] **Step 5: Commit** — `feat(crypto): AWS KMS signing provider (GetPublicKey cache + DIGEST sign)`

### Task 4: GcpKmsKeyProvider

**Files:**
- Modify: `core/crypto/keys.py` (replace stub)
- Test: `core/tests/test_crypto_kms_gcp.py` (create)

**Interfaces:**
- Produces: `GcpKmsKeyProvider(key_name: str, client: Any | None = None)` — `key_name` = full CryptoKeyVersion resource name. Lazy `from google.cloud import kms` only when `client is None`. `public_pem` from cached `client.get_public_key(request={"name": key_name}).pem`. `async sign()` = sha256 digest → `asyncio.to_thread(client.asymmetric_sign, request={"name": key_name, "digest": {"sha256": digest}})` → `response.signature`.
- Consumes: Task 1 protocol.

- [ ] **Step 1: Failing tests** — mirror Task 3 with a `FakeGcpKmsClient` (real local RSA key; `get_public_key` returns an object with `.pem`; `asymmetric_sign` returns an object with `.signature`; use `types.SimpleNamespace`). Same four assertions.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS + full suite.
- [ ] **Step 5: Commit** — `feat(crypto): GCP KMS signing provider`

### Task 5: DataKeyProvider + envelope encryption (fixes pre-existing Fernet key bug)

**Files:**
- Create: `core/crypto/data_keys.py`
- Create: `core/crypto/wrap_data_key.py` (`python3 -m core.crypto.wrap_data_key`)
- Modify: `core/crypto/secrets.py`
- Modify: `core/crypto/__init__.py` (exports)
- Test: `core/tests/test_crypto_data_keys.py` (create), `core/tests/test_crypto_secrets.py` (adapt)

**Interfaces:**
- Produces: `DataKeyProvider` protocol: `def get_data_key(self) -> bytes` (32 raw bytes; sync — resolved once at boot). `InAppDataKeyProvider()` (env `DATA_ENCRYPTION_KEY` = b64 of 32 bytes; dev fallback generates ephemeral + warning — port existing semantics). `AwsKmsDataKeyProvider(key_arn, wrapped_key_b64, client=None)` / `GcpKmsDataKeyProvider(key_name, wrapped_key_b64, client=None)`: b64-decode blob → KMS `Decrypt`/`decrypt` once in `get_data_key` (cache result). `SecretEncryptor.__init__(self, key: bytes)` takes the 32-byte DEK and builds `Fernet(base64.urlsafe_b64encode(key))` — **this fixes the pre-existing bug where any env-set key failed Fernet construction**. `get_encryptor()` builds from the provider chosen in Task 6 (until then: `InAppDataKeyProvider`).
- Consumes: fake KMS clients pattern from Tasks 3–4 (`encrypt`/`decrypt` locally with Fernet inside the fake to simulate wrap/unwrap).

- [ ] **Step 1: Failing tests** — (a) in-app provider round-trips env key: set `DATA_ENCRYPTION_KEY=b64(32 bytes)`, `SecretEncryptor(provider.get_data_key())` encrypts+decrypts ("was impossible before — regression: fernet env-key construction"); (b) two encryptors from same key decrypt each other's ciphertext; (c) AWS/GCP providers return the unwrapped 32 bytes via fake client and call Decrypt exactly once (cached); (d) tampered ciphertext → ValueError; (e) `wrap_data_key` main() with fake client prints b64 blob that the provider can unwrap (capture stdout).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (files ≤1000 lines; wrap CLI prints ONLY the wrapped blob + usage hint, never the plaintext DEK). **Step 4: Run** → PASS + full suite.
- [ ] **Step 5: Commit** — `feat(crypto): envelope encryption via DataKeyProvider; fix Fernet env-key construction`

### Task 6: Gated selection + boot wiring + core entitlement registration

**Files:**
- Create: `core/crypto/selection.py`
- Modify: `core/registry/registry.py` (add `register_entitlements`)
- Modify: `core/app.py` (register core flag/entitlement; set `app.config["KEY_PROVIDER"]`; wire encryptor provider)
- Modify: `core/crypto/keys.py` (`build_key_provider` delegates to selection or is superseded — keep name working)
- Modify: `.env.example`
- Test: `core/tests/test_crypto_selection.py` (create)

**Interfaces:**
- Produces:
  - `ModuleRegistry.register_entitlements(entitlements: list[Entitlement]) -> None` — extends `_entitlements` (core-level features without a module contract).
  - `selection.build_signing_provider(registry: Any) -> KeyProvider` and `selection.build_data_key_provider(registry: Any) -> DataKeyProvider`: read `KMS_PROVIDER` (`inapp` default). For `aws`/`gcp`: require `feature_enabled("core", "external_kms")` AND `_is_licensed_for_tier(tier_of("core.external_kms", registry))`; on failure → `logger.warning("external_kms_not_entitled_falling_back_inapp")` + in-app. Env: `AWS_KMS_SIGNING_KEY_ARN`, `AWS_KMS_DATA_KEY_ARN`, `GCP_KMS_SIGNING_KEY`, `GCP_KMS_DATA_KEY`, `WRAPPED_DATA_KEY`. Missing required env for a selected KMS → `ValueError` (fail loud, not silent fallback — misconfiguration ≠ unlicensed).
  - `create_app` registers `Entitlement(feature="core.external_kms", tier="enterprise")` + flag `tobogganing.core.external_kms` via `register_entitlements`, then sets `app.config["KEY_PROVIDER"] = build_signing_provider(registry)` and initializes the global encryptor from `build_data_key_provider(registry)`.
  - Metering: when an external provider is active, record the per-feature activation the same way existing per-feature Enterprise entitlements are surfaced in `core/entitlements/metering.py` (inspect `Usage`; if it has no per-feature field, add `features: list[str]` to the snapshot and include `"core.external_kms"`).
- Consumes: Tasks 1–5 providers; `core.entitlements.gate.tier_of/_is_licensed_for_tier`; `core.flags.feature_enabled`.

- [ ] **Step 1: Failing tests** — (a) default env → `InAppKeyProvider`; (b) `KMS_PROVIDER=aws` + flag OFF → in-app (assert warning logged); (c) flag ON (monkeypatch `feature_enabled`) + unlicensed → in-app; (d) flag ON + `monkeypatch core.entitlements.gate._is_licensed_for_tier` → True + fake client factory → `AwsKmsKeyProvider`; (e) same for GCP; (f) `KMS_PROVIDER=aws` licensed but missing ARN env → `ValueError`; (g) registry: `entitlement_for("core.external_kms").tier == "enterprise"` after `create_app` (via `async with app.test_app()` if needed); (h) entitlement key is BARE (`core.external_kms` — assert `entitlement_for("tobogganing.core.external_kms") is None`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Full suite** → PASS.
- [ ] **Step 5: Commit** — `feat(crypto): Enterprise-gated KMS provider selection + core entitlement wiring`

### Task 7: Optional deps, docs, verification sweep

**Files:**
- Create: `core/requirements-kms.in` (+ compiled `core/requirements-kms.txt` via `uv pip compile --generate-hashes`) — pinned boto3, google-cloud-kms
- Modify: `docs/` — new `docs/KMS.md` (setup: key creation, IAM/roles least-privilege — `kms:Sign`+`kms:GetPublicKey`+`kms:Decrypt` only; wrap-key procedure; env matrix; fallback semantics)
- Modify: `README.md` (Enterprise features list mentions external KMS + pointer to docs/KMS.md)
- Modify: memory + `.PLAN`/`.TODO` if present

**Steps:**
- [ ] Write requirements + compile with hashes (do NOT add to base requirements — optional extra).
- [ ] Write docs (include the entitlement-key bare-vs-prefixed note and the "misconfig fails loud / unlicensed falls back" distinction).
- [ ] Run: full suite, `flake8`/`black --check`/`isort --check` on touched files, `bandit -r core/crypto`, line-count check ≤1000 on all touched files.
- [ ] Commit — `docs(kms): Enterprise external KMS setup guide + pinned optional deps`
- [ ] Push branch; open stacked PR (base `feature/phase-dal-async-fix`).

## Self-Review Notes

- Spec coverage: sign-vs-export resolution (T1–T2), AWS (T3), GCP (T4), at-rest envelope (T5), config selection + Enterprise flag/entitlement + fallback + metering (T6), docs/deps (T7). ✔
- Type consistency: `sign` async everywhere; `get_data_key` sync everywhere; `KeyProvider` consumers only use `sign/public_pem/kid`. ✔
- No placeholders; all steps carry code or exact interface contracts. ✔
