//! Real JWT signature/claims verification, replacing the Go testserver's
//! opaque-hash-then-DB-lookup scheme
//! (`engines/testserver/internal/auth/auth.go`'s `hashString` +
//! `ValidateJWT(tokenHash)`) — the flagged security gap this migration
//! closes. A `Bearer <token>` credential is now cryptographically verified
//! (HS256 signature + `exp`) with no database round trip; the `ApiKey
//! <key>` scheme is unchanged and still resolved via `testserver-db`.

use crate::error::ApiError;
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::Deserialize;

/// JWT claims this service requires — matches the platform's mandatory
/// claim set (security.md JWT Claims): `sub`, `exp`, plus `tenant`/`scope`/
/// `roles` where present. `roles` is audit/display only; no authz decision
/// in this crate branches on it.
#[derive(Debug, Clone, Deserialize)]
struct Claims {
    sub: String,
    #[serde(default)]
    tenant: Option<String>,
    #[serde(default)]
    scope: Option<String>,
    #[serde(default)]
    roles: Vec<String>,
    #[allow(dead_code)] // required by jsonwebtoken's exp validation, never read directly
    exp: usize,
}

/// AuthUser is the sanitized, request-scoped identity extracted from a
/// verified credential — never the raw DB row or raw JWT claims (see
/// security.md Output Validation: responses/derived state are always an
/// explicit DTO, not a passthrough of the underlying model).
#[derive(Debug, Clone)]
pub struct AuthUser {
    pub id: String,
    pub tenant: Option<String>,
    pub scope: Option<String>,
    pub roles: Vec<String>,
}

/// JwtVerifier owns the decoding key + validation policy for Bearer tokens.
/// Constructed once at startup from `JWT_SECRET`; `AUTH_ENABLED=false`
/// bypasses this entirely (see `testserver::http_api::auth_middleware`).
#[derive(Clone)]
pub struct JwtVerifier {
    decoding_key: DecodingKey,
    validation: Validation,
}

impl JwtVerifier {
    /// Builds an HS256 verifier. HS256 (shared-secret) matches this
    /// service's trust model: testserver and the issuing hub-api share one
    /// cluster-internal secret (`JWT_SECRET`), delivered via K8s Secret —
    /// never a public/private keypair, since there's no cross-org
    /// federation need here.
    pub fn new_hs256(secret: &[u8]) -> Self {
        let mut validation = Validation::new(Algorithm::HS256);
        validation.validate_exp = true;
        // Every mandatory claim from security.md JWT Claims must be present;
        // this crate additionally requires `sub`/`exp` structurally via the
        // Claims struct (a missing required field fails deserialization).
        validation.required_spec_claims = ["exp", "sub"].into_iter().map(String::from).collect();
        Self {
            decoding_key: DecodingKey::from_secret(secret),
            validation,
        }
    }

    /// Verifies signature + expiration and returns the sanitized identity.
    /// Any failure (bad signature, expired, malformed) collapses to the
    /// same `ApiError::InvalidCredentials` — never leaking which check
    /// failed to the caller, only to the (sanitized) debug log.
    pub fn verify(&self, token: &str) -> Result<AuthUser, ApiError> {
        let data = decode::<Claims>(token, &self.decoding_key, &self.validation).map_err(|e| {
            tracing::debug!(error = %e, "jwt verification failed");
            ApiError::InvalidCredentials
        })?;
        Ok(AuthUser {
            id: data.claims.sub,
            tenant: data.claims.tenant,
            scope: data.claims.scope,
            roles: data.claims.roles,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use jsonwebtoken::{encode, EncodingKey, Header};
    use serde_json::json;

    fn sign(secret: &[u8], claims: serde_json::Value) -> String {
        encode(
            &Header::new(Algorithm::HS256),
            &claims,
            &EncodingKey::from_secret(secret),
        )
        .expect("signing a well-formed claim set must succeed")
    }

    #[test]
    fn verify_accepts_valid_signature_and_claims() {
        let secret = b"test-secret";
        let verifier = JwtVerifier::new_hs256(secret);
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let token = sign(
            secret,
            json!({"sub": "user-123", "tenant": "acme", "scope": "test:run", "roles": ["viewer"], "exp": now + 3600}),
        );

        let user = verifier.verify(&token).expect("valid token must verify");
        assert_eq!(user.id, "user-123");
        assert_eq!(user.tenant.as_deref(), Some("acme"));
        assert_eq!(user.scope.as_deref(), Some("test:run"));
        assert_eq!(user.roles, vec!["viewer".to_string()]);
    }

    #[test]
    fn verify_rejects_wrong_secret() {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        let token = sign(
            b"attacker-secret",
            json!({"sub": "user-123", "exp": now + 3600}),
        );

        let verifier = JwtVerifier::new_hs256(b"real-secret");
        assert!(verifier.verify(&token).is_err());
    }

    #[test]
    fn verify_rejects_expired_token() {
        let secret = b"test-secret";
        let verifier = JwtVerifier::new_hs256(secret);
        let token = sign(secret, json!({"sub": "user-123", "exp": 1}));

        assert!(verifier.verify(&token).is_err());
    }

    #[test]
    fn verify_rejects_missing_required_claim() {
        let secret = b"test-secret";
        let verifier = JwtVerifier::new_hs256(secret);
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        // Missing `sub`.
        let token = sign(secret, json!({"exp": now + 3600}));

        assert!(verifier.verify(&token).is_err());
    }
}
