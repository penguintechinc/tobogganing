//! `ApiError` is the single error type crossing both API boundaries (axum
//! REST and tonic gRPC) — never a leaked `anyhow::Error`, per
//! backend-rust.md. `From<ApiError> for tonic::Status` and
//! `IntoResponse for ApiError` keep the two transports' error mapping in
//! one place instead of duplicating match arms at every handler.

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ApiError {
    #[error("validation error for field '{field}': {message}")]
    Validation { field: String, message: String },

    #[error("invalid request body: {0}")]
    BadRequest(String),

    #[error("authentication required")]
    Unauthorized,

    #[error("invalid credentials")]
    InvalidCredentials,

    #[error("test execution failed: {0}")]
    TestExecution(String),

    #[error("database unavailable")]
    DatabaseUnavailable,

    #[error("database error: {0}")]
    Database(String),

    /// Deferred functionality (ICMP/traceroute/*_trace probes, SSH banner
    /// probe) — see PR description for the follow-up-PR tracking list.
    #[error("not yet implemented: {0}")]
    NotImplemented(String),
}

impl ApiError {
    pub fn validation(field: impl Into<String>, message: impl Into<String>) -> Self {
        ApiError::Validation {
            field: field.into(),
            message: message.into(),
        }
    }

    fn status_code(&self) -> StatusCode {
        match self {
            ApiError::Validation { .. } | ApiError::BadRequest(_) => StatusCode::BAD_REQUEST,
            ApiError::Unauthorized | ApiError::InvalidCredentials => StatusCode::UNAUTHORIZED,
            ApiError::NotImplemented(_) => StatusCode::NOT_IMPLEMENTED,
            ApiError::TestExecution(_) | ApiError::Database(_) | ApiError::DatabaseUnavailable => {
                StatusCode::INTERNAL_SERVER_ERROR
            }
        }
    }
}

#[derive(Serialize)]
struct ErrorBody {
    error: String,
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let status = self.status_code();
        let body = ErrorBody {
            error: self.to_string(),
        };
        (status, Json(body)).into_response()
    }
}

impl From<ApiError> for tonic::Status {
    fn from(err: ApiError) -> Self {
        match err {
            ApiError::Validation { .. } | ApiError::BadRequest(_) => {
                tonic::Status::invalid_argument(err.to_string())
            }
            ApiError::Unauthorized | ApiError::InvalidCredentials => {
                tonic::Status::unauthenticated(err.to_string())
            }
            ApiError::NotImplemented(msg) => tonic::Status::unimplemented(msg),
            ApiError::TestExecution(_) | ApiError::Database(_) | ApiError::DatabaseUnavailable => {
                tonic::Status::internal(err.to_string())
            }
        }
    }
}

/// The gRPC half of the two-layer `api_version` versioning contract
/// (backend.md API Versioning): every request message carries an
/// `api_version` field; unknown/missing routes to `UNIMPLEMENTED` with a
/// `"api_version {v} not supported"` message, never a silent fall-through
/// to a mismatched handler. Mirrors the client-side contract asserted in
/// `agents/node-agent/crates/transport/src/grpc.rs`.
pub fn check_api_version(api_version: &str) -> Result<(), tonic::Status> {
    const SUPPORTED: &[&str] = &["v1"];
    if SUPPORTED.contains(&api_version) {
        Ok(())
    } else {
        Err(tonic::Status::unimplemented(format!(
            "api_version {api_version:?} not supported"
        )))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_api_version_accepts_v1() {
        assert!(check_api_version("v1").is_ok());
    }

    #[test]
    fn check_api_version_rejects_unknown_and_missing() {
        let err = check_api_version("v99").unwrap_err();
        assert_eq!(err.code(), tonic::Code::Unimplemented);
        assert!(err.message().contains("api_version"));

        let err = check_api_version("").unwrap_err();
        assert_eq!(err.code(), tonic::Code::Unimplemented);
    }

    #[test]
    fn not_implemented_maps_to_unimplemented_status() {
        let status: tonic::Status = ApiError::NotImplemented("icmp".into()).into();
        assert_eq!(status.code(), tonic::Code::Unimplemented);
    }

    #[test]
    fn invalid_credentials_maps_to_unauthorized_http_status() {
        let resp = ApiError::InvalidCredentials.into_response();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }
}
