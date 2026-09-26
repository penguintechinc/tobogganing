//! Machine-JWT signing for control-plane enrollment and authenticated
//! calls, built on the shared [`penguin_aaa::Es256Signer`] primitive. Every
//! inter-service call carries a short-lived signed JWT per the org's
//! universal auth policy (`aud="headend"`, TTL capped at 5 minutes).
//! ES256-only, per the org's EC-primary signing policy — RSA stays a
//! verify-only legacy backup elsewhere in the org, never a new signer (see
//! `penguin_aaa`'s crate-root doc for the full algorithm policy and why no
//! bundled multi-algorithm JWT crate is used here).

use crate::error::{AgentError, Result};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use penguin_aaa::{AaaError, Claims, Es256Signer};
use serde::de::DeserializeOwned;
use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// Claims embedded in a short-lived machine JWT authenticating this node
/// against the control plane's `headend` audience — an alias for the
/// shared `penguin_aaa::Claims` shape (`sub`/`iss`/`aud`/`iat`/`exp`/
/// `scope`, plus optional `tenant`/`teams`/`roles` this workspace's
/// machine-to-machine tokens leave empty). `node_type` travels alongside
/// this token in `EnrollRequest::node_type`, not inside it — mirrors
/// `hub-router-rs`'s `TokenExchangeRequest`, and no consumer decodes a
/// `node_type` claim off this token today.
pub type MachineJwtClaims = Claims;

/// Signs short-lived machine JWTs (JWS) for enrollment and authenticated
/// control-plane calls via [`penguin_aaa::Es256Signer`]. Holds only an
/// encoding key — this signer never verifies incoming tokens, since
/// verification is the control plane's job.
pub struct MachineJwtSigner {
    inner: Es256Signer,
}

impl MachineJwtSigner {
    /// Builds a signer from an already-loaded [`Es256Signer`] — the
    /// constructor of choice for tests and callers that manage key
    /// material themselves.
    pub fn new(inner: Es256Signer) -> Self {
        Self { inner }
    }

    /// Loads an EC P-256 private key PEM file from disk and builds an
    /// ES256-only signer.
    ///
    /// The signing key is a K8s Secret mounted at `0600` (owner read/write
    /// only) — full platform-secure storage (Keychain/Keystore/secure
    /// enclave) is the desktop-`penguind` client's concern per `client.md`,
    /// not this server-side/DaemonSet agent's. What this agent *can* and
    /// must enforce at load time is that the mount actually landed with
    /// tightened permissions: on Unix, [`check_key_permissions`] rejects
    /// any mode with a group or world bit set (`mode & 0o077 != 0`) —
    /// fail-closed, since a group/world-readable copy of this key lets
    /// another local user or container forge machine JWTs as this node.
    pub fn from_pem_file(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        check_key_permissions(path)?;
        let pem = std::fs::read(path)?;
        let inner = Es256Signer::from_ec_pem(&pem).map_err(AgentError::from)?;
        Ok(Self::new(inner))
    }

    /// Signs a new machine JWT for `node_id` with `scope`, valid for `ttl`
    /// from now against the fixed `"headend"` audience. Callers should keep
    /// `ttl` at or below 5 minutes per the short-lived-JWT policy.
    pub fn sign(&self, issuer: &str, node_id: &str, scope: &str, ttl: Duration) -> Result<String> {
        let now = current_unix_time()?;
        let claims = Claims::new(
            node_id,
            issuer,
            "headend",
            now,
            now + ttl.as_secs() as i64,
            scope,
        );
        self.inner.sign(&claims).map_err(AgentError::from)
    }
}

/// Verifies that the key file at `path` is not group/world-accessible
/// (`mode & 0o077 != 0`) before it is ever read — fail-closed: a key
/// mounted or left with looser permissions than the `0600` the K8s Secret
/// mount is expected to produce is refused rather than silently loaded, so
/// a misconfigured mount or a shared-filesystem edge deployment can't leak
/// this node's signing key to another local user or container.
#[cfg(unix)]
fn check_key_permissions(path: &Path) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    let mode = std::fs::metadata(path)?.permissions().mode();
    if mode & 0o077 != 0 {
        return Err(AgentError::Config(format!(
            "machine-JWT signing key at {} is group/world-accessible (mode {:o}); expected 0600 or tighter — refusing to load",
            path.display(),
            mode & 0o777,
        )));
    }
    Ok(())
}

/// Non-Unix fallback: the mode bits this check inspects don't exist on
/// non-Unix targets, and no current deployment (K8s DaemonSet, bare-metal
/// edge) loads this key on one — nothing to enforce.
#[cfg(not(unix))]
fn check_key_permissions(_path: &Path) -> Result<()> {
    Ok(())
}

/// Decodes the claims of an opaque JWT **without verifying its signature**.
/// Used only to read informational claims (e.g. `tenant`, `exp`) issued by
/// an already-TLS-authenticated control plane — never for authorization
/// decisions, which always go through full signature + claim validation
/// (see [`penguin_aaa::Es256Verifier`] on the control-plane side).
///
/// Hand-rolled here (base64url-decode the payload segment, then parse with
/// `serde_json`) rather than through `penguin_aaa`, which has no
/// unverified-decode helper as of v0.1 — flag for a v0.2 follow-up so this
/// logic doesn't get reimplemented independently by every consumer
/// (`node-agent`, `hub-router-rs`, `testserver-rs`).
pub fn decode_unverified_claims<T: DeserializeOwned>(token: &str) -> Result<T> {
    let payload_b64 = token.split('.').nth(1).ok_or_else(|| {
        AgentError::Jwt(AaaError::Verification(
            "malformed JWT: fewer than two '.'-separated segments".to_string(),
        ))
    })?;
    let payload_bytes = URL_SAFE_NO_PAD.decode(payload_b64).map_err(|e| {
        AgentError::Jwt(AaaError::Verification(format!(
            "malformed JWT payload base64: {e}"
        )))
    })?;
    serde_json::from_slice(&payload_bytes).map_err(|e| {
        AgentError::Jwt(AaaError::Verification(format!(
            "malformed JWT payload JSON: {e}"
        )))
    })
}

