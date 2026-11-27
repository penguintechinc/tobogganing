//! Process-wide concurrency cap on probe execution, enforcing
//! `MAX_CONCURRENT_TESTS`. Shared by the REST and gRPC surfaces so the bound
//! is global, not per-surface.
//!
//! Over-limit behaviour is fail-fast (HTTP 429 / gRPC `RESOURCE_EXHAUSTED`),
//! not a bounded wait: probes can run for tens of seconds (ICMP/traceroute),
//! so queueing would push callers past their own deadlines and hide overload.
//! Callers (hub-api workers, node agents) retry with backoff, so an
//! immediate, explicit rejection is the cheaper and more honest signal.

use std::sync::Arc;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

use crate::ApiError;

/// Cloneable handle to the shared probe semaphore; each running probe holds
/// one [`OwnedSemaphorePermit`] for its full duration (released on drop).
#[derive(Clone, Debug)]
pub struct TestLimiter {
    sem: Arc<Semaphore>,
    max: usize,
}

impl TestLimiter {
    /// Builds a limiter allowing `max` concurrent probes. `max == 0` is
    /// clamped to 1 so a misconfiguration never silently disables every probe.
    pub fn new(max: usize) -> Self {
        let max = max.max(1);
        Self {
            sem: Arc::new(Semaphore::new(max)),
            max,
        }
    }

    /// Acquires a probe slot without waiting; returns
    /// [`ApiError::TooManyTests`] when all `max` slots are in use.
    pub fn try_acquire(&self) -> Result<OwnedSemaphorePermit, ApiError> {
        self.sem
            .clone()
            .try_acquire_owned()
            .map_err(|_| ApiError::TooManyTests(self.max))
    }

    /// Configured cap (after clamping).
    pub fn max(&self) -> usize {
        self.max
    }

    /// Slots currently free — used by tests and diagnostics.
    pub fn available(&self) -> usize {
        self.sem.available_permits()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounds_concurrency_and_releases_on_drop() {
        let lim = TestLimiter::new(2);
        let a = lim.try_acquire().expect("slot 1");
        let _b = lim.try_acquire().expect("slot 2");
        let err = lim.try_acquire().unwrap_err();
        assert!(matches!(err, ApiError::TooManyTests(2)));
        drop(a);
        assert_eq!(lim.available(), 1);
        assert!(lim.try_acquire().is_ok());
    }

    #[test]
    fn zero_is_clamped_to_one() {
        let lim = TestLimiter::new(0);
        assert_eq!(lim.max(), 1);
        let _p = lim.try_acquire().expect("one slot");
        assert!(lim.try_acquire().is_err());
    }

    #[tokio::test]
    async fn bounds_real_concurrent_tasks() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        let lim = TestLimiter::new(3);
        let live = Arc::new(AtomicUsize::new(0));
        let peak = Arc::new(AtomicUsize::new(0));
        let rejected = Arc::new(AtomicUsize::new(0));
        let mut handles = Vec::new();
        for _ in 0..20 {
            let (lim, live, peak, rejected) =
                (lim.clone(), live.clone(), peak.clone(), rejected.clone());
            handles.push(tokio::spawn(async move {
                match lim.try_acquire() {
                    Ok(_permit) => {
                        let now = live.fetch_add(1, Ordering::SeqCst) + 1;
                        peak.fetch_max(now, Ordering::SeqCst);
                        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
                        live.fetch_sub(1, Ordering::SeqCst);
                    }
                    Err(_) => {
                        rejected.fetch_add(1, Ordering::SeqCst);
                    }
                }
            }));
        }
        for h in handles {
            h.await.expect("task");
        }
        assert!(peak.load(Ordering::SeqCst) <= 3);
        assert!(rejected.load(Ordering::SeqCst) >= 17);
        assert_eq!(lim.available(), 3);
    }

    #[test]
    fn too_many_tests_maps_to_resource_exhausted_and_429() {
        use axum::response::IntoResponse;
        let status: tonic::Status = ApiError::TooManyTests(3).into();
        assert_eq!(status.code(), tonic::Code::ResourceExhausted);
        let resp = ApiError::TooManyTests(3).into_response();
        assert_eq!(resp.status(), axum::http::StatusCode::TOO_MANY_REQUESTS);
    }
}
