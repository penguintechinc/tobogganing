//! Real JWT signature/claims verification, replacing the Go testserver's
//! opaque-hash-then-DB-lookup scheme
//! (`engines/testserver/internal/auth/auth.go`'s `hashString` +
//! `ValidateJWT(tokenHash)`) — the flagged security gap this migration
//! closes. A `Bearer <token>` credential is now cryptographically verified
//! against the platform's ES256 (EC P-256, asymmetric) public key — the
//! same algorithm `agents/node-agent`'s `MachineJwtSigner` signs with — with
//! no database round trip; the `ApiKey <key>` scheme is unchanged and still
//! resolved via `testserver-db`.

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

/// Failure building a [`JwtVerifier`] from key material — always a
/// startup/configuration failure (bad PEM), never a per-request outcome;
/// compare [`ApiError`], which is per-request only.
#[derive(Debug, thiserror::Error)]
pub enum JwtKeyError {
    #[error("invalid ES256 public key PEM: {0}")]
    InvalidKey(#[from] jsonwebtoken::errors::Error),
}

/// JwtVerifier owns the decoding key + validation policy for Bearer tokens.
/// Constructed once at startup from the platform auth service's ES256 (EC
/// P-256) public key (see `testserver_core::config`); `AUTH_ENABLED=false`
/// bypasses this entirely (see `testserver::http_api::auth_middleware`).
#[derive(Clone)]
pub struct JwtVerifier {
    decoding_key: DecodingKey,
    validation: Validation,
}

// `DecodingKey`/`Validation` don't derive `Debug`, and there's no key
// material here worth hiding anyway (this is a *public* key) — a minimal
// manual impl lets `AppConfig` (which embeds this) keep deriving `Debug`
// without leaking internals that aren't `Debug` themselves.
impl std::fmt::Debug for JwtVerifier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("JwtVerifier").finish_non_exhaustive()
    }
}

impl JwtVerifier {
    /// Builds an ES256 verifier from an EC P-256 public key in PEM
    /// (`-----BEGIN PUBLIC KEY-----`, SPKI/DER) format. ES256 is the
    /// platform standard (security.md JWT Claims) — asymmetric, so
    /// testserver only ever needs the *public* half of the auth service's
    /// signing keypair, never a shared secret it would have to protect as
    /// tightly as a private key.
    ///
    /// `validation.algorithms` is pinned to `[ES256]` only, so a token
    /// signed HS256 — including the classic alg-confusion attack that
    /// reuses this public key as an HMAC secret — or one claiming
    /// `alg: none` is rejected before signature verification ever runs;
    /// `jsonwebtoken::Algorithm` has no `none` variant at all, so an
    /// `alg: none` header fails to even parse.
    pub fn new_es256(public_key_pem: &[u8]) -> Result<Self, JwtKeyError> {
        let decoding_key = DecodingKey::from_ec_pem(public_key_pem)?;
        let mut validation = Validation::new(Algorithm::ES256);
        validation.validate_exp = true;
        validation.algorithms = vec![Algorithm::ES256];
        // Every mandatory claim from security.md JWT Claims must be present;
        // this crate additionally requires `sub`/`exp` structurally via the
        // Claims struct (a missing required field fails deserialization).
        validation.required_spec_claims = ["exp", "sub"].into_iter().map(String::from).collect();
        Ok(Self {
            decoding_key,
            validation,
        })
    }

    /// Verifies signature + expiration and returns the sanitized identity.
    /// Any failure (bad signature, wrong/unsupported algorithm, expired,
    /// malformed) collapses to the same `ApiError::InvalidCredentials` —
    /// never leaking which check failed to the caller, only to the
    /// (sanitized) debug log.
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
    use p256::ecdsa::{SigningKey, VerifyingKey};
    use p256::pkcs8::{EncodePrivateKey, EncodePublicKey, LineEnding};
    use serde_json::json;

    /// Generates a fresh, throwaway EC P-256 keypair as PKCS#8/SPKI PEM —
    /// generated at test time, never a fixed/committed key, so nothing
    /// resembling real key material ever lands in source control (mirrors
    /// `agents/node-agent`'s `generate_test_ec_key_pem`).
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

    fn sign_es256(private_pem: &str, claims: serde_json::Value) -> String {
        encode(
            &Header::new(Algorithm::ES256),
            &claims,
            &EncodingKey::from_ec_pem(private_pem.as_bytes())
                .expect("a freshly generated EC PEM must load as a signing key"),
        )
        .expect("signing a well-formed claim set must succeed")
    }

