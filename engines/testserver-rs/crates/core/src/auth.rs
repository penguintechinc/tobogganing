//! Real JWT signature/claims verification, replacing the Go testserver's
//! opaque-hash-then-DB-lookup scheme
//! (`engines/testserver/internal/auth/auth.go`'s `hashString` +
//! `ValidateJWT(tokenHash)`) — the flagged security gap this migration
//! closes. A `Bearer <token>` credential is now cryptographically verified
//! against the platform's ES256 (EC P-256, asymmetric) public key — the
//! same algorithm `agents/node-agent`'s `MachineJwtSigner` signs with — with
//! no database round trip; the `ApiKey <key>` scheme is unchanged and still
//! resolved via `testserver-db`.
//!
//! Verification itself delegates to the shared [`penguin_aaa::Es256Verifier`]
//! (the `penguin-aaa` crate, `penguin-libs` repo) rather than a local
//! `jsonwebtoken`-based implementation. See that crate's root doc for the
//! full algorithm policy: the EC family (ES256/ES384/ES512/EdDSA) plus
//! RS256 as a verify-only legacy backup, hand-rolled JWS framing with zero
//! `rsa`-crate dependency — so RUSTSEC-2023-0071 (Marvin Attack, RustCrypto
//! `rsa` timing sidechannel) no longer reaches this workspace at all
//! (verify with `cargo tree | grep rsa`).

use crate::error::ApiError;
use std::sync::Arc;

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
    InvalidKey(#[from] penguin_aaa::AaaError),
}

/// JwtVerifier wraps the shared [`penguin_aaa::Es256Verifier`] with the
/// key-material load path and claims-to-[`AuthUser`] mapping this service
/// needs. Constructed once at startup from the platform auth service's
/// ES256 (EC P-256) public key (see `testserver_core::config`);
/// `AUTH_ENABLED=false` bypasses this entirely (see
/// `testserver::http_api::auth_middleware`).
///
/// Held behind an `Arc` because `penguin_aaa::Es256Verifier` itself isn't
/// `Clone` (it owns raw key bytes / a `p521` verifying key, neither of
/// which derive `Clone`), while `AppConfig`/`AppState` — which embed this —
/// are cloned per Axum request.
#[derive(Clone)]
pub struct JwtVerifier {
    inner: Arc<penguin_aaa::Es256Verifier>,
}

// `penguin_aaa::Es256Verifier` already has its own key-material-free
// `Debug` impl (`finish_non_exhaustive`); this wrapper keeps that guarantee
// explicit at its own layer too rather than relying on it transitively
// through `Arc`.
impl std::fmt::Debug for JwtVerifier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("JwtVerifier").finish_non_exhaustive()
    }
}

impl JwtVerifier {
    /// Builds an ES256 verifier from an EC P-256 public key in PEM
    /// (`-----BEGIN PUBLIC KEY-----`, SPKI/DER) format, via
    /// [`penguin_aaa::Es256Verifier::from_public_key_pem`]. No audience or
    /// issuer is pinned — this service has never required a specific
    /// `aud`/`iss`, and this migration doesn't change that.
    ///
    /// `penguin_aaa` derives the accepted algorithm from the key's own
    /// type, never from a caller-supplied `Algorithm` enum, so a token
    /// signed HS256 — including the classic alg-confusion attack that
    /// reuses this public key as an HMAC secret — or one claiming
    /// `alg: none` is rejected before signature verification ever runs.
    pub fn new_es256(public_key_pem: &[u8]) -> Result<Self, JwtKeyError> {
        let inner = penguin_aaa::Es256Verifier::from_public_key_pem(public_key_pem)?;
        Ok(Self {
            inner: Arc::new(inner),
        })
    }

