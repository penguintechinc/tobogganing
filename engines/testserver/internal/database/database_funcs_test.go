package database_test

import (
	"database/sql"
	"errors"
	"math"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
)

// TestValidateAPIKey_Success tests a valid API key lookup
func TestValidateAPIKey_Success(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	// Expect the query with the API key
	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(1, "testuser", "test@example.com", "Admin", 7, true)

	mock.ExpectQuery("SELECT id, username, email, role, ou_id, is_active FROM users WHERE api_key = \\? AND is_active = TRUE").
		WithArgs("valid-api-key").
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

// TestValidateAPIKey_InvalidKey tests invalid API key (no rows)
func TestValidateAPIKey_InvalidKey(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	// Expect the query to return no rows
	mock.ExpectQuery("SELECT id, username, email, role, ou_id, is_active FROM users WHERE api_key = \\? AND is_active = TRUE").
		WithArgs("invalid-api-key").
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

// TestValidateAPIKey_DatabaseError tests database error during query
func TestValidateAPIKey_DatabaseError(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	// Expect the query to return an error
	mock.ExpectQuery("SELECT id, username, email, role, ou_id, is_active FROM users WHERE api_key = \\? AND is_active = TRUE").
		WithArgs("api-key").
		WillReturnError(errors.New("connection lost"))

	user, err := db.ValidateAPIKey("api-key")

	if err == nil {
		t.Fatal("expected database error, got nil")
	}
	if user != nil {
		t.Errorf("expected nil user, got %v", user)
	}
	if !errors.Is(err, errors.New("connection lost")) && err.Error() != "database error: connection lost" {
		t.Errorf("error = %q, want database error", err.Error())
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestValidateJWT_Success tests a valid JWT token
func TestValidateJWT_Success(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(2, "jwtuser", "jwt@example.com", "Maintainer", nil, true)

	mock.ExpectQuery("SELECT u.id, u.username, u.email, u.role, u.ou_id, u.is_active FROM users u INNER JOIN jwt_tokens t ON u.id = t.user_id WHERE t.token_hash = \\? AND t.expires_at > NOW\\(\\) AND t.revoked = FALSE AND u.is_active = TRUE").
		WithArgs("valid-token-hash").
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

// TestValidateJWT_InvalidOrExpired tests invalid or expired JWT
func TestValidateJWT_InvalidOrExpired(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	mock.ExpectQuery("SELECT u.id, u.username, u.email, u.role, u.ou_id, u.is_active FROM users u INNER JOIN jwt_tokens t ON u.id = t.user_id WHERE t.token_hash = \\? AND t.expires_at > NOW\\(\\) AND t.revoked = FALSE AND u.is_active = TRUE").
		WithArgs("expired-token").
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

// TestValidateJWT_DatabaseError tests database error during JWT validation
func TestValidateJWT_DatabaseError(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	mock.ExpectQuery("SELECT u.id, u.username, u.email, u.role, u.ou_id, u.is_active FROM users u INNER JOIN jwt_tokens t ON u.id = t.user_id WHERE t.token_hash = \\? AND t.expires_at > NOW\\(\\) AND t.revoked = FALSE AND u.is_active = TRUE").
		WithArgs("token-hash").
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

// TestValidateServerKey_Success tests a valid server key
func TestValidateServerKey_Success(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	rows := sqlmock.NewRows([]string{"is_active"}).
		AddRow(true)

	mock.ExpectQuery("SELECT is_active FROM server_keys WHERE key_hash = \\?").
		WithArgs("valid-key-hash").
		WillReturnRows(rows)

	err = db.ValidateServerKey("valid-key-hash")

	if err != nil {
		t.Fatalf("ValidateServerKey failed: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestValidateServerKey_InvalidKey tests invalid server key (no rows)
func TestValidateServerKey_InvalidKey(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	mock.ExpectQuery("SELECT is_active FROM server_keys WHERE key_hash = \\?").
		WithArgs("invalid-key").
		WillReturnRows(sqlmock.NewRows([]string{"is_active"}))

	err = db.ValidateServerKey("invalid-key")

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

// TestValidateServerKey_InactiveKey tests an inactive server key
func TestValidateServerKey_InactiveKey(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	rows := sqlmock.NewRows([]string{"is_active"}).
		AddRow(false)

	mock.ExpectQuery("SELECT is_active FROM server_keys WHERE key_hash = \\?").
		WithArgs("inactive-key").
		WillReturnRows(rows)

	err = db.ValidateServerKey("inactive-key")

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

// TestValidateServerKey_DatabaseError tests database error during key validation
func TestValidateServerKey_DatabaseError(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	mock.ExpectQuery("SELECT is_active FROM server_keys WHERE key_hash = \\?").
		WithArgs("key-hash").
		WillReturnError(errors.New("database connection failed"))

	err = db.ValidateServerKey("key-hash")

	if err == nil {
		t.Fatal("expected database error, got nil")
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestInsertTestResult_Success tests successful test result insertion
func TestInsertTestResult_Success(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

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

	mock.ExpectExec("INSERT INTO server_test_results").
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

// TestInsertTestResult_WithoutUserID tests insertion without user ID
func TestInsertTestResult_WithoutUserID(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	result := &database.TestResult{
		UserID:         nil,
		DeviceSerial:   "SN-99999",
		DeviceHostname: "anonymous-host",
		DeviceOS:       "Windows",
		DeviceOSVersion: "10",
		TestType:       "tcp",
		TargetHost:     "test.example.com",
		TargetIP:       "192.0.2.1",
		ClientIP:       "198.51.100.1",
		RawResults:     map[string]interface{}{"trace": []string{"hop1", "hop2"}},
	}

	mock.ExpectExec("INSERT INTO server_test_results").
		WithArgs(
			sql.NullInt64{},
			"SN-99999",
			"anonymous-host",
			"Windows",
			"10",
			"tcp",
			sqlmock.AnyArg(),
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

// TestInsertTestResult_DatabaseError tests database error during insert
func TestInsertTestResult_DatabaseError(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	result := &database.TestResult{
		DeviceSerial: "SN-ERR",
		TestType:     "http",
		RawResults:   map[string]interface{}{"error": "test"},
	}

	mock.ExpectExec("INSERT INTO server_test_results").
		WillReturnError(errors.New("constraint violation"))

	id, err := db.InsertTestResult(result)

	if err == nil {
		t.Fatal("expected database error, got nil")
	}
	if id != 0 {
		t.Errorf("returned ID = %d, want 0", id)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestInsertTestResult_LastInsertIDError tests error retrieving last insert ID
func TestInsertTestResult_LastInsertIDError(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	result := &database.TestResult{
		DeviceSerial: "SN-LIDERR",
		TestType:     "http",
		RawResults:   map[string]interface{}{},
	}

	// Return a result that will fail on LastInsertId()
	mock.ExpectExec("INSERT INTO server_test_results").
		WillReturnResult(sqlmock.NewErrorResult(errors.New("last_insert_id not supported")))

	id, err := db.InsertTestResult(result)

	if err == nil {
		t.Fatal("expected error retrieving last insert ID, got nil")
	}
	if id != 0 {
		t.Errorf("returned ID = %d, want 0", id)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestClose tests the Close method
func TestClose(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}

	db := &database.DB{DB: mockDB}

	mock.ExpectClose()

	err = db.Close()

	if err != nil {
		t.Fatalf("Close failed: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestValidateAPIKey_NilOUID tests API key validation returning nil OUID
func TestValidateAPIKey_NilOUID(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(3, "noouuser", "noou@example.com", "Viewer", nil, true)

	mock.ExpectQuery("SELECT id, username, email, role, ou_id, is_active FROM users WHERE api_key = \\? AND is_active = TRUE").
		WithArgs("api-no-ou").
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

// TestValidateServerKey_MultipleResults tests server key with multiple rows (edge case)
func TestValidateServerKey_MultipleResults(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	// Return multiple rows (only first should be scanned)
	rows := sqlmock.NewRows([]string{"is_active"}).
		AddRow(true).
		AddRow(false)

	mock.ExpectQuery("SELECT is_active FROM server_keys WHERE key_hash = \\?").
		WithArgs("multi-row-key").
		WillReturnRows(rows)

	err = db.ValidateServerKey("multi-row-key")

	if err != nil {
		t.Fatalf("ValidateServerKey failed: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestValidateJWT_NilOUID tests JWT validation with nil OUID
func TestValidateJWT_NilOUID(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	rows := sqlmock.NewRows([]string{"id", "username", "email", "role", "ou_id", "is_active"}).
		AddRow(5, "nooutoken", "noou-token@example.com", "Viewer", nil, true)

	mock.ExpectQuery("SELECT u.id, u.username, u.email, u.role, u.ou_id, u.is_active FROM users u INNER JOIN jwt_tokens t ON u.id = t.user_id WHERE t.token_hash = \\? AND t.expires_at > NOW\\(\\) AND t.revoked = FALSE AND u.is_active = TRUE").
		WithArgs("token-no-ou").
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

// TestInsertTestResult_EmptyRawResults tests insertion with empty RawResults
func TestInsertTestResult_EmptyRawResults(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	result := &database.TestResult{
		DeviceSerial: "SN-EMPTY",
		TestType:     "ping",
		RawResults:   map[string]interface{}{},
	}

	mock.ExpectExec("INSERT INTO server_test_results").
		WillReturnResult(sqlmock.NewResult(789, 1))

	id, err := db.InsertTestResult(result)

	if err != nil {
		t.Fatalf("InsertTestResult failed: %v", err)
	}
	if id != 789 {
		t.Errorf("returned ID = %d, want 789", id)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestInsertTestResult_UnmarshalableRawResults tests json.Marshal error handling with NaN
func TestInsertTestResult_UnmarshalableRawResults(t *testing.T) {
	mockDB, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("failed to create sqlmock: %v", err)
	}
	defer mockDB.Close()

	db := &database.DB{DB: mockDB}

	// JSON cannot marshal NaN values
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
	if err.Error() != "failed to marshal raw results: unsupported value: NaN" {
		t.Logf("error message: %q", err.Error())
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unfulfilled expectations: %v", err)
	}
}

// TestNew_SuccessfulConnection tests New() with successful connection (requires real MySQL)
func TestNew_SuccessfulConnection(t *testing.T) {
	// Skip if we can't test with a real database
	cfg := database.Config{
		Host:     "localhost",
		Port:     "3306",
		User:     "root",
		Password: "",
		Database: "mysql",
	}

	// This test is commented out because it requires a real MySQL connection
	// It would require setting up MySQL in CI or locally.
	// For now, we test New() via its error path.
	_ = cfg
}

// TestNew_PingFailure tests New() with a connection that fails on Ping
func TestNew_PingFailure(t *testing.T) {
	// Test with an invalid host:port that will fail on Ping
	// Using a port that should be refused
	cfg := database.Config{
		Host:     "127.0.0.1",
		Port:     "1", // Port 1 is privileged and likely not accepting connections
		User:     "testuser",
		Password: "testpass",
		Database: "testdb",
	}

	db, err := database.New(cfg)

	if err == nil {
		// If it somehow connected, close it
		if db != nil {
			db.Close()
		}
		t.Fatal("expected error on Ping to invalid host:port, got nil")
	}
	if db != nil {
		t.Errorf("expected nil DB, got %v", db)
	}
	if err.Error() != "failed to ping database: connection refused" {
		t.Logf("error message: %q (this is expected to vary by system)", err.Error())
	}
}

// TestNew_InvalidDSN tests New() with an invalid DSN format
func TestNew_InvalidDSN(t *testing.T) {
	// Empty password/user may cause issues
	cfg := database.Config{
		Host:     "",
		Port:     "0",
		User:     "",
		Password: "",
		Database: "",
	}

	db, err := database.New(cfg)

	if err == nil {
		if db != nil {
			db.Close()
		}
		t.Fatal("expected error with invalid DSN, got nil")
	}
	if db != nil {
		t.Errorf("expected nil DB, got %v", db)
	}
}
