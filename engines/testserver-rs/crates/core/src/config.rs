//! Environment-driven configuration, matching the Go testserver's env var
//! names 1:1 (`DB_TYPE`/`DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASS`/`DB_NAME`,
//! `AUTH_ENABLED`, `PORT`, `MAX_CONCURRENT_TESTS`,
//! `TESTSERVER_ALLOWED_ORIGINS`) plus new Rust-only knobs (`GRPC_PORT`,
//! `METRICS_PORT`, `JWT_SECRET`).

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

/// AppConfig is the fully-resolved runtime configuration, loaded once at
/// startup via [`AppConfig::from_env`].
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
    /// HMAC secret for HS256 JWT verification. `None` with `auth_enabled`
    /// true means every Bearer-token request is rejected (fail closed,
    /// never fall back to "accept any token").
    pub jwt_secret: Option<String>,
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

impl AppConfig {
    pub fn from_env() -> Self {
        let db = DbConfig {
            db_type: DbType::from_env_str(&env_or("DB_TYPE", "postgresql")),
            host: env_or("DB_HOST", "localhost"),
            port: env_or("DB_PORT", "5432"),
            user: env_or("DB_USER", "testserver"),
            password: env_or("DB_PASS", ""),
            database: env_or("DB_NAME", "testserver"),
        };

        Self {
            db,
            auth_enabled: env_or("AUTH_ENABLED", "true") == "true",
            http_port: env_or("PORT", "8080").parse().unwrap_or(8080),
            grpc_port: env_or("GRPC_PORT", "50051").parse().unwrap_or(50051),
            metrics_port: env_or("METRICS_PORT", "9090").parse().unwrap_or(9090),
            max_concurrent_tests: env_or("MAX_CONCURRENT_TESTS", "100").parse().unwrap_or(100),
            allowed_origins: parse_allowed_origins(&env_or("TESTSERVER_ALLOWED_ORIGINS", "")),
            jwt_secret: std::env::var("JWT_SECRET").ok().filter(|v| !v.is_empty()),
        }
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
}
