//go:build !tpm

package attestation

import (
    "errors"
    "testing"
)

func TestCollectTPMAttestation_Stub_ReturnsNotAvailable(t *testing.T) {
    tpm, err := CollectTPMAttestation(nil)
    if tpm != nil {
        t.Error("Stub should return nil TPMAttestation")
    }
    if !errors.Is(err, ErrTPMNotAvailable) {
        t.Errorf("Stub should return ErrTPMNotAvailable, got: %v", err)
    }
}
