/**
 * Rate limiting with in-memory and Redis support
 * Prevents abuse by limiting request rates per client
 */

import { Request, Response, NextFunction } from 'express';
import { Redis } from 'ioredis';

/**
 * Rate limit configuration options
 */
export interface RateLimitOptions {
  /**
   * Time window in seconds
   */
  windowSeconds: number;

  /**
   * Maximum requests allowed in window
   */
  maxRequests: number;

  /**
   * Redis client for distributed rate limiting (optional)
   */
  redis?: Redis;

  /**
   * Key prefix for Redis storage
   */
  keyPrefix?: string;

  /**
   * Function to extract identifier from request (default: IP address)
   */
  keyGenerator?: (req: Request) => string;

  /**
   * Handler called when rate limit is exceeded
   */
  onLimitReached?: (req: Request, res: Response) => void;

  /**
   * Skip rate limiting based on request
   */
  skip?: (req: Request) => boolean;

  /**
   * Include rate limit headers in response
   */
  headers?: boolean;
}

/**
 * In-memory storage for rate limit counters
 */
interface RateLimitEntry {
  count: number;
  resetTime: number;
}

/**
 * Default key generator (uses IP address)
 */
function defaultKeyGenerator(req: Request): string {
  // Try to get real IP from proxy headers
  const forwarded = req.headers['x-forwarded-for'];
  if (forwarded) {
    const ips = (forwarded as string).split(',');
    return ips[0].trim();
  }
  return req.ip || req.socket.remoteAddress || 'unknown';
}

/**
 * Rate limiter class supporting in-memory and Redis backends
 */
export class RateLimiter {
  private options: Required<RateLimitOptions>;
  private store: Map<string, RateLimitEntry>;
  private cleanupInterval?: NodeJS.Timeout;

  constructor(options: RateLimitOptions) {
    this.options = {
      windowSeconds: options.windowSeconds,
      maxRequests: options.maxRequests,
      redis: options.redis as Redis,
      keyPrefix: options.keyPrefix ?? 'ratelimit:',
      keyGenerator: options.keyGenerator ?? defaultKeyGenerator,
      onLimitReached: options.onLimitReached ?? this.defaultLimitHandler,
      skip: options.skip ?? (() => false),
      headers: options.headers ?? true,
    };

    this.store = new Map();

    // Cleanup expired entries every minute if using in-memory storage
    if (!this.options.redis) {
      this.cleanupInterval = setInterval(() => this.cleanup(), 60000);
    }
  }

  /**
   * Default handler for rate limit exceeded
   */
  private defaultLimitHandler(req: Request, res: Response): void {
    res.status(429).json({
      error: 'Too Many Requests',
      message: 'Rate limit exceeded. Please try again later.',
    });
  }

  /**
   * Cleanup expired entries from in-memory storage
   */
  private cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.store.entries()) {
      if (entry.resetTime < now) {
        this.store.delete(key);
      }
    }
  }

  /**
   * Increment counter in Redis
   */
  private async incrementRedis(key: string): Promise<{ count: number; ttl: number }> {
    const redis = this.options.redis;
    const fullKey = this.options.keyPrefix + key;

    const multi = redis.multi();
    multi.incr(fullKey);
    multi.ttl(fullKey);

    const results = await multi.exec();
    if (!results) {
      throw new Error('Redis transaction failed');
    }

    const count = results[0][1] as number;
    let ttl = results[1][1] as number;

    // Set expiration on first request
    if (count === 1 || ttl === -1) {
      await redis.expire(fullKey, this.options.windowSeconds);
      ttl = this.options.windowSeconds;
    }

    return { count, ttl };
  }

  /**
   * Increment counter in memory
   */
  private incrementMemory(key: string): { count: number; ttl: number } {
    const now = Date.now();
    const entry = this.store.get(key);

    if (!entry || entry.resetTime < now) {
      const resetTime = now + this.options.windowSeconds * 1000;
      const newEntry: RateLimitEntry = { count: 1, resetTime };
      this.store.set(key, newEntry);
      return { count: 1, ttl: this.options.windowSeconds };
    }

    entry.count++;
    const ttl = Math.ceil((entry.resetTime - now) / 1000);
    return { count: entry.count, ttl };
  }

  /**
   * Express middleware for rate limiting
   */
  public middleware(): (req: Request, res: Response, next: NextFunction) => void {
    return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
      try {
        // Skip if configured
        if (this.options.skip(req)) {
          next();
          return;
        }

        // Generate key for this request
        const key = this.options.keyGenerator(req);

        // Increment counter
        const { count, ttl } = this.options.redis
          ? await this.incrementRedis(key)
          : this.incrementMemory(key);

        // Set headers if enabled
        if (this.options.headers) {
          res.setHeader('X-RateLimit-Limit', String(this.options.maxRequests));
          res.setHeader('X-RateLimit-Remaining', String(Math.max(0, this.options.maxRequests - count)));
          res.setHeader('X-RateLimit-Reset', String(Date.now() + ttl * 1000));
        }

        // Check if limit exceeded
        if (count > this.options.maxRequests) {
          res.setHeader('Retry-After', String(ttl));
          this.options.onLimitReached(req, res);
          return;
        }

        next();
      } catch (error) {
        // Log error and allow request (fail open)
        console.error('Rate limiter error:', error);
        next();
      }
    };
  }

  /**
   * Reset rate limit for a specific key
   */
  public async reset(key: string): Promise<void> {
    if (this.options.redis) {
      const fullKey = this.options.keyPrefix + key;
      await this.options.redis.del(fullKey);
    } else {
      this.store.delete(key);
    }
  }

  /**
   * Get current count for a key
   */
  public async getCount(key: string): Promise<number> {
    if (this.options.redis) {
      const fullKey = this.options.keyPrefix + key;
      const count = await this.options.redis.get(fullKey);
      return count ? parseInt(count, 10) : 0;
    } else {
      const entry = this.store.get(key);
      if (!entry || entry.resetTime < Date.now()) {
        return 0;
      }
      return entry.count;
    }
  }

  /**
   * Cleanup resources
   */
  public destroy(): void {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    this.store.clear();
  }
}

/**
 * Create rate limiter middleware with options
 * @param options - Rate limit configuration
 * @returns Express middleware
 */
export function rateLimit(
  options: RateLimitOptions
): (req: Request, res: Response, next: NextFunction) => void {
  const limiter = new RateLimiter(options);
  return limiter.middleware();
}
