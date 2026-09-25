// Package main implements the SASEWaddle headend proxy server.
package main

import (
	"strings"
)

// extractJWTFromPacket extracts JWT token from packet data.
// It looks for "JWT:" prefix in the first 512 bytes of the packet.
// In practice, this would be part of a custom protocol.
func extractJWTFromPacket(data []byte) string {
	dataStr := string(data)
	if idx := strings.Index(dataStr, "JWT:"); idx != -1 {
		end := strings.Index(dataStr[idx+4:], "\n")
		if end == -1 {
			end = len(dataStr) - idx - 4
		}
		return strings.TrimSpace(dataStr[idx+4 : idx+4+end])
	}
	return ""
}

// extractTargetFromPacket extracts target host from packet data.
// It looks for "HOST:" prefix in the packet.
// In practice, this would be part of a custom protocol.
func extractTargetFromPacket(data []byte) string {
	dataStr := string(data)
	if idx := strings.Index(dataStr, "HOST:"); idx != -1 {
		end := strings.Index(dataStr[idx+5:], "\n")
		if end == -1 {
			end = len(dataStr) - idx - 5
		}
		return strings.TrimSpace(dataStr[idx+5 : idx+5+end])
	}
	return ""
}
