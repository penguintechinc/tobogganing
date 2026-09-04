// Package database provides the GORM-backed persistence layer for
// testserver: user/API-key/JWT lookups and probe result storage, across
// PostgreSQL (default), MySQL, and SQLite via DB_TYPE.
package database

import (
	"database/sql"
	"errors"
	"fmt"
	"log"
	"time"

	"gorm.io/driver/mysql"
	"gorm.io/driver/postgres"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// DBType selects the SQL dialect New() dials. PostgreSQL is the platform
// default (see hub_api/config); MySQL/MariaDB is the production alternative;
// SQLite is development-tier only (backend-database.md Database Support
// Matrix) and is the only dialect this package will AutoMigrate.
type DBType string

const (
	DBTypePostgreSQL DBType = "postgresql"
	DBTypeMySQL      DBType = "mysql"
	DBTypeSQLite     DBType = "sqlite"
)

// Config carries DB_TYPE-selected connection parameters, matching the env
// var names used across the platform (hub_api/config: DB_TYPE/DB_HOST/
// DB_PORT/DB_USER/DB_PASS/DB_NAME).
type Config struct {
	Type     DBType
	Host     string
	Port     string
	User     string
	Password string
	Database string

	// MaxRetries/RetryDelay control the startup connection retry loop.
	// Defaults (5 attempts, 5s backoff) apply when unset.
	MaxRetries int
	RetryDelay time.Duration
}

// DB wraps *gorm.DB with testserver's persistence methods. It intentionally
// does not fail the process on connection loss — see New().
type DB struct {
	*gorm.DB
}

const (
	defaultMaxRetries = 5
	defaultRetryDelay = 5 * time.Second
)

// New dials the database selected by cfg.Type with retry+backoff. It never
// calls log.Fatalf/os.Exit — callers must handle a non-nil error and keep
// serving DB-independent endpoints (e.g. /health) rather than crash the
// process, per the platform's graceful-degradation rule.
func New(cfg Config) (*DB, error) {
	dialector, err := dialectorFor(cfg)
	if err != nil {
		return nil, err
	}

	maxRetries := cfg.MaxRetries
	if maxRetries <= 0 {
		maxRetries = defaultMaxRetries
	}
	retryDelay := cfg.RetryDelay
	if retryDelay <= 0 {
		retryDelay = defaultRetryDelay
	}

	var gormDB *gorm.DB
	for attempt := 1; attempt <= maxRetries; attempt++ {
		gormDB, err = gorm.Open(dialector, &gorm.Config{
			Logger: logger.Default.LogMode(logger.Warn),
			// Single-statement writes (InsertTestResult) don't need the
			// implicit per-call transaction GORM wraps around Create() by
			// default — skip it for one fewer round trip on the hot path.
			SkipDefaultTransaction: true,
		})
		if err == nil {
			var sqlDB *sql.DB
			sqlDB, err = gormDB.DB()
			if err == nil {
				err = sqlDB.Ping()
			}
			if err == nil {
				break
			}
		}
		log.Printf("database connection attempt %d/%d failed: %v", attempt, maxRetries, err)
		if attempt < maxRetries {
			time.Sleep(retryDelay)
		}
	}
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database after %d attempts: %w", maxRetries, err)
	}

	sqlDB, err := gormDB.DB()
	if err != nil {
		return nil, fmt.Errorf("failed to get underlying sql.DB: %w", err)
	}
	sqlDB.SetMaxOpenConns(100)
	sqlDB.SetMaxIdleConns(10)
	sqlDB.SetConnMaxLifetime(time.Hour)

	// SQLite is dev-tier only; we own its schema outright. Postgres/MySQL
	// schema is managed externally (hub_api Alembic) — never AutoMigrate
	// tables we don't own.
	if cfg.Type == DBTypeSQLite {
		if err := gormDB.AutoMigrate(&User{}, &jwtTokenRow{}, &serverKeyRow{}, &serverTestResultRow{}); err != nil {
			return nil, fmt.Errorf("failed to auto-migrate sqlite schema: %w", err)
		}
	}

	log.Printf("✓ Database connection established (type=%s)", displayType(cfg.Type))

	return &DB{gormDB}, nil
}

