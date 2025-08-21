"""Redis cache service for SASEWaddle Manager."""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta

import aioredis
from aioredis import Redis

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis-based caching service with connection pooling and retry logic."""
    
    def __init__(self, redis_url: Optional[str] = None, default_ttl: int = 300):
        """Initialize Redis cache.
        
        Args:
            redis_url: Redis connection URL (defaults to env REDIS_URL)
            default_ttl: Default TTL in seconds for cached items
        """
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.default_ttl = default_ttl
        self.pool: Optional[Redis] = None
        self.connected = False
        
    async def connect(self) -> bool:
        """Establish Redis connection with error handling."""
        try:
            self.pool = await aioredis.from_url(
                self.redis_url,
                encoding='utf-8',
                decode_responses=True,
                max_connections=20,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # Test connection
            await self.pool.ping()
            self.connected = True
            logger.info(f"Connected to Redis at {self.redis_url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.connected = False
            return False
            
    async def disconnect(self):
        """Close Redis connection."""
        if self.pool:
            await self.pool.close()
            self.connected = False
            logger.info("Disconnected from Redis")
    
    def _serialize(self, value: Any) -> str:
        """Serialize value for Redis storage."""
        if isinstance(value, (str, int, float)):
            return str(value)
        return json.dumps(value, default=str)
    
    def _deserialize(self, value: str) -> Any:
        """Deserialize value from Redis storage."""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a cache value with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.connected or not self.pool:
            return False
            
        try:
            serialized_value = self._serialize(value)
            expire_time = ttl or self.default_ttl
            
            await self.pool.setex(key, expire_time, serialized_value)
            logger.debug(f"Cached key '{key}' with TTL {expire_time}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set cache key '{key}': {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a cache value.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if not self.connected or not self.pool:
            return None
            
        try:
            value = await self.pool.get(key)
            if value is None:
                return None
                
            result = self._deserialize(value)
            logger.debug(f"Cache hit for key '{key}'")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get cache key '{key}': {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a cache key.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self.connected or not self.pool:
            return False
            
        try:
            deleted = await self.pool.delete(key)
            logger.debug(f"Deleted cache key '{key}': {bool(deleted)}")
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"Failed to delete cache key '{key}': {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a cache key exists.
        
        Args:
            key: Cache key to check
            
        Returns:
            True if key exists, False otherwise
        """
        if not self.connected or not self.pool:
            return False
            
        try:
            exists = await self.pool.exists(key)
            return bool(exists)
            
        except Exception as e:
            logger.error(f"Failed to check cache key '{key}': {e}")
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (e.g., 'user:*', 'firewall:*')
            
        Returns:
            Number of keys deleted
        """
        if not self.connected or not self.pool:
            return 0
            
        try:
            keys = await self.pool.keys(pattern)
            if keys:
                deleted = await self.pool.delete(*keys)
                logger.info(f"Invalidated {deleted} cache keys matching pattern '{pattern}'")
                return deleted
            return 0
            
        except Exception as e:
            logger.error(f"Failed to invalidate pattern '{pattern}': {e}")
            return 0
    
    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key.
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds (-1 if no expiry, -2 if key doesn't exist)
        """
        if not self.connected or not self.pool:
            return -2
            
        try:
            return await self.pool.ttl(key)
        except Exception as e:
            logger.error(f"Failed to get TTL for key '{key}': {e}")
            return -2
    
    async def extend_ttl(self, key: str, ttl: int) -> bool:
        """Extend TTL for an existing key.
        
        Args:
            key: Cache key
            ttl: New TTL in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if not self.connected or not self.pool:
            return False
            
        try:
            result = await self.pool.expire(key, ttl)
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to extend TTL for key '{key}': {e}")
            return False


class FirewallRulesCache:
    """Specialized cache for firewall rules with versioning."""
    
    def __init__(self, redis_cache: RedisCache):
        self.redis = redis_cache
        self.key_prefix = "firewall:"
    
    async def get_user_rules(self, user_id: str) -> Optional[Dict]:
        """Get cached firewall rules for a user."""
        key = f"{self.key_prefix}user:{user_id}"
        return await self.redis.get(key)
    
    async def set_user_rules(self, user_id: str, rules: Dict, ttl: int = 300) -> bool:
        """Cache firewall rules for a user."""
        key = f"{self.key_prefix}user:{user_id}"
        # Add timestamp to track cache freshness
        rules['cached_at'] = datetime.utcnow().isoformat()
        return await self.redis.set(key, rules, ttl)
    
    async def get_all_rules(self) -> Optional[Dict]:
        """Get all cached firewall rules."""
        key = f"{self.key_prefix}all_rules"
        return await self.redis.get(key)
    
    async def set_all_rules(self, rules: Dict, ttl: int = 180) -> bool:
        """Cache all firewall rules (shorter TTL for headend consumption)."""
        key = f"{self.key_prefix}all_rules"
        rules['cached_at'] = datetime.utcnow().isoformat()
        return await self.redis.set(key, rules, ttl)
    
    async def invalidate_user(self, user_id: str) -> bool:
        """Invalidate cached rules for a specific user."""
        key = f"{self.key_prefix}user:{user_id}"
        success = await self.redis.delete(key)
        
        # Also invalidate the all_rules cache since it contains this user's rules
        await self.redis.delete(f"{self.key_prefix}all_rules")
        
        return success
    
    async def invalidate_all(self) -> int:
        """Invalidate all firewall rule caches."""
        return await self.redis.invalidate_pattern(f"{self.key_prefix}*")


# Global cache instance
cache_instance: Optional[RedisCache] = None
firewall_cache: Optional[FirewallRulesCache] = None


async def get_cache() -> RedisCache:
    """Get global cache instance (singleton pattern)."""
    global cache_instance
    
    if cache_instance is None:
        cache_instance = RedisCache()
        await cache_instance.connect()
    
    return cache_instance


async def get_firewall_cache() -> FirewallRulesCache:
    """Get firewall-specific cache instance."""
    global firewall_cache
    
    if firewall_cache is None:
        redis_cache = await get_cache()
        firewall_cache = FirewallRulesCache(redis_cache)
    
    return firewall_cache


async def cleanup_cache():
    """Clean up cache connections on shutdown."""
    global cache_instance, firewall_cache
    
    if cache_instance:
        await cache_instance.disconnect()
        cache_instance = None
        firewall_cache = None