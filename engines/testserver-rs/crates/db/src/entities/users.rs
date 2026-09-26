//! Mirrors the platform `users` table's auth-relevant columns — pinned to
//! the existing table (unmanaged by this service; owned by hub_api's
//! Alembic migrations), matching the Go `database.User` GORM model 1:1.
//! Only `api_key` lookups (`ApiKey <key>` auth scheme) touch this entity —
//! `Bearer` JWTs are verified in-process by `testserver-core::JwtVerifier`
//! with no DB round trip.

use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "users")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub username: String,
    pub email: String,
    pub role: String,
    pub ou_id: Option<i32>,
    pub is_active: bool,
    pub api_key: Option<String>,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {}

impl ActiveModelBehavior for ActiveModel {}
