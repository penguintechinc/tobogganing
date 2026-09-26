//! Connection dialing with retry+backoff, matching Go's `database.New()`
//! defaults (5 attempts, 5s backoff) and its "never crash the process"
//! contract — a permanently unreachable database is the caller's problem
//! to degrade around (`SwitchableStore`), not a reason to exit.

use sea_orm::{ConnectOptions, Database, DatabaseConnection, DbErr};
use std::time::Duration;
use testserver_core::{DbConfig, DbType};

pub const DEFAULT_MAX_RETRIES: u32 = 5;
pub const DEFAULT_RETRY_DELAY: Duration = Duration::from_secs(5);

fn dsn_for(cfg: &DbConfig) -> String {
    match cfg.db_type {
        DbType::MySql => format!(
            "mysql://{}:{}@{}:{}/{}",
            cfg.user, cfg.password, cfg.host, cfg.port, cfg.database
        ),
        DbType::Sqlite => {
            if cfg.database.is_empty() {
                "sqlite::memory:".to_string()
            } else {
                format!("sqlite://{}?mode=rwc", cfg.database)
            }
        }
        DbType::PostgreSql => format!(
            "postgres://{}:{}@{}:{}/{}",
            cfg.user, cfg.password, cfg.host, cfg.port, cfg.database
        ),
    }
}

/// Dials the database selected by `cfg.db_type` with retry+backoff. Never
/// panics or exits the process on failure — the caller (main.rs) spawns
/// this in the background and swaps the result into `SwitchableStore`,
/// exactly like the Go implementation's `connectDB` goroutine.
pub async fn connect_with_retry(
    cfg: &DbConfig,
    max_retries: u32,
    retry_delay: Duration,
) -> Result<DatabaseConnection, DbErr> {
    let dsn = dsn_for(cfg);
    let mut opts = ConnectOptions::new(dsn);
    opts.max_connections(100).min_connections(1);

    let attempts = max_retries.max(1);
    let mut last_err = None;
    for attempt in 1..=attempts {
        match Database::connect(opts.clone()).await {
            Ok(conn) => return Ok(conn),
            Err(e) => {
                tracing::warn!(
                    attempt,
                    max_retries = attempts,
                    error = %e,
                    "database connection attempt failed"
                );
                last_err = Some(e);
                if attempt < attempts {
                    tokio::time::sleep(retry_delay).await;
                }
            }
        }
    }
    Err(last_err.expect("loop runs at least once, so last_err is always populated on failure"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dsn_for_postgres() {
        let cfg = DbConfig {
            db_type: DbType::PostgreSql,
            host: "db".into(),
            port: "5432".into(),
            user: "u".into(),
            password: "p".into(),
            database: "testserver".into(),
        };
        assert_eq!(dsn_for(&cfg), "postgres://u:p@db:5432/testserver");
    }

    #[test]
    fn dsn_for_sqlite_defaults_to_in_memory() {
        let cfg = DbConfig {
            db_type: DbType::Sqlite,
            host: String::new(),
            port: String::new(),
            user: String::new(),
            password: String::new(),
            database: String::new(),
        };
        assert_eq!(dsn_for(&cfg), "sqlite::memory:");
    }

    #[tokio::test]
    async fn connect_with_retry_gives_up_after_max_retries_without_panicking() {
        let cfg = DbConfig {
            db_type: DbType::Sqlite,
            host: String::new(),
            port: String::new(),
            user: String::new(),
            password: String::new(),
            // An invalid path under a directory that doesn't exist forces a
            // connect failure without needing a live network dependency.
            database: "/nonexistent/dir/x.db".into(),
        };
        let result = connect_with_retry(&cfg, 2, Duration::from_millis(10)).await;
        assert!(result.is_err());
    }
}
