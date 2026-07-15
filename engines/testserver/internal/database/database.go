package database

import (
	"database/sql"
	"fmt"
	"log"
	"time"

	_ "github.com/go-sql-driver/mysql"
)

type Config struct {
	Host     string
	Port     string
	User     string
	Password string
	Database string
}

type DB struct {
	*sql.DB
}

func New(cfg Config) (*DB, error) {
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?parseTime=true&charset=utf8mb4&collation=utf8mb4_unicode_ci",
		cfg.User,
		cfg.Password,
		cfg.Host,
		cfg.Port,
		cfg.Database,
	)

	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	db.SetMaxOpenConns(100)
	db.SetMaxIdleConns(10)
	db.SetConnMaxLifetime(time.Hour)

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	log.Println("✓ Database connection established")

	return &DB{db}, nil
}

func (db *DB) Close() error {
	return db.DB.Close()
}

func (db *DB) ValidateAPIKey(apiKey string) (*User, error) {
	var user User
	query := `
		SELECT id, username, email, role, ou_id, is_active
		FROM users
		WHERE api_key = ? AND is_active = TRUE
	`
	err := db.QueryRow(query, apiKey).Scan(
		&user.ID,
		&user.Username,
		&user.Email,
		&user.Role,
		&user.OUID,
		&user.IsActive,
	)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("invalid API key")
	}
	if err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}
	return &user, nil
}

func (db *DB) ValidateJWT(tokenHash string) (*User, error) {
	var user User
	query := `
		SELECT u.id, u.username, u.email, u.role, u.ou_id, u.is_active
		FROM users u
		INNER JOIN jwt_tokens t ON u.id = t.user_id
		WHERE t.token_hash = ?
		  AND t.expires_at > NOW()
		  AND t.revoked = FALSE
		  AND u.is_active = TRUE
	`
	err := db.QueryRow(query, tokenHash).Scan(
		&user.ID,
		&user.Username,
		&user.Email,
		&user.Role,
		&user.OUID,
		&user.IsActive,
	)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("invalid or expired JWT")
	}
	if err != nil {
		return nil, fmt.Errorf("database error: %w", err)
	}
	return &user, nil
}

func (db *DB) ValidateServerKey(keyHash string) error {
	var isActive bool
	query := `SELECT is_active FROM server_keys WHERE key_hash = ?`
	err := db.QueryRow(query, keyHash).Scan(&isActive)
	if err == sql.ErrNoRows {
		return fmt.Errorf("invalid server key")
	}
	if err != nil {
		return fmt.Errorf("database error: %w", err)
	}
	if !isActive {
		return fmt.Errorf("server key is inactive")
	}
	return nil
}

type User struct {
	ID       int
	Username string
	Email    string
	Role     string
	OUID     *int
	IsActive bool
}
