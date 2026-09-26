//! SeaORM persistence layer, replacing the Go testserver's GORM layer
//! (`engines/testserver/internal/database`). Owns two tables the service
//! does not manage the schema for (`users`, `server_test_results` — see
//! `entities` for the column-ownership note carried over from the Go
//! source) plus the retry+degraded-mode connection lifecycle
//! (`SwitchableStore`) that lets `/health` and public speedtest routes
//! serve before/without a database.

pub mod connection;
pub mod entities;
pub mod store;

pub use connection::connect_with_retry;
pub use store::{AuthDb, DbError, NewTestResult, SeaOrmStore, SwitchableStore, TestResultStore};