fn current_unix_time() -> Result<i64> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .map_err(|e| AgentError::Config(format!("system clock before unix epoch: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use p256::ecdsa::{SigningKey, VerifyingKey};
    use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
    use penguin_aaa::Es256Verifier;
    use serde::Deserialize;

    #[derive(Debug, Deserialize)]
    struct TenantOnly {
        #[serde(default)]
        tenant: String,
    }

    /// Generates a fresh, throwaway P-256 keypair as PKCS#8/SPKI PEMs —
    /// good only for round-tripping in this test, never a committed key
    /// value.
    fn generate_test_keypair() -> (String, String) {
        let signing_key = SigningKey::random(&mut rand_core::OsRng);
        let private_pem = signing_key
            .to_pkcs8_pem(LineEnding::LF)
            .expect("encoding a freshly generated P-256 key as PKCS#8 PEM must succeed")
            .to_string();
        let public_pem = VerifyingKey::from(&signing_key)
            .to_public_key_pem(LineEnding::LF)
            .expect("encoding the matching public key as SPKI PEM must succeed");
        (private_pem, public_pem)
    }

    #[test]
    fn machine_jwt_signs_and_verifies_via_penguin_aaa() {
        let (private_pem, public_pem) = generate_test_keypair();
        let signer = MachineJwtSigner::new(
            Es256Signer::from_ec_pem(private_pem.as_bytes())
                .expect("a freshly generated P-256 key must load"),
        );
        let token = signer
            .sign(
                "node-agent-test",
                "node-123",
                "dns:config:read metrics:write",
                Duration::from_secs(60),
            )
            .expect("signing with a valid EC key must succeed");

        let verifier = Es256Verifier::from_public_key_pem(public_pem.as_bytes())
            .expect("the matching public key must load")
            .with_audience("headend")
            .with_issuer("node-agent-test");
        let claims = verifier
            .verify(&token)
            .expect("a token signed above must verify against the matching public key");

        assert_eq!(claims.sub, "node-123");
        assert_eq!(claims.aud, "headend");
        assert_eq!(claims.scope, "dns:config:read metrics:write");
        assert!(claims.exp > claims.iat);
    }

    #[test]
    fn decode_unverified_claims_reads_tenant_without_a_key() {
        let (private_pem, _public_pem) = generate_test_keypair();
        let signer = MachineJwtSigner::new(
            Es256Signer::from_ec_pem(private_pem.as_bytes())
                .expect("a freshly generated P-256 key must load"),
        );
        let token = signer
            .sign(
                "node-agent-test",
                "node-456",
                "dns:config:read",
                Duration::from_secs(30),
            )
            .expect("signing must succeed");

        // `tenant` is absent from a machine-to-machine token built via
        // `Claims::new` (skipped on serialize), so this proves
        // decode_unverified_claims tolerates a missing optional field via
        // #[serde(default)] rather than erroring.
        let claims: TenantOnly =
            decode_unverified_claims(&token).expect("unverified decode must not require a key");
        assert_eq!(claims.tenant, "");
    }

    #[test]
    #[cfg(unix)]
    fn from_pem_file_rejects_a_group_or_world_readable_key() {
        use std::os::unix::fs::PermissionsExt;
        let path = std::env::temp_dir().join(format!(
            "node-agent-jwt-test-{}-loose.pem",
            std::process::id()
        ));
        // Content is irrelevant here — the permission gate must reject the
        // file before its bytes are ever read.
        std::fs::write(&path, b"not a real key").expect("writing the test file must succeed");
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644))
            .expect("chmod must succeed");

        // `expect_err` would require `MachineJwtSigner: Debug`, which it
        // does not implement — match instead.
        let err = match MachineJwtSigner::from_pem_file(&path) {
            Ok(_) => panic!("a 0644 key file must be rejected before its contents are ever parsed"),
            Err(err) => err,
        };
        assert!(matches!(err, AgentError::Config(msg) if msg.contains("group/world-accessible")));

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    #[cfg(unix)]
    fn from_pem_file_accepts_an_owner_only_key_and_proceeds_past_the_permission_check() {
        use std::os::unix::fs::PermissionsExt;
        let path = std::env::temp_dir().join(format!(
            "node-agent-jwt-test-{}-tight.pem",
            std::process::id()
        ));
        std::fs::write(&path, b"not a real key").expect("writing the test file must succeed");
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))
            .expect("chmod must succeed");

        let err = match MachineJwtSigner::from_pem_file(&path) {
            Ok(_) => panic!("garbage PEM content must still fail to parse"),
            Err(err) => err,
        };
        // Proves the permission gate passed (an 0o600 file is never
        // rejected on permissions) and the failure came from PEM parsing
        // instead, not from `check_key_permissions`.
        assert!(matches!(err, AgentError::Jwt(_)));

        let _ = std::fs::remove_file(&path);
    }
}
