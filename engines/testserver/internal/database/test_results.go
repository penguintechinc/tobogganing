package database

import (
	"database/sql"
	"encoding/json"
	"fmt"
)

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

func (db *DB) InsertTestResult(result *TestResult) (int64, error) {
	rawJSON, err := json.Marshal(result.RawResults)
	if err != nil {
		return 0, fmt.Errorf("failed to marshal raw results: %w", err)
	}

	query := `
		INSERT INTO server_test_results (
			user_id, device_serial, device_hostname, device_os, device_os_version,
			test_type, protocol_detail, target_host, target_ip, client_ip,
			latency_ms, throughput_mbps, jitter_ms, packet_loss_percent,
			raw_results
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`

	var userID interface{} = sql.NullInt64{}
	if result.UserID != nil {
		userID = *result.UserID
	}

	res, err := db.Exec(query,
		userID,
		result.DeviceSerial,
		result.DeviceHostname,
		result.DeviceOS,
		result.DeviceOSVersion,
		result.TestType,
		result.ProtocolDetail,
		result.TargetHost,
		result.TargetIP,
		result.ClientIP,
		result.LatencyMS,
		result.ThroughputMbps,
		result.JitterMS,
		result.PacketLossPercent,
		rawJSON,
	)

	if err != nil {
		return 0, fmt.Errorf("failed to insert test result: %w", err)
	}

	id, err := res.LastInsertId()
	if err != nil {
		return 0, fmt.Errorf("failed to get last insert ID: %w", err)
	}

	return id, nil
}
