//! Machine-JWT signing for control-plane enrollment and authenticated
//! calls. Every inter-service call carries a short-lived signed JWT per the
//! org's universal auth policy (`aud="headend"`, TTL capped at 5 minutes).

use crate::error::{AgentError, Result};
use jsonwebtoken::{Algorithm, EncodingKey, Header};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// Claims embedded in a short-lived machine JWT authenticating this node
/// against the control plane's `headend` audience.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MachineJwtClaims {
    pub sub: String,
    pub aud: String,
    pub iss: String,
    pub iat: i64,
    pub exp: i64,
    pub node_type: String,
    pub scope: String,
}

/// Signs short-lived machine JWTs (JWS) for enrollment and authenticated
/// control-plane calls. Holds only an encoding key — this signer never
/// verifies incoming tokens, since verification is the control plane's job.
pub struct MachineJwtSigner {
    encoding_key: EncodingKey,
    algorithm: Algorithm,
}

impl MachineJwtSigner {
    /// Builds a signer from an already-loaded [`EncodingKey`] and
    /// [`Algorithm`] — the constructor of choice for tests and callers that
    /// manage key material themselves.
    pub fn new(encoding_key: EncodingKey, algorithm: Algorithm) -> Self {
        Self {
            encoding_key,
            algorithm,
        }
    }

    /// Loads an EC or RSA private key from a PEM file on disk and builds a
    /// signer using `algorithm`.
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
    pub fn from_pem_file(path: impl AsRef<Path>, algorithm: Algorithm) -> Result<Self> {
        let path = path.as_ref();
        check_key_permissions(path)?;
        let pem = std::fs::read(path)?;
        let encoding_key = EncodingKey::from_ec_pem(&pem)
            .or_else(|_| EncodingKey::from_rsa_pem(&pem))
            .map_err(AgentError::from)?;
        Ok(Self::new(encoding_key, algorithm))
    }

    /// Signs a new machine JWT for `node_id`/`node_type` with `scope`,
    /// valid for `ttl` from now. Callers should keep `ttl` at or below 5
    /// minutes per the short-lived-JWT policy.
    pub fn sign(
        &self,
        issuer: &str,
        node_id: &str,
        node_type: &str,
        scope: &str,
        ttl: Duration,
    ) -> Result<String> {
        let now = current_unix_time()?;
        let claims = MachineJwtClaims {
            sub: node_id.to_string(),
            aud: "headend".to_string(),
            iss: issuer.to_string(),
            iat: now,
            exp: now + ttl.as_secs() as i64,
            node_type: node_type.to_string(),
            scope: scope.to_string(),
        };
        let header = Header::new(self.algorithm);
        Ok(jsonwebtoken::encode(&header, &claims, &self.encoding_key)?)
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
/// decisions, which always go through full signature + claim validation.
pub fn decode_unverified_claims<T: DeserializeOwned>(token: &str) -> Result<T> {
    Ok(jsonwebtoken::dangerous::insecure_decode::<T>(token)?.claims)
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
    use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};

    #[derive(Debug, Deserialize)]
    struct TenantOnly {
        #[serde(default)]
        tenant: String,
    }

    #[test]
    fn machine_jwt_round_trips_with_hmac() {
        let signer =
            MachineJwtSigner::new(EncodingKey::from_secret(b"test-secret"), Algorithm::HS256);
        let token = signer
            .sign(
                "node-agent-test",
                "node-123",
                "connectivity",
                "dns:config:read metrics:write",
                Duration::from_secs(60),
            )
            .expect("signing with a valid HMAC key must succeed");

        let mut validation = Validation::new(Algorithm::HS256);
        validation.set_audience(&["headend"]);
        let decoded = decode::<MachineJwtClaims>(
            &token,
            &DecodingKey::from_secret(b"test-secret"),
            &validation,
        )
        .expect("token signed above must verify against the same secret");

        assert_eq!(decoded.claims.sub, "node-123");
        assert_eq!(decoded.claims.aud, "headend");
        assert_eq!(decoded.claims.node_type, "connectivity");
        assert!(decoded.claims.exp > decoded.claims.iat);
    }

    #[test]
    fn decode_unverified_claims_reads_tenant_without_a_key() {
        let signer = MachineJwtSigner::new(
            EncodingKey::from_secret(b"another-secret"),
            Algorithm::HS256,
        );
        let token = signer
            .sign(
                "node-agent-test",
                "node-456",
                "netsvcs-edge",
                "dns:config:read",
                Duration::from_secs(30),
            )
            .expect("signing must succeed");

        // `tenant` isn't a MachineJwtClaims field, so this proves
        // decode_unverified_claims tolerates unknown/missing fields via
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
        // deliberately does not implement (it holds live key material via
        // `jsonwebtoken::EncodingKey`, which itself withholds `Debug` to
        // avoid ever formatting key bytes) — match instead.
        let err = match MachineJwtSigner::from_pem_file(&path, Algorithm::ES256) {
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

        let err = match MachineJwtSigner::from_pem_file(&path, Algorithm::ES256) {
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
