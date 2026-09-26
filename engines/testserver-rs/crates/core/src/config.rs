//! Environment-driven configuration, matching the Go testserver's env var
//! names 1:1 (`DB_TYPE`/`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS`/`DB_NAME`,
//! `AUTH_ENABLED`, `PORT`, `MAX_CONCURRENT_TESTS`,
//! `TESTSERVER_ALLOWED_ORIGINS`) plus new Rust-only knobs (`GRPC_PORT`,
//! `METRICS_PORT`, `TESTSERVER_JWT_PUBLIC_KEY`/
//! `TESTSERVER_JWT_PUBLIC_KEY_PATH`).

use crate::auth::{JwtKeyError, JwtVerifier};
use std::collections::HashSet;

/// DbType selects the SQL dialect `testserver-db` connects to. PostgreSQL is
/// the platform default (see hub_api/config); MySQL/MariaDB is the
/// production alternative; SQLite is development-tier only.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DbType {
    PostgreSql,
    MySql,
    Sqlite,
}

impl DbType {
    fn from_env_str(raw: &str) -> Self {
        match raw {
            "mysql" => DbType::MySql,
            "sqlite" => DbType::Sqlite,
            // Matches the Go dialectorFor's `case DBTypePostgreSQL, "":` —
            // postgres is the default for any unset/unrecognized value.
            _ => DbType::PostgreSql,
        }
    }
}

/// DbConfig carries DB_TYPE-selected connection parameters.
#[derive(Debug, Clone)]
pub struct DbConfig {
    pub db_type: DbType,
    pub host: String,
    pub port: String,
    pub user: String,
    pub password: String,
    pub database: String,
}

/// Failure loading [`AppConfig`] — always fatal at startup. Auth is a
/// security control, not a feature: a missing or unparseable JWT public key
/// while `AUTH_ENABLED=true` must stop the process, never fall back to
/// starting up with auth silently unenforceable (client.md Feature Flags &
/// License Validation's "never crash" rule is about feature gating, not
/// about security-control fail-open — this is the opposite case).
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error(
        "AUTH_ENABLED=true but no JWT public key is configured — set \
         TESTSERVER_JWT_PUBLIC_KEY_PATH or TESTSERVER_JWT_PUBLIC_KEY; refusing to start with \
         auth silently unenforceable"
    )]
    MissingJwtPublicKey,

    #[error("failed to read TESTSERVER_JWT_PUBLIC_KEY_PATH={path}: {source}")]
    JwtPublicKeyRead {
        path: String,
        #[source]
        source: std::io::Error,
    },

    #[error("invalid JWT public key: {0}")]
    JwtPublicKey(#[from] JwtKeyError),
}

/// AppConfig is the fully-resolved runtime configuration, loaded once at
/// startup via [`AppConfig::from_env`]. Loading is fallible: see
/// [`ConfigError`].
#[derive(Debug, Clone)]
pub struct AppConfig {
    pub db: DbConfig,
    pub auth_enabled: bool,
    pub http_port: u16,
    pub grpc_port: u16,
    pub metrics_port: u16,
    /// TODO(follow-up PR): parsed but not yet enforced — the Go
    /// implementation also left this dead (see main.go's `maxConcurrent`
    /// variable, read but never wired to a semaphore). Wiring a
    /// `tokio::sync::Semaphore` bound to this value is deferred to the PR
    /// that ports ICMP/traceroute (the expensive shell-out probes this cap
    /// is meant to protect against).
    pub max_concurrent_tests: usize,
    /// Config-driven CORS allowlist — unset/empty means deny-all, never a
    /// wildcard fallback (mirrors main.go's `parseAllowedOrigins`).
    pub allowed_origins: HashSet<String>,
    /// ES256 verifier built from the platform auth service's EC P-256
    /// public key (`TESTSERVER_JWT_PUBLIC_KEY`/
    /// `TESTSERVER_JWT_PUBLIC_KEY_PATH`) — never a shared secret (see
    /// security.md JWT Claims; mirrors `agents/node-agent`'s asymmetric
    /// `MachineJwtSigner`). `None` only when `auth_enabled` is false:
    /// [`AppConfig::from_env`] fails closed otherwise, so a running server
    /// with `auth_enabled == true` always has `Some` here.
    pub jwt_verifier: Option<JwtVerifier>,
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key)
        .ok()
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn parse_allowed_origins(raw: &str) -> HashSet<String> {
    raw.split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .collect()
}

/// Reads the ES256 public key PEM from `TESTSERVER_JWT_PUBLIC_KEY` (inline)
/// or `TESTSERVER_JWT_PUBLIC_KEY_PATH` (file) — inline takes precedence.
/// Returns `Ok(None)` when neither is set; whether that's fatal is decided
/// by [`resolve_jwt_verifier`], based on `auth_enabled`.
fn load_jwt_public_key_pem() -> Result<Option<Vec<u8>>, ConfigError> {
    if let Some(inline) = std::env::var("TESTSERVER_JWT_PUBLIC_KEY")
        .ok()
        .filter(|v| !v.trim().is_empty())
    {
        return Ok(Some(inline.into_bytes()));
    }
    if let Some(path) = std::env::var("TESTSERVER_JWT_PUBLIC_KEY_PATH")
        .ok()
        .filter(|v| !v.trim().is_empty())
    {
        let bytes = std::fs::read(&path).map_err(|source| ConfigError::JwtPublicKeyRead {
            path: path.clone(),
            source,
        })?;
        return Ok(Some(bytes));
    }
    Ok(None)
}