    /// Verifies signature, required claims, and expiration via
    /// [`penguin_aaa::Es256Verifier::verify`], returning the sanitized
    /// identity. Any failure (bad signature, wrong/unsupported algorithm,
    /// expired, malformed, missing required claim) collapses to the same
    /// `ApiError::InvalidCredentials` — never leaking which check failed
    /// to the caller, only to the (sanitized) debug log.
    pub fn verify(&self, token: &str) -> Result<AuthUser, ApiError> {
        let claims = self.inner.verify(token).map_err(|e| {
            tracing::debug!(error = %e, "jwt verification failed");
            ApiError::InvalidCredentials
        })?;
        Ok(AuthUser {
            id: claims.sub,
            tenant: claims.tenant,
            // `penguin_aaa::Claims::scope` is a required, possibly-empty
            // `String` (never absent); this service's `AuthUser` keeps the
            // pre-migration `Option<String>` shape for its callers, so an
            // empty scope collapses to `None` rather than `Some("")`.
            scope: (!claims.scope.is_empty()).then_some(claims.scope),
            roles: claims.roles,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hmac::{Hmac, Mac};
    use p256::ecdsa::signature::Signer as _;
    use p256::ecdsa::{Signature, SigningKey, VerifyingKey};
    use p256::pkcs8::{DecodePrivateKey, EncodePrivateKey, EncodePublicKey, LineEnding};
    use penguin_aaa::{Claims, Es256Signer};
    use sha2::Sha256;

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

    fn now() -> i64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64
    }

    /// Builds a structurally-complete claim set — `penguin_aaa::Claims`
    /// requires `sub`/`iss`/`aud`/`iat`/`exp`/`scope`, unlike this crate's
    /// pre-migration inline `Claims` (which only required `sub`/`exp`).
    fn build_claims(
        sub: &str,
        tenant: Option<&str>,
        scope: &str,
        roles: Vec<String>,
        exp: i64,
    ) -> Claims {
        Claims {
            sub: sub.to_string(),
            iss: "testserver-test".to_string(),
            aud: "testserver".to_string(),
            iat: now(),
            exp,
            scope: scope.to_string(),
            tenant: tenant.map(str::to_string),
            teams: Vec::new(),
            roles,
        }
    }

    /// Signs `claims` via [`Es256Signer`] — the same primitive the
    /// platform auth service and `agents/node-agent`'s `MachineJwtSigner`
    /// use in production.
    fn sign_valid(private_pem: &str, claims: &Claims) -> String {
        Es256Signer::from_ec_pem(private_pem.as_bytes())
            .expect("a freshly generated EC PEM must load as a signing key")
            .sign(claims)
            .expect("signing a well-formed claim set must succeed")
    }

    /// Hand-signs a raw ES256 token from `header_json`/`payload_json`
    /// bytes, bypassing [`Es256Signer`]/[`Claims`] so a claim set `Claims`
    /// itself couldn't represent (e.g. missing `sub`) can still be
    /// constructed for a rejection test.
    fn sign_raw_es256(private_pem: &str, header_json: &str, payload_json: &str) -> String {
        let signing_key = SigningKey::from_pkcs8_pem(private_pem)
            .expect("a freshly generated PKCS#8 EC key must load");
        let signing_input = format!(
            "{}.{}",
            b64url(header_json.as_bytes()),
            b64url(payload_json.as_bytes())
        );
        let signature: Signature = signing_key.sign(signing_input.as_bytes());
        format!("{signing_input}.{}", b64url(&signature.to_bytes()))
    }

    /// Forges an HS256-labeled token, HMAC-SHA256-signed with `secret` —
    /// used only to prove [`JwtVerifier`] rejects it (alg-confusion guard).
    fn forge_hs256(secret: &[u8], header_json: &str, payload_json: &str) -> String {
        let signing_input = format!(
            "{}.{}",
            b64url(header_json.as_bytes()),
            b64url(payload_json.as_bytes())
        );
        let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(secret)
            .expect("HMAC-SHA256 accepts a key of any length");
        mac.update(signing_input.as_bytes());
        let tag = mac.finalize().into_bytes();
        format!("{signing_input}.{}", b64url(&tag))
    }

    #[test]
    fn verify_accepts_valid_es256_signature_and_claims() {
        let (private_pem, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        let claims = build_claims(
            "user-123",
            Some("acme"),
            "test:run",
            vec!["viewer".to_string()],
            now() + 3600,
        );
        let token = sign_valid(&private_pem, &claims);

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
        let claims = build_claims("user-123", None, "test:run", vec![], now() + 3600);
        let token = sign_valid(&attacker_private_pem, &claims);

        let verifier = JwtVerifier::new_es256(real_public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        assert!(verifier.verify(&token).is_err());
    }

    #[test]
    fn verify_rejects_expired_token() {
        let (private_pem, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        let claims = build_claims("user-123", None, "test:run", vec![], 1);
        let token = sign_valid(&private_pem, &claims);

        assert!(verifier.verify(&token).is_err());
    }

    #[test]
    fn verify_rejects_missing_required_claim() {
        let (private_pem, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");
        // Missing `sub` — hand-built payload, since `penguin_aaa::Claims`
        // can't itself construct an invalid claim set. `sub` is structurally
        // required, so this fails to deserialize before any signature or
        // expiration check even runs.
        let token = sign_raw_es256(
            &private_pem,
            r#"{"alg":"ES256","typ":"JWT"}"#,
            &format!(
                r#"{{"iss":"x","aud":"y","iat":{},"exp":{},"scope":"test:run"}}"#,
                now(),
                now() + 3600
            ),
        );

        assert!(verifier.verify(&token).is_err());
    }

    /// Alg-confusion guard: a token signed HS256 using this verifier's own
    /// ES256 *public* key bytes as the HMAC secret (the textbook
    /// asymmetric→HS256 confusion attack — a public key is not secret, so
    /// anyone who can see it could forge an HS256-signed token if the
    /// verifier ever accepted HS256) must be rejected — `Es256Verifier` has
    /// no HS256 code path at all; the forged token is rejected by its
    /// explicit `alg` check before the signature segment is ever
    /// interpreted.
    #[test]
    fn verify_rejects_hs256_alg_confusion_token() {
        let (_, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");

        let forged = forge_hs256(
            public_pem.as_bytes(),
            r#"{"alg":"HS256","typ":"JWT"}"#,
            &format!(
                r#"{{"sub":"attacker","iss":"x","aud":"y","iat":{},"exp":{},"scope":"admin:*"}}"#,
                now(),
                now() + 3600
            ),
        );

        assert!(verifier.verify(&forged).is_err());
    }

    /// Alg-confusion guard: a token that declares `alg: none` and carries no
    /// signature must be rejected — caught by `Es256Verifier`'s explicit
    /// `alg` check before any signature parsing is attempted.
    #[test]
    fn verify_rejects_alg_none_token() {
        let (_, public_pem) = generate_test_keypair();
        let verifier = JwtVerifier::new_es256(public_pem.as_bytes())
            .expect("a freshly generated EC public key must build a verifier");

        let header = b64url(br#"{"alg":"none","typ":"JWT"}"#);
        let payload = b64url(
            format!(
                r#"{{"sub":"attacker","iss":"x","aud":"y","iat":{},"exp":{},"scope":"admin:*"}}"#,
                now(),
                now() + 3600
            )
            .as_bytes(),
        );
        let forged = format!("{header}.{payload}.");

        assert!(verifier.verify(&forged).is_err());
    }

    /// Minimal unpadded base64url encoder for the hand-forged tokens above
    /// — deliberately hand-rolled instead of pulling in a `base64`
    /// dependency just to construct a few malformed/forged test tokens.
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
