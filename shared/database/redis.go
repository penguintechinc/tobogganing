package database

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

// RedisClient wraps redis.Client with additional functionality
type RedisClient struct {
	*redis.Client
	config *RedisConfig
}

// RedisConfig holds Redis configuration
type RedisConfig struct {
	Addr     string
	Password string
	DB       int

	// Connection pool settings
	PoolSize     int
	MinIdleConns int
	MaxIdleTime  time.Duration
	MaxConnAge   time.Duration

	// Timeouts
	DialTimeout  time.Duration
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
}

// DefaultRedisConfig returns default Redis configuration
func DefaultRedisConfig() *RedisConfig {
	return &RedisConfig{
		Addr:     getEnv("REDIS_ADDR", "localhost:6379"),
		Password: getEnv("REDIS_PASSWORD", ""),
		DB:       getEnvInt("REDIS_DB", 0),

		PoolSize:     10,
		MinIdleConns: 5,
		MaxIdleTime:  5 * time.Minute,
		MaxConnAge:   10 * time.Minute,

		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
	}
}

// NewRedisFromURL creates a new Redis client from URL
func NewRedisFromURL(url string) (*RedisClient, error) {
	if url == "" {
		url = os.Getenv("REDIS_URL")
	}

	if url == "" {
		return nil, fmt.Errorf("Redis URL not provided")
	}

	opts, err := redis.ParseURL(url)
	if err != nil {
		return nil, fmt.Errorf("failed to parse Redis URL: %w", err)
	}

	// Apply default timeouts
	config := DefaultRedisConfig()
	opts.PoolSize = config.PoolSize
	opts.MinIdleConns = config.MinIdleConns
	opts.MaxIdleTime = config.MaxIdleTime
	opts.MaxConnAge = config.MaxConnAge
	opts.DialTimeout = config.DialTimeout
	opts.ReadTimeout = config.ReadTimeout
	opts.WriteTimeout = config.WriteTimeout

	client := redis.NewClient(opts)

	// Test the connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to ping Redis: %w", err)
	}

	return &RedisClient{
		Client: client,
		config: config,
	}, nil
}

// NewRedis creates a new Redis client with configuration
func NewRedis(config *RedisConfig) (*RedisClient, error) {
	if config == nil {
		config = DefaultRedisConfig()
	}

	client := redis.NewClient(&redis.Options{
		Addr:     config.Addr,
		Password: config.Password,
		DB:       config.DB,

		PoolSize:     config.PoolSize,
		MinIdleConns: config.MinIdleConns,
		MaxIdleTime:  config.MaxIdleTime,
		MaxConnAge:   config.MaxConnAge,

		DialTimeout:  config.DialTimeout,
		ReadTimeout:  config.ReadTimeout,
		WriteTimeout: config.WriteTimeout,
	})

	// Test the connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to ping Redis: %w", err)
	}

	return &RedisClient{
		Client: client,
		config: config,
	}, nil
}

// HealthCheck performs a health check on Redis
func (r *RedisClient) HealthCheck(ctx context.Context) error {
	return r.Ping(ctx).Err()
}

// Cache operations with structured key patterns

// CacheKey represents a structured cache key
type CacheKey struct {
	Prefix string
	ID     string
	Suffix string
}

// String returns the formatted cache key
func (k CacheKey) String() string {
	if k.Suffix != "" {
		return fmt.Sprintf("%s:%s:%s", k.Prefix, k.ID, k.Suffix)
	}
	return fmt.Sprintf("%s:%s", k.Prefix, k.ID)
}

// License cache operations
func (r *RedisClient) CacheLicenseValidation(ctx context.Context, licenseKey string, data interface{}, ttl time.Duration) error {
	key := CacheKey{Prefix: "license", ID: licenseKey, Suffix: "validation"}
	return r.SetEx(ctx, key.String(), data, ttl).Err()
}

func (r *RedisClient) GetCachedLicenseValidation(ctx context.Context, licenseKey string) (string, error) {
	key := CacheKey{Prefix: "license", ID: licenseKey, Suffix: "validation"}
	return r.Get(ctx, key.String()).Result()
}

func (r *RedisClient) CacheFeature(ctx context.Context, licenseKey, feature string, enabled bool, ttl time.Duration) error {
	key := CacheKey{Prefix: "feature", ID: licenseKey, Suffix: feature}
	return r.SetEx(ctx, key.String(), enabled, ttl).Err()
}

func (r *RedisClient) GetCachedFeature(ctx context.Context, licenseKey, feature string) (bool, error) {
	key := CacheKey{Prefix: "feature", ID: licenseKey, Suffix: feature}
	result := r.Get(ctx, key.String())
	if result.Err() != nil {
		return false, result.Err()
	}
	return result.Bool()
}