/// Resolves `pem` + `auth_enabled` into the verifier `AppConfig` carries.
/// Deliberately pure/no I/O (unlike [`load_jwt_public_key_pem`]) so the
/// fail-closed policy is unit-testable without mutating process
/// environment — env vars are process-global mutable state and races
/// across parallel test threads.
fn resolve_jwt_verifier(
    auth_enabled: bool,
    pem: Option<Vec<u8>>,
) -> Result<Option<JwtVerifier>, ConfigError> {
    match pem {
        Some(bytes) => Ok(Some(JwtVerifier::new_es256(&bytes)?)),
        None if auth_enabled => Err(ConfigError::MissingJwtPublicKey),
        None => Ok(None),
    }
}

impl AppConfig {
    pub fn from_env() -> Result<Self, ConfigError> {
        let db = DbConfig {
            db_type: DbType::from_env_str(&env_or("DB_TYPE", "postgresql")),
            host: env_or("DB_HOST", "localhost"),
            port: env_or("DB_PORT", "5432"),
            user: env_or("DB_USER", "testserver"),
            password: env_or("DB_PASS", ""),
            database: env_or("DB_NAME", "testserver"),
        };

        let auth_enabled = env_or("AUTH_ENABLED", "true") == "true";
        let pem = load_jwt_public_key_pem()?;
        let jwt_verifier = resolve_jwt_verifier(auth_enabled, pem)?;

        Ok(Self {
            db,
            auth_enabled,
            http_port: env_or("PORT", "8080").parse().unwrap_or(8080),
            grpc_port: env_or("GRPC_PORT", "50051").parse().unwrap_or(50051),
            metrics_port: env_or("METRICS_PORT", "9090").parse().unwrap_or(9090),
            max_concurrent_tests: env_or("MAX_CONCURRENT_TESTS", "100").parse().unwrap_or(100),
            allowed_origins: parse_allowed_origins(&env_or("TESTSERVER_ALLOWED_ORIGINS", "")),
            jwt_verifier,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_allowed_origins_empty_is_deny_all() {
        assert!(parse_allowed_origins("").is_empty());
        assert!(parse_allowed_origins("   ").is_empty());
    }

    #[test]
    fn parse_allowed_origins_trims_and_splits() {
        let set = parse_allowed_origins("https://a.example, https://b.example ,,");
        assert_eq!(set.len(), 2);
        assert!(set.contains("https://a.example"));
        assert!(set.contains("https://b.example"));
    }

    #[test]
    fn db_type_defaults_to_postgres() {
        assert_eq!(DbType::from_env_str(""), DbType::PostgreSql);
        assert_eq!(DbType::from_env_str("postgresql"), DbType::PostgreSql);
        assert_eq!(DbType::from_env_str("unknown"), DbType::PostgreSql);
        assert_eq!(DbType::from_env_str("mysql"), DbType::MySql);
        assert_eq!(DbType::from_env_str("sqlite"), DbType::Sqlite);
    }

    fn generate_test_public_key_pem() -> String {
        use p256::ecdsa::{SigningKey, VerifyingKey};
        use p256::pkcs8::{EncodePublicKey, LineEnding};
        let signing_key = SigningKey::random(&mut rand_core::OsRng);
        VerifyingKey::from(&signing_key)
            .to_public_key_pem(LineEnding::LF)
            .expect("encoding a freshly generated P-256 public key as SPKI PEM must succeed")
    }

    #[test]
    fn resolve_jwt_verifier_fails_closed_when_auth_enabled_and_no_key() {
        let err = resolve_jwt_verifier(true, None).expect_err("must fail closed");
        assert!(matches!(err, ConfigError::MissingJwtPublicKey));
    }

    #[test]
    fn resolve_jwt_verifier_allows_no_key_when_auth_disabled() {
        assert!(resolve_jwt_verifier(false, None)
            .expect("auth disabled must not require a key")
            .is_none());
    }

    #[test]
    fn resolve_jwt_verifier_rejects_invalid_pem() {
        let err = resolve_jwt_verifier(true, Some(b"not a real key".to_vec()))
            .expect_err("malformed PEM must be rejected");
        assert!(matches!(err, ConfigError::JwtPublicKey(_)));
    }

    #[test]
    fn resolve_jwt_verifier_builds_a_verifier_from_a_valid_key() {
        let pem = generate_test_public_key_pem();
        let verifier = resolve_jwt_verifier(true, Some(pem.into_bytes()))
            .expect("a freshly generated EC public key must be accepted");
        assert!(verifier.is_some());
    }
}