    fn now_plus(secs: u64) -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
            + secs
    }

    #[test]
    fn verify_accepts_valid_es256_signature_and_claims() {
        let (private_pem, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        let token = sign_es256(
            &private_pem,
            json!({"sub": "user-123", "tenant": "acme", "scope": "test:run", "roles": ["viewer"], "exp": now_plus(3600)}),
        );

        let user = verifier.verify(&token).expect("valid token must verify");
        assert_eq!(user.id, "user-123");
        assert_eq!(user.tenant.as_deref(), Some("acme"));
        assert_eq!(user.scope.as_deref(), Some("test:run"));
        assert_eq!(user.roles, vec!["viewer".to_string()]);
    }

    #[test]
    fn verify_rejects_wrong_key() {
        let (attacker_private_pem, _) = generate_test_keypair();
        let (_, real_public_pem) = generate_test_keypair();
        let token = sign_es256(
            &attacker_private_pem,
            json!({"sub": "user-123", "exp": now_plus(3600)}),
        );

        let verifier = JwtVerifier::new_es256(real_public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        assert!(verifier.verify(&token).is_err());
    }

    #[test]
    fn verify_rejects_expired_token() {
        let (private_pem, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        let token = sign_es256(&private_pem, json!({"sub": "user-123", "exp": 1}));

        assert!(verifier.verify(&token).is_err());
    }

    #[test]
    fn verify_rejects_missing_required_claim() {
        let (private_pem, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        // Missing `sub`.
        let token = sign_es256(&private_pem, json!({"exp": now_plus(3600)}));

        assert!(verifier.verify(&token).is_err());
    }

    /// Alg-confusion guard: a token signed HS256 using this verifier's own
    /// ES256 *public* key bytes as the HMAC secret (the textbook
    /// asymmetric→HS256 confusion attack — a public key is not secret, so
    /// anyone who can see it could forge an HS256-signed token if the
    /// verifier ever accepted HS256) must be rejected, because
    /// `Validation::algorithms` is pinned to `[ES256]` only.
    #[test]
    fn verify_rejects_hs256_alg_confusion_token() {
        let (_, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");

        let forged = encode(
            &Header::new(Algorithm::HS256),
            &json!({"sub": "attacker", "exp": now_plus(3600)}),
            &EncodingKey::from_secret(public_pem.as_bytes()),
        )
        .expect("signing an HS256 token must succeed");

        assert!(verifier.verify(&forged).is_err());
    }

    /// Alg-confusion guard: a token that declares `alg: none` and carries no
    /// signature must be rejected. `jsonwebtoken::Algorithm` has no `none`
    /// variant, so this fails to parse before any claim/signature check
    /// runs — asserted here so a future jsonwebtoken upgrade that changed
    /// that behavior would be caught immediately.
    #[test]
    fn verify_rejects_alg_none_token() {
        let (_, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");

        let header = b64url(br#"{"alg":"none","typ":"JWT"}"#);
        let payload =
            b64url(format!(r#"{{"sub":"attacker","exp":{}}}"#, now_plus(3600)).as_bytes());
        let forged = format!("{header}.{payload}.");

        assert!(verifier.verify(&forged).is_err());
    }

    /// Minimal unpadded base64url encoder for the single `alg: none` test
    /// above — deliberately hand-rolled instead of pulling in a `base64`
    /// dependency just to construct one malformed test token.
    fn b64url(input: &[u8]) -> String {
        const ALPHABET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
        let mut out = String::new();
        for chunk in input.chunks(3) {
            let b0 = chunk[0];
            let b1 = chunk.get(1).copied().unwrap_or(0);
            let b2 = chunk.get(2).copied().unwrap_or(0);
            let n = ((b0 as u32) << 16) | ((b1 as u32) << 8) | (b2 as u32);
            out.push(ALPHABET[((n >> 18) & 0x3F) as usize] as char);
            out.push(ALPHABET[((n >> 12) & 0x3F) as usize] as char);
            if chunk.len() > 1 {
                out.push(ALPHABET[((n >> 6) & 0x3F) as usize] as char);
            }
            if chunk.len() > 2 {
                out.push(ALPHABET[(n & 0x3F) as usize] as char);
            }
        }
        out
    }
}
