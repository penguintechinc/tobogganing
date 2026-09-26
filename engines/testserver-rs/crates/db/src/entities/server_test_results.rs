//! Probe/speedtest result storage — matches the Go `serverTestResultRow`
//! GORM model 1:1, including `raw_results` staying a marshaled-JSON text
//! column (portable across PostgreSQL/MySQL/SQLite without assuming a
//! native json/jsonb type). Schema for this table is not currently owned
//! by this service (carried over from the Go source's same note).

use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, DeriveEntityModel)]
#[sea_orm(table_name = "server_test_results")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i64,
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
    pub raw_results: String,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {}

impl ActiveModelBehavior for ActiveModel {}
