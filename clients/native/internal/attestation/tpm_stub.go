//go:build !tpm

package attestation

// CollectTPMAttestation is a stub that returns ErrTPMNotAvailable when the
// binary is built without the tpm build tag. This ensures default builds
// have zero dependency on github.com/google/go-tpm.
func CollectTPMAttestation(_ []byte) (*TPMAttestation, error) {
	return nil, ErrTPMNotAvailable
}
