//! Bounded, TTL-expiring cache of DNS answers keyed by `(name, record
//! type)`. Sits in front of the DoH upstream so repeat local queries for
//! the same name don't round-trip to the P3 resolver until the configured
//! TTL elapses. Guarded by an async mutex so the concurrent UDP/TCP request
//! handlers spawned by `hickory-server` can share one instance safely.

use hickory_proto::op::ResponseCode;
use hickory_proto::rr::{Name, Record, RecordType};
use lru::LruCache;
use std::num::NonZeroUsize;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

/// Cache key: the queried name and record type. DNS names compare and hash
/// case-insensitively (per `hickory_proto::rr::Name`'s own `Eq`/`Hash`
/// impls), matching RFC 1035 name comparison rules.
pub(super) type CacheKey = (Name, RecordType);

/// The parts of a resolved DNS answer worth caching: the response code plus
/// the three record sections a forwarder relays verbatim.
#[derive(Debug, Clone)]
pub(super) struct CachedAnswer {
    pub response_code: ResponseCode,
    pub answers: Vec<Record>,
    pub authorities: Vec<Record>,
    pub additionals: Vec<Record>,
}

struct Entry {
    answer: CachedAnswer,
    inserted_at: Instant,
}

/// A bounded LRU cache with a single configured TTL applied uniformly to
/// every entry. Constructing with `enabled = false` or `max_entries == 0`
/// produces an always-miss cache rather than a special-cased code path.
pub(super) struct ResponseCache {
    inner: Mutex<Option<LruCache<CacheKey, Entry>>>,
    ttl: Duration,
}

impl ResponseCache {
    /// Builds a cache honoring `DnsConfig`'s `cache_enabled`/
    /// `cache_max_entries`/`cache_ttl_secs` fields.
    pub(super) fn new(enabled: bool, max_entries: u32, ttl_secs: u32) -> Self {
        let inner = if enabled {
            NonZeroUsize::new(max_entries as usize).map(LruCache::new)
        } else {
            None
        };
        Self {
            inner: Mutex::new(inner),
            ttl: Duration::from_secs(u64::from(ttl_secs)),
        }
    }

    /// Returns the cached answer for `key` if present and not yet expired;
    /// an expired entry is evicted on access rather than left to linger.
    pub(super) async fn get(&self, key: &CacheKey) -> Option<CachedAnswer> {
        let mut guard = self.inner.lock().await;
        let cache = guard.as_mut()?;
        let expired = cache
            .get(key)
            .map(|entry| entry.inserted_at.elapsed() > self.ttl)?;
        if expired {
            cache.pop(key);
            return None;
        }
        cache.get(key).map(|entry| entry.answer.clone())
    }

    /// Inserts or replaces the cached answer for `key`, resetting its TTL
    /// clock. A no-op on a disabled (`None`) cache.
    pub(super) async fn put(&self, key: CacheKey, answer: CachedAnswer) {
        let mut guard = self.inner.lock().await;
        if let Some(cache) = guard.as_mut() {
            cache.put(
                key,
                Entry {
                    answer,
                    inserted_at: Instant::now(),
                },
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::str::FromStr;
    use std::time::Duration as StdDuration;

    fn sample_answer() -> CachedAnswer {
        CachedAnswer {
            response_code: ResponseCode::NoError,
            answers: Vec::new(),
            authorities: Vec::new(),
            additionals: Vec::new(),
        }
    }

    #[tokio::test]
    async fn disabled_cache_always_misses() {
        let cache = ResponseCache::new(false, 10, 300);
        let key = (Name::from_str("example.com.").unwrap(), RecordType::A);
        cache.put(key.clone(), sample_answer()).await;
        assert!(cache.get(&key).await.is_none());
    }

    #[tokio::test]
    async fn hit_then_expiry() {
        // A 0-second TTL means "elapsed() > ttl" is true almost immediately,
        // exercising the expiry path deterministically without a real sleep.
        let cache = ResponseCache::new(true, 10, 0);
        let key = (Name::from_str("example.com.").unwrap(), RecordType::A);
        cache.put(key.clone(), sample_answer()).await;

        // Give the clock a moment to move past the 0s TTL.
        tokio::time::sleep(StdDuration::from_millis(5)).await;
        assert!(cache.get(&key).await.is_none());
    }

    #[tokio::test]
    async fn hit_within_ttl() {
        let cache = ResponseCache::new(true, 10, 300);
        let key = (Name::from_str("example.com.").unwrap(), RecordType::AAAA);
        cache.put(key.clone(), sample_answer()).await;
        let hit = cache.get(&key).await;
        assert!(hit.is_some());
        assert_eq!(hit.unwrap().response_code, ResponseCode::NoError);
    }

    #[tokio::test]
    async fn max_entries_zero_disables_cache() {
        let cache = ResponseCache::new(true, 0, 300);
        let key = (Name::from_str("example.com.").unwrap(), RecordType::A);
        cache.put(key.clone(), sample_answer()).await;
        assert!(cache.get(&key).await.is_none());
    }
}
