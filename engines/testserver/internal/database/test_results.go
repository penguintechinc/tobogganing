package database

import (
	"encoding/json"
	"fmt"
)

// TestResult is the public shape callers (handlers) build and pass to
// InsertTestResult — unchanged across the GORM conversion so handlers/auth
// callers need no changes.
type TestResult struct {
	UserID            *int
	DeviceSerial      string
	DeviceHostname    string
	DeviceOS          string
	DeviceOSVersion   string
	TestType          string
	ProtocolDetail    string
	TargetHost        string
	TargetIP          string
	ClientIP          string
	LatencyMS         *float64
	ThroughputMbps    *float64
	JitterMS          *float64
	PacketLossPercent *float64
	RawResults        map[string]interface{}
}

// serverTestResultRow is the GORM row for the `server_test_results` table.
// RawResults is stored as marshaled JSON text — portable across
// PostgreSQL/MySQL/SQLite without assuming a native json/jsonb column type
// (the actual production schema for this table isn't currently owned by
// this service — see the W1 plan doc's schema note).
type serverTestResultRow struct {
	ID                int64    `gorm:"column:id;primaryKey"`
	UserID            *int     `gorm:"column:user_id"`
	DeviceSerial      string   `gorm:"column:device_serial"`
	DeviceHostname    string   `gorm:"column:device_hostname"`
	DeviceOS          string   `gorm:"column:device_os"`
	DeviceOSVersion   string   `gorm:"column:device_os_version"`
	TestType          string   `gorm:"column:test_type"`
	ProtocolDetail    string   `gorm:"column:protocol_detail"`
	TargetHost        string   `gorm:"column:target_host"`
	TargetIP          string   `gorm:"column:target_ip"`
	ClientIP          string   `gorm:"column:client_ip"`
	LatencyMS         *float64 `gorm:"column:latency_ms"`
	ThroughputMbps    *float64 `gorm:"column:throughput_mbps"`
	JitterMS          *float64 `gorm:"column:jitter_ms"`
	PacketLossPercent *float64 `gorm:"column:packet_loss_percent"`
	RawResults        string   `gorm:"column:raw_results"`
}

func (serverTestResultRow) TableName() string { return "server_test_results" }

// InsertTestResult persists a probe/speedtest result. Unlike the previous
// database/sql implementation (which called sql.Result.LastInsertId() —
// unsupported by the Postgres driver, so this path was silently broken on
// Postgres), GORM's Create() retrieves the generated ID per-dialect
// (RETURNING id on Postgres, LAST_INSERT_ID() on MySQL, last_insert_rowid()
// on SQLite).
func (db *DB) InsertTestResult(result *TestResult) (int64, error) {
	rawJSON, err := json.Marshal(result.RawResults)
	if err != nil {
		return 0, fmt.Errorf("failed to marshal raw results: %w", err)
	}

	row := serverTestResultRow{
		UserID:            result.UserID,
		DeviceSerial:      result.DeviceSerial,
		DeviceHostname:    result.DeviceHostname,
		DeviceOS:          result.DeviceOS,
		DeviceOSVersion:   result.DeviceOSVersion,
		TestType:          result.TestType,
		ProtocolDetail:    result.ProtocolDetail,
		TargetHost:        result.TargetHost,
		TargetIP:          result.TargetIP,
		ClientIP:          result.ClientIP,
		LatencyMS:         result.LatencyMS,
		ThroughputMbps:    result.ThroughputMbps,
		JitterMS:          result.JitterMS,
		PacketLossPercent: result.PacketLossPercent,
		RawResults:        string(rawJSON),
	}

	if err := db.Create(&row).Error; err != nil {
		return 0, fmt.Errorf("failed to insert test result: %w", err)
	}

	return row.ID, nil
}
