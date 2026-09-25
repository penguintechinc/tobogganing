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

    /// Loads an EC or RSA private key from a PEM file on disk (expected
    /// mode `0600` per the credential-hygiene policy) and builds a signer
    /// using `algorithm`.
    pub fn from_pem_file(path: impl AsRef<Path>, algorithm: Algorithm) -> Result<Self> {
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
}
