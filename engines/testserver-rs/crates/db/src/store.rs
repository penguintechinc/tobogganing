//! `TestResultStore`/`AuthDb` are satisfied by both `SeaOrmStore` (real
//! connection) and `SwitchableStore` (degraded-start wrapper), mirroring
//! the Go interfaces of the same names in `cmd/testserver/main.go` /
//! `internal/handlers` / `internal/auth` that let tests inject a mock.

use crate::entities::{server_test_results, users};
use async_trait::async_trait;
use sea_orm::{
    ActiveModelTrait, ColumnTrait, DatabaseConnection, DbErr, EntityTrait, QueryFilter, Set,
};
use std::sync::Arc;
use testserver_core::AuthUser;
use thiserror::Error;
use tokio::sync::RwLock;

#[derive(Debug, Error)]
pub enum DbError {
    #[error("database unavailable")]
    Unavailable,
    #[error("invalid API key")]
    InvalidApiKey,
    #[error("database error: {0}")]
    Db(#[from] DbErr),
    #[error("failed to marshal raw results: {0}")]
    Serialize(#[from] serde_json::Error),
}

/// The public shape callers (axum/tonic handlers) build and pass to
/// `insert_test_result` — mirrors Go's `database.TestResult`.
#[derive(Debug, Clone, Default)]
pub struct NewTestResult {
    pub user_id: Option<i32>,
    pub device_serial: String,
    pub device_hostname: String,
    pub device_os: String,
    pub device_os_version: String,
    pub test_type: String,
    pub protocol_detail: String,
    pub target_host: String,
    pub target_ip: String,
    pub client_ip: String,
    pub latency_ms: Option<f64>,
    pub throughput_mbps: Option<f64>,
    pub jitter_ms: Option<f64>,
    pub packet_loss_percent: Option<f64>,
    pub raw_results: serde_json::Value,
}

#[async_trait]
pub trait TestResultStore: Send + Sync {
    async fn insert_test_result(&self, result: NewTestResult) -> Result<i64, DbError>;
}

#[async_trait]
pub trait AuthDb: Send + Sync {
    async fn validate_api_key(&self, api_key: &str) -> Result<AuthUser, DbError>;
}

/// SeaOrmStore wraps a live `DatabaseConnection`.
pub struct SeaOrmStore {
    conn: DatabaseConnection,
}

impl SeaOrmStore {
    pub fn new(conn: DatabaseConnection) -> Self {
        Self { conn }
    }
}

#[async_trait]
impl TestResultStore for SeaOrmStore {
    async fn insert_test_result(&self, result: NewTestResult) -> Result<i64, DbError> {
        let raw_json = serde_json::to_string(&result.raw_results)?;
        let active = server_test_results::ActiveModel {
            user_id: Set(result.user_id),
            device_serial: Set(result.device_serial),
            device_hostname: Set(result.device_hostname),
            device_os: Set(result.device_os),
            device_os_version: Set(result.device_os_version),
            test_type: Set(result.test_type),
            protocol_detail: Set(result.protocol_detail),
            target_host: Set(result.target_host),
            target_ip: Set(result.target_ip),
            client_ip: Set(result.client_ip),
            latency_ms: Set(result.latency_ms),
            throughput_mbps: Set(result.throughput_mbps),
            jitter_ms: Set(result.jitter_ms),
            packet_loss_percent: Set(result.packet_loss_percent),
            raw_results: Set(raw_json),
            ..Default::default()
        };
        let inserted = active.insert(&self.conn).await?;
        Ok(inserted.id)
    }
}

#[async_trait]
impl AuthDb for SeaOrmStore {
    async fn validate_api_key(&self, api_key: &str) -> Result<AuthUser, DbError> {
        let user = users::Entity::find()
            .filter(users::Column::ApiKey.eq(api_key))
            .filter(users::Column::IsActive.eq(true))
            .one(&self.conn)
            .await?
            .ok_or(DbError::InvalidApiKey)?;
        Ok(AuthUser {
            id: user.id.to_string(),
            tenant: user.ou_id.map(|v| v.to_string()),
            scope: None,
            roles: vec![user.role],
        })
    }
}

/// Starts with no backing connection (every call returns
/// `DbError::Unavailable`) and is swapped to a live `SeaOrmStore` once
/// `connect_with_retry` succeeds — see `cmd/testserver/main.go`'s
/// `switchableStore` for the Go equivalent this mirrors. `/health` and
/// every DB-independent route serve immediately; result storage and
/// API-key auth degrade gracefully instead of blocking startup.
#[derive(Default)]
pub struct SwitchableStore {
    inner: RwLock<Option<SeaOrmStore>>,
}

impl SwitchableStore {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            inner: RwLock::new(None),
        })
    }

    pub async fn set_connection(&self, conn: DatabaseConnection) {
        *self.inner.write().await = Some(SeaOrmStore::new(conn));
    }

    pub async fn is_connected(&self) -> bool {
        self.inner.read().await.is_some()
    }
}

#[async_trait]
impl TestResultStore for SwitchableStore {
    async fn insert_test_result(&self, result: NewTestResult) -> Result<i64, DbError> {
        match self.inner.read().await.as_ref() {
            Some(store) => store.insert_test_result(result).await,
            None => Err(DbError::Unavailable),
        }
    }
}

#[async_trait]
impl AuthDb for SwitchableStore {
    async fn validate_api_key(&self, api_key: &str) -> Result<AuthUser, DbError> {
        match self.inner.read().await.as_ref() {
            Some(store) => store.validate_api_key(api_key).await,
            None => Err(DbError::Unavailable),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn switchable_store_starts_degraded() {
        let store = SwitchableStore::new();
        assert!(!store.is_connected().await);
        let err = store.validate_api_key("any-key").await.unwrap_err();
        assert!(matches!(err, DbError::Unavailable));
        let err = store
            .insert_test_result(NewTestResult::default())
            .await
            .unwrap_err();
        assert!(matches!(err, DbError::Unavailable));
    }
}
