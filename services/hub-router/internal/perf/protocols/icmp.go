package protocols

import (
	"fmt"
	"net"
	"os"
	"time"
)

// ICMPTestResult holds the outcome of a multi-ping ICMP probe sequence.
type ICMPTestResult struct {
	Target     string  `json:"target"`
	LatencyMs  float64 `json:"latency_ms"`
	PacketLoss float64 `json:"packet_loss_pct"`
	JitterMs   float64 `json:"jitter_ms"`
	Success    bool    `json:"success"`
	Error      string  `json:"error,omitempty"`
}

// RunICMPTest sends count ICMP echo requests to target (IP or hostname) and
// returns average latency, max inter-packet jitter, and packet loss.
// Requires CAP_NET_RAW or root privileges; degrades gracefully if unavailable.
func RunICMPTest(target string, count int, timeout time.Duration) ICMPTestResult {
	result := ICMPTestResult{Target: target}

	addr, err := net.ResolveIPAddr("ip4", target)
	if err != nil {
		result.Error = err.Error()
		return result
	}

	conn, err := net.DialIP("ip4:icmp", nil, addr)
	if err != nil {
		result.Error = fmt.Sprintf("ICMP requires root/CAP_NET_RAW: %v", err)
		return result
	}
	defer conn.Close()

	if count <= 0 {
		count = 5
	}

	var latencies []float64
	sent := 0
	received := 0

	for i := 0; i < count; i++ {
		_ = conn.SetDeadline(time.Now().Add(timeout))

		msg := buildICMPEchoRequest(uint16(os.Getpid()&0xffff), uint16(i))

		start := time.Now()
		if _, err := conn.Write(msg); err != nil {
			sent++
			continue
		}
		sent++

		buf := make([]byte, 1500)
		if _, err := conn.Read(buf); err != nil {
			continue
		}

		elapsed := time.Since(start).Seconds() * 1000
		latencies = append(latencies, elapsed)
		received++
	}

	if len(latencies) > 0 {
		var sum float64
		for _, l := range latencies {
			sum += l
		}
		result.LatencyMs = sum / float64(len(latencies))
		result.Success = true

		if len(latencies) > 1 {
			var maxDiff float64
			for i := 1; i < len(latencies); i++ {
				diff := latencies[i] - latencies[i-1]
				if diff < 0 {
					diff = -diff
				}
				if diff > maxDiff {
					maxDiff = diff
				}
			}
			result.JitterMs = maxDiff
		}
	}

	if sent > 0 {
		result.PacketLoss = float64(sent-received) / float64(sent) * 100
	}

	return result
}

// buildICMPEchoRequest constructs a minimal ICMP echo request packet.
func buildICMPEchoRequest(id, seq uint16) []byte {
	msg := make([]byte, 8)
	msg[0] = 8 // Echo Request type
	msg[1] = 0 // Code
	msg[4] = byte(id >> 8)
	msg[5] = byte(id)
	msg[6] = byte(seq >> 8)
	msg[7] = byte(seq)

	cs := icmpChecksum(msg)
	msg[2] = byte(cs >> 8)
	msg[3] = byte(cs)
	return msg
}

// icmpChecksum computes the one's complement checksum for an ICMP packet.
func icmpChecksum(b []byte) uint16 {
	var sum uint32
	for i := 0; i < len(b)-1; i += 2 {
		sum += uint32(b[i])<<8 | uint32(b[i+1])
	}
	if len(b)%2 != 0 {
		sum += uint32(b[len(b)-1]) << 8
	}
	for sum > 0xffff {
		sum = (sum >> 16) + (sum & 0xffff)
	}
	return ^uint16(sum)
}