func dialectorFor(cfg Config) (gorm.Dialector, error) {
	switch cfg.Type {
	case DBTypeMySQL:
		dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?parseTime=true&charset=utf8mb4&collation=utf8mb4_unicode_ci",
			cfg.User, cfg.Password, cfg.Host, cfg.Port, cfg.Database)
		return mysql.Open(dsn), nil
	case DBTypeSQLite:
		path := cfg.Database
		if path == "" {
			path = "file::memory:?cache=shared"
		}
		return sqlite.Open(path), nil
	case DBTypePostgreSQL, "":
		dsn := fmt.Sprintf("host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
			cfg.Host, cfg.Port, cfg.User, cfg.Password, cfg.Database)
		return postgres.Open(dsn), nil
	default:
		return nil, fmt.Errorf("unsupported DB_TYPE: %q (want postgresql, mysql, or sqlite)", cfg.Type)
	}
}

func displayType(t DBType) DBType {
	if t == "" {
		return DBTypePostgreSQL
	}
	return t
}

// Close releases the underlying connection pool.
func (db *DB) Close() error {
	sqlDB, err := db.DB.DB()
	if err != nil {
		return err
	}
	return sqlDB.Close()
}

// User mirrors the platform `users` table's auth-relevant columns.
type User struct {
	ID       int    `gorm:"column:id;primaryKey"`
	Username string `gorm:"column:username"`
	Email    string `gorm:"column:email"`
	Role     string `gorm:"column:role"`
	OUID     *int   `gorm:"column:ou_id"`
	IsActive bool   `gorm:"column:is_active"`
}

// TableName pins User to the existing `users` table (unmanaged by this
// service — see the W1 plan doc's schema-ownership note).
func (User) TableName() string { return "users" }

// jwtTokenRow is used only for AutoMigrate's dev-tier (sqlite) schema; the
// join in ValidateJWT selects directly into User.
type jwtTokenRow struct {
	ID        int       `gorm:"column:id;primaryKey"`
	UserID    int       `gorm:"column:user_id"`
	TokenHash string    `gorm:"column:token_hash"`
	ExpiresAt time.Time `gorm:"column:expires_at"`
	Revoked   bool      `gorm:"column:revoked"`
}

func (jwtTokenRow) TableName() string { return "jwt_tokens" }

type serverKeyRow struct {
	ID       int    `gorm:"column:id;primaryKey"`
	KeyHash  string `gorm:"column:key_hash"`
	IsActive bool   `gorm:"column:is_active"`
}

func (serverKeyRow) TableName() string { return "server_keys" }

// ValidateAPIKey looks up an active user by API key hash.
func (db *DB) ValidateAPIKey(apiKey string) (*User, error) {
	var user User
	err := db.Select("id", "username", "email", "role", "ou_id", "is_active").
		Where("api_key = ? AND is_active = ?", apiKey, true).
		Take(&user).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, fmt.Errorf("invalid API key")
	}
	if err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}
	return &user, nil
}

// ValidateJWT looks up an active user by an unexpired, unrevoked JWT token
// hash. expires_at is compared against the caller's clock (time.Now) rather
// than a DB-side NOW()/CURRENT_TIMESTAMP so the query is portable across
// PostgreSQL, MySQL, and SQLite.
func (db *DB) ValidateJWT(tokenHash string) (*User, error) {
	var user User
	err := db.Table("users AS u").
		Select("u.id, u.username, u.email, u.role, u.ou_id, u.is_active").
		Joins("INNER JOIN jwt_tokens t ON u.id = t.user_id").
		Where("t.token_hash = ? AND t.expires_at > ? AND t.revoked = ? AND u.is_active = ?",
			tokenHash, time.Now(), false, true).
		Take(&user).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, fmt.Errorf("invalid or expired JWT")
	}
	if err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}
	return &user, nil
}

// ValidateServerKey checks a server key hash is registered and active.
func (db *DB) ValidateServerKey(keyHash string) error {
	var rec serverKeyRow
	err := db.Select("is_active").Where("key_hash = ?", keyHash).Take(&rec).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return fmt.Errorf("invalid server key")
	}
	if err != nil {
		return fmt.Errorf("database error: %w", err)
	}
	if !rec.IsActive {
		return fmt.Errorf("server key is inactive")
	}
	return nil
}
