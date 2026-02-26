//go:build !xdp

package xdp

import "fmt"

// AFXDPSocket is a no-op stub when built without the xdp tag.
type AFXDPSocket struct{}

// NewAFXDPSocket returns an error without XDP build tag.
func NewAFXDPSocket(_ string, _, _ int) (*AFXDPSocket, error) {
	return nil, fmt.Errorf("afxdp: not available (build without -tags xdp)")
}

// Receive returns an error without XDP build tag.
func (s *AFXDPSocket) Receive() ([][]byte, error) {
	return nil, fmt.Errorf("afxdp: not available")
}

// Transmit returns an error without XDP build tag.
func (s *AFXDPSocket) Transmit(_ [][]byte) error {
	return fmt.Errorf("afxdp: not available")
}

// Close is a no-op without XDP build tag.
func (s *AFXDPSocket) Close() {}
