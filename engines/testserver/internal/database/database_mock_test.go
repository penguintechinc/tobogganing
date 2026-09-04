package database_test

import (
	"errors"
	"math"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
	gormmysql "gorm.io/driver/mysql"
	"gorm.io/gorm"
	gormlogger "gorm.io/gorm/logger"
)

// newMockDB wraps a sqlmock *sql.DB in GORM's MySQL dialector (chosen for
// its ?-placeholder SQL, the least surprising to assert against) so
// ValidateAPIKey/ValidateJWT/ValidateServerKey/InsertTestResult exercise the
// real GORM query-builder path without a live database.
func newMockDB(t *testing.T) (*database.DB, sqlmock.Sqlmock) {
	t.Helper()

	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	t.Cleanup(func() { _ = mockDB.Close() })

	gormDB, err := gorm.Open(gormmysql.New(gormmysql.Config{
		Conn:                      mockDB,
		SkipInitializeWithVersion: true,
	}), &gorm.Config{
		Logger:                 gormlogger.Default.LogMode(gormlogger.Silent),
		SkipDefaultTransaction: true,
	})
	if err != nil {
		t.Fatalf("failed to open gorm on sqlmock conn: %v", err)
	}

	return &database.DB{DB: gormDB}, mock
}

func TestValidateAPIKey_Success(t *testing.T) {
	db, mock := newMockDB(t)

	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(1, "testuser", "test@example.com", "Admin", 7, true)

	mock.ExpectQuery(`(?i)SELECT .* FROM .users. WHERE api_key = \? AND is_active = \?`).
		WithArgs("valid-api-key", true, sqlmock.AnyArg()).
		WillReturnRows(rows)

	user, err := db.ValidateAPIKey("valid-api-key")

	if err != nil {
		t.Fatalf("ValidateAPIKey failed: %v", err)
	}
	if user == nil {
		t.Fatal("expected user, got nil")
	}
	if user.ID != 1 {
		t.Errorf("user.ID = %d, want 1", user.ID)
	}
	if user.Username != "testuser" {
		t.Errorf("user.Username = %q, want testuser", user.Username)
	}
	if user.Role != "Admin" {
		t.Errorf("user.Role = %q, want Admin", user.Role)
	}
	if user.OUID == nil || *user.OUID != 7 {
		t.Error("user.OUID should be 7")
	}
	if !user.IsActive {
		t.Error("user.IsActive should be true")
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateAPIKey_InvalidKey(t *testing.T) {
	db, mock := newMockDB(t)

	mock.ExpectQuery(`(?i)SELECT .* FROM .users. WHERE api_key = \? AND is_active = \?`).
		WithArgs("invalid-api-key", true, sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}))

	user, err := db.ValidateAPIKey("invalid-api-key")

	if err == nil {
		t.Fatal("expected error for invalid API key, got nil")
	}
	if user != nil {
		t.Errorf("expected nil user, got %v", user)
	}
	if err.Error() != "invalid API key" {
		t.Errorf("error = %q, want 'invalid API key'", err.Error())
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateAPIKey_DatabaseError(t *testing.T) {
	db, mock := newMockDB(t)

	mock.ExpectQuery(`(?i)SELECT .* FROM .users. WHERE api_key = \? AND is_active = \?`).
		WithArgs("api-key", true, sqlmock.AnyArg()).
		WillReturnError(errors.New("connection lost"))

	user, err := db.ValidateAPIKey("api-key")

	if err == nil {
		t.Fatal("expected database error, got nil")
	}
	if user != nil {
		t.Errorf("expected nil user, got %v", user)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateAPIKey_NilOUID(t *testing.T) {
	db, mock := newMockDB(t)

	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(3, "noouuser", "noou@example.com", "Viewer", nil, true)

	mock.ExpectQuery(`(?i)SELECT .* FROM .users. WHERE api_key = \? AND is_active = \?`).
		WithArgs("api-no-ou", true, sqlmock.AnyArg()).
		WillReturnRows(rows)

	user, err := db.ValidateAPIKey("api-no-ou")

	if err != nil {
		t.Fatalf("ValidateAPIKey failed: %v", err)
	}
	if user.OUID != nil {
		t.Errorf("user.OUID should be nil, got %v", user.OUID)
	}
	if user.Role != "Viewer" {
		t.Errorf("user.Role = %q, want Viewer", user.Role)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateJWT_Success(t *testing.T) {
	db, mock := newMockDB(t)

	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(2, "jwtuser", "jwt@example.com", "Maintainer", nil, true)

	mock.ExpectQuery(`(?i)SELECT .* FROM users AS u INNER JOIN jwt_tokens t ON u\.id = t\.user_id WHERE t\.token_hash = \? AND t\.expires_at > \? AND t\.revoked = \? AND u\.is_active = \?`).
		WithArgs("valid-token-hash", sqlmock.AnyArg(), false, true, sqlmock.AnyArg()).
		WillReturnRows(rows)

	user, err := db.ValidateJWT("valid-token-hash")

	if err != nil {
		t.Fatalf("ValidateJWT failed: %v", err)
	}
	if user == nil {
		t.Fatal("expected user, got nil")
	}
	if user.ID != 2 {
		t.Errorf("user.ID = %d, want 2", user.ID)
	}
	if user.Username != "jwtuser" {
		t.Errorf("user.Username = %q, want jwtuser", user.Username)
	}
	if user.Role != "Maintainer" {
		t.Errorf("user.Role = %q, want Maintainer", user.Role)
	}
	if user.OUID != nil {
		t.Errorf("user.OUID should be nil, got %v", user.OUID)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateJWT_InvalidOrExpired(t *testing.T) {
	db, mock := newMockDB(t)

	mock.ExpectQuery(`(?i)SELECT .* FROM users AS u INNER JOIN jwt_tokens`).
		WithArgs("expired-token", sqlmock.AnyArg(), false, true, sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}))

	user, err := db.ValidateJWT("expired-token")

	if err == nil {
		t.Fatal("expected error for invalid/expired JWT, got nil")
	}
	if user != nil {
		t.Errorf("expected nil user, got %v", user)
	}
	if err.Error() != "invalid or expired JWT" {
		t.Errorf("error = %q, want 'invalid or expired JWT'", err.Error())
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateJWT_DatabaseError(t *testing.T) {
	db, mock := newMockDB(t)

	mock.ExpectQuery(`(?i)SELECT .* FROM users AS u INNER JOIN jwt_tokens`).
		WithArgs("token-hash", sqlmock.AnyArg(), false, true, sqlmock.AnyArg()).
		WillReturnError(errors.New("network timeout"))

	user, err := db.ValidateJWT("token-hash")

	if err == nil {
		t.Fatal("expected database error, got nil")
	}
	if user != nil {
		t.Errorf("expected nil user, got %v", user)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateJWT_NilOUID(t *testing.T) {
	db, mock := newMockDB(t)

	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(5, "nooutoken", "noou-token@example.com", "Viewer", nil, true)

	mock.ExpectQuery(`(?i)SELECT .* FROM users AS u INNER JOIN jwt_tokens`).
		WithArgs("token-no-ou", sqlmock.AnyArg(), false, true, sqlmock.AnyArg()).
		WillReturnRows(rows)

	user, err := db.ValidateJWT("token-no-ou")

	if err != nil {
		t.Fatalf("ValidateJWT failed: %v", err)
	}
	if user.OUID != nil {
		t.Errorf("user.OUID should be nil, got %v", user.OUID)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateServerKey_Success(t *testing.T) {
	db, mock := newMockDB(t)

	rows := sqlmock.NewRows([]string{"is_active"}).AddRow(true)

	mock.ExpectQuery(`(?i)SELECT .* FROM .server_keys. WHERE key_hash = \?`).
		WithArgs("valid-key-hash", sqlmock.AnyArg()).
		WillReturnRows(rows)

	if err := db.ValidateServerKey("valid-key-hash"); err != nil {
		t.Fatalf("ValidateServerKey failed: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateServerKey_InvalidKey(t *testing.T) {
	db, mock := newMockDB(t)

	mock.ExpectQuery(`(?i)SELECT .* FROM .server_keys. WHERE key_hash = \?`).
		WithArgs("invalid-key", sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{"is_active"}))

	err := db.ValidateServerKey("invalid-key")

	if err == nil {
		t.Fatal("expected error for invalid server key, got nil")
	}
	if err.Error() != "invalid server key" {
		t.Errorf("error = %q, want 'invalid server key'", err.Error())
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateServerKey_InactiveKey(t *testing.T) {
	db, mock := newMockDB(t)

	rows := sqlmock.NewRows([]string{"is_active"}).AddRow(false)

	mock.ExpectQuery(`(?i)SELECT .* FROM .server_keys. WHERE key_hash = \?`).
		WithArgs("inactive-key", sqlmock.AnyArg()).
		WillReturnRows(rows)

	err := db.ValidateServerKey("inactive-key")

	if err == nil {
		t.Fatal("expected error for inactive server key, got nil")
	}
	if err.Error() != "server key is inactive" {
		t.Errorf("error = %q, want 'server key is inactive'", err.Error())
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateServerKey_DatabaseError(t *testing.T) {
	db, mock := newMockDB(t)

	mock.ExpectQuery(`(?i)SELECT .* FROM .server_keys. WHERE key_hash = \?`).
		WithArgs("key-hash", sqlmock.AnyArg()).
		WillReturnError(errors.New("database connection failed"))

	if err := db.ValidateServerKey("key-hash"); err == nil {
		t.Fatal("expected database error, got nil")
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestValidateServerKey_MultipleResults(t *testing.T) {
	db, mock := newMockDB(t)

	rows := sqlmock.NewRows([]string{"is_active"}).AddRow(true).AddRow(false)

	mock.ExpectQuery(`(?i)SELECT .* FROM .server_keys. WHERE key_hash = \?`).
		WithArgs("multi-row-key", sqlmock.AnyArg()).
		WillReturnRows(rows)

	if err := db.ValidateServerKey("multi-row-key"); err != nil {
		t.Fatalf("ValidateServerKey failed: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestInsertTestResult_Success(t *testing.T) {
	db, mock := newMockDB(t)

	latency := 12.5
	throughput := 100.0
	jitter := 1.5
	packetLoss := 0.0
	userID := 42

	result := &database.TestResult{
		UserID:            &userID,
		DeviceSerial:      "SN-12345",
		DeviceHostname:    "test-host",
		DeviceOS:          "Linux",
		DeviceOSVersion:   "6.1",
		TestType:          "http",
		ProtocolDetail:    "http1",
		TargetHost:        "example.com",
		TargetIP:          "93.184.216.34",
		ClientIP:          "192.168.1.100",
		LatencyMS:         &latency,
		ThroughputMbps:    &throughput,
		JitterMS:          &jitter,
		PacketLossPercent: &packetLoss,
		RawResults: map[string]interface{}{
			"status_code": 200,
			"ttfb_ms":     5.0,
		},
	}

	mock.ExpectExec(`(?i)INSERT INTO .server_test_results.`).
		WithArgs(
			userID,
			"SN-12345",
			"test-host",
			"Linux",
			"6.1",
			"http",
			"http1",
			"example.com",
			"93.184.216.34",
			"192.168.1.100",
			latency,
			throughput,
			jitter,
			packetLoss,
			sqlmock.AnyArg(), // raw JSON
		).
		WillReturnResult(sqlmock.NewResult(123, 1))

	id, err := db.InsertTestResult(result)

	if err != nil {
		t.Fatalf("InsertTestResult failed: %v", err)
	}
	if id != 123 {
		t.Errorf("returned ID = %d, want 123", id)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestInsertTestResult_WithoutUserID(t *testing.T) {
	db, mock := newMockDB(t)

	result := &database.TestResult{
		UserID:          nil,
		DeviceSerial:    "SN-99999",
		DeviceHostname:  "anonymous-host",
		DeviceOS:        "Windows",
		DeviceOSVersion: "10",
		TestType:        "tcp",
		TargetHost:      "test.example.com",
		TargetIP:        "192.0.2.1",
		ClientIP:        "198.51.100.1",
		RawResults:      map[string]interface{}{"trace": []string{"hop1", "hop2"}},
	}

	mock.ExpectExec(`(?i)INSERT INTO .server_test_results.`).
		WithArgs(
			nil,
			"SN-99999",
			"anonymous-host",
			"Windows",
			"10",
			"tcp",
			"",
			"test.example.com",
			"192.0.2.1",
			"198.51.100.1",
			nil, nil, nil, nil,
			sqlmock.AnyArg(),
		).
		WillReturnResult(sqlmock.NewResult(456, 1))

	id, err := db.InsertTestResult(result)

	if err != nil {
		t.Fatalf("InsertTestResult failed: %v", err)
	}
	if id != 456 {
		t.Errorf("returned ID = %d, want 456", id)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

func TestInsertTestResult_DatabaseError(t *testing.T) {
	db, mock := newMockDB(t)

	result := &database.TestResult{
		DeviceSerial: "SN-ERR",
		TestType:     "http",
		RawResults:   map[string]interface{}{"error": "test"},
	}

	mock.ExpectExec(`(?i)INSERT INTO .server_test_results.`).
		WillReturnError(errors.New("constraint violation"))

	id, err := db.InsertTestResult(result)

	if err == nil {
		t.Fatal("expected database error, got nil")
	}
	if id != 0 {
		t.Errorf("returned ID = %d, want 0", id)
	}
}

// lastInsertIDErrorResult reports a successful write (RowsAffected=1) but a
// failing LastInsertId() — sqlmock.NewErrorResult fails both identically,
// which short-circuits GORM's create callback (it checks RowsAffected()
// first and returns early on 0) before ever reaching LastInsertId().
type lastInsertIDErrorResult struct{}

func (lastInsertIDErrorResult) LastInsertId() (int64, error) {
	return 0, errors.New("last_insert_id not supported")
}

func (lastInsertIDErrorResult) RowsAffected() (int64, error) {
	return 1, nil
}

func TestInsertTestResult_LastInsertIDError(t *testing.T) {
	db, mock := newMockDB(t)

	result := &database.TestResult{
		DeviceSerial: "SN-LIDERR",
		TestType:     "http",
		RawResults:   map[string]interface{}{},
	}

	mock.ExpectExec(`(?i)INSERT INTO .server_test_results.`).
		WillReturnResult(lastInsertIDErrorResult{})

	id, err := db.InsertTestResult(result)

	if err == nil {
		t.Fatal("expected error retrieving last insert ID, got nil")
	}
	if id != 0 {
		t.Errorf("returned ID = %d, want 0", id)
	}
}

func TestInsertTestResult_EmptyRawResults(t *testing.T) {
	db, mock := newMockDB(t)

	result := &database.TestResult{
		DeviceSerial: "SN-EMPTY",
		TestType:     "ping",
		RawResults:   map[string]interface{}{},
	}

	mock.ExpectExec(`(?i)INSERT INTO .server_test_results.`).
		WillReturnResult(sqlmock.NewResult(789, 1))

	id, err := db.InsertTestResult(result)

	if err != nil {
		t.Fatalf("InsertTestResult failed: %v", err)
	}
	if id != 789 {
		t.Errorf("returned ID = %d, want 789", id)
	}
}

func TestInsertTestResult_UnmarshalableRawResults(t *testing.T) {
	db, _ := newMockDB(t)

	// JSON cannot marshal NaN values — fails before ever reaching the DB.
	result := &database.TestResult{
		DeviceSerial: "SN-NAN",
		TestType:     "http",
		RawResults: map[string]interface{}{
			"invalid_latency": math.NaN(),
		},
	}

	id, err := db.InsertTestResult(result)

	if err == nil {
		t.Fatal("expected error for unmarshalable RawResults, got nil")
	}
	if id != 0 {
		t.Errorf("returned ID = %d, want 0", id)
	}
}

func TestClose(t *testing.T) {
	db, mock := newMockDB(t)

	mock.ExpectClose()

	if err := db.Close(); err != nil {
		t.Fatalf("Close failed: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}