// Session management operations
func (r *RedisClient) StoreSession(ctx context.Context, sessionID string, userID uint, ttl time.Duration) error {
	key := CacheKey{Prefix: "session", ID: sessionID}
	return r.SetEx(ctx, key.String(), userID, ttl).Err()
}

func (r *RedisClient) GetSession(ctx context.Context, sessionID string) (uint, error) {
	key := CacheKey{Prefix: "session", ID: sessionID}
	result := r.Get(ctx, key.String())
	if result.Err() != nil {
		return 0, result.Err()
	}
	userID, err := result.Uint64()
	return uint(userID), err
}

func (r *RedisClient) DeleteSession(ctx context.Context, sessionID string) error {
	key := CacheKey{Prefix: "session", ID: sessionID}
	return r.Del(ctx, key.String()).Err()
}

// Rate limiting operations
func (r *RedisClient) RateLimit(ctx context.Context, identifier string, limit int, window time.Duration) (bool, error) {
	key := CacheKey{Prefix: "ratelimit", ID: identifier}

	pipe := r.Pipeline()
	incr := pipe.Incr(ctx, key.String())
	pipe.Expire(ctx, key.String(), window)

	_, err := pipe.Exec(ctx)
	if err != nil {
		return false, err
	}

	current, err := incr.Result()
	if err != nil {
		return false, err
	}

	return current <= int64(limit), nil
}

// Feature usage tracking
func (r *RedisClient) IncrementFeatureUsage(ctx context.Context, userID uint, feature string) error {
	key := CacheKey{Prefix: "usage", ID: fmt.Sprintf("%d", userID), Suffix: feature}
	return r.Incr(ctx, key.String()).Err()
}

func (r *RedisClient) GetFeatureUsage(ctx context.Context, userID uint, feature string) (int64, error) {
	key := CacheKey{Prefix: "usage", ID: fmt.Sprintf("%d", userID), Suffix: feature}
	return r.Get(ctx, key.String()).Int64()
}

// Configuration caching
func (r *RedisClient) CacheConfig(ctx context.Context, configKey string, value interface{}, ttl time.Duration) error {
	key := CacheKey{Prefix: "config", ID: configKey}
	return r.SetEx(ctx, key.String(), value, ttl).Err()
}

func (r *RedisClient) GetConfig(ctx context.Context, configKey string) (string, error) {
	key := CacheKey{Prefix: "config", ID: configKey}
	return r.Get(ctx, key.String()).Result()
}

// Metrics caching
func (r *RedisClient) CacheMetrics(ctx context.Context, metricKey string, value interface{}, ttl time.Duration) error {
	key := CacheKey{Prefix: "metrics", ID: metricKey}
	return r.SetEx(ctx, key.String(), value, ttl).Err()
}

// Pub/Sub operations for real-time features
func (r *RedisClient) PublishLicenseUpdate(ctx context.Context, licenseKey string, message interface{}) error {
	channel := fmt.Sprintf("license_updates:%s", licenseKey)
	return r.Publish(ctx, channel, message).Err()
}

func (r *RedisClient) SubscribeLicenseUpdates(ctx context.Context, licenseKey string) *redis.PubSub {
	channel := fmt.Sprintf("license_updates:%s", licenseKey)
	return r.Subscribe(ctx, channel)
}

// Health monitoring
func (r *RedisClient) GetConnectionStats() *redis.PoolStats {
	return r.PoolStats()
}

// Cleanup operations
func (r *RedisClient) CleanupExpiredSessions(ctx context.Context) error {
	// This would be implemented as a periodic cleanup job
	pattern := "session:*"
	iter := r.Scan(ctx, 0, pattern, 100).Iterator()

	var keysToCheck []string
	for iter.Next(ctx) {
		keysToCheck = append(keysToCheck, iter.Val())
	}

	if err := iter.Err(); err != nil {
		return err
	}

	// Check TTL for each key and remove expired ones
	for _, key := range keysToCheck {
		ttl := r.TTL(ctx, key)
		if ttl.Val() < 0 {
			r.Del(ctx, key)
		}
	}

	return nil
}

// Bulk operations
func (r *RedisClient) GetMultiple(ctx context.Context, keys []string) ([]interface{}, error) {
	if len(keys) == 0 {
		return nil, nil
	}

	pipe := r.Pipeline()
	cmds := make([]*redis.StringCmd, len(keys))

	for i, key := range keys {
		cmds[i] = pipe.Get(ctx, key)
	}

	_, err := pipe.Exec(ctx)
	if err != nil && err != redis.Nil {
		return nil, err
	}

	results := make([]interface{}, len(keys))
	for i, cmd := range cmds {
		val, err := cmd.Result()
		if err == redis.Nil {
			results[i] = nil
		} else if err != nil {
			return nil, err
		} else {
			results[i] = val
		}
	}

	return results, nil
}

// Helper function to get environment variable as int
func getEnvInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if intVal, err := strconv.Atoi(value); err == nil {
			return intVal
		}
	}
	return defaultValue
}