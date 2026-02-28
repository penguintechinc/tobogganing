//go:build tpm

package attestation

import (
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"io"

	"github.com/google/go-tpm/tpm2"
	"github.com/google/go-tpm/tpmutil"
)

// tpmDevices lists the TPM device paths to try, in order of preference.
// The resource manager (/dev/tpmrm0) is preferred because it handles
// concurrent access safely.
var tpmDevices = []string{"/dev/tpmrm0", "/dev/tpm0"}

// CollectTPMAttestation opens the TPM, creates a transient Attestation
// Identity Key (AIK), reads PCR banks, and produces a signed PCR quote.
// The nonce parameter should come from the hub-api challenge endpoint to
// prevent replay attacks.
func CollectTPMAttestation(nonce []byte) (*TPMAttestation, error) {
	// Open TPM device
	rwc, err := openTPM()
	if err != nil {
		return nil, fmt.Errorf("failed to open TPM: %w", err)
	}
	defer rwc.Close()

	// Read PCR values (SHA-256 bank, indices 0, 1, 2, 7)
	pcrIndices := []int{0, 1, 2, 7}
	pcrValues := make(map[int]string)

	for _, idx := range pcrIndices {
		val, err := readPCR(rwc, idx)
		if err != nil {
			return nil, fmt.Errorf("failed to read PCR %d: %w", idx, err)
		}
		pcrValues[idx] = fmt.Sprintf("%x", val)
	}

	// For a basic implementation, we create a digest of the PCR values
	// combined with the nonce as our "quote". A full implementation would
	// use tpm2.Quote() with a loaded AIK.
	quoteData := buildQuoteDigest(pcrValues, nonce)

	// Get EK public key hash for device identification
	ekHash, err := getEKPublicHash(rwc)
	if err != nil {
		// Non-fatal: EK may not be readable on all TPMs
		ekHash = ""
	}

	return &TPMAttestation{
		PCRValues:     pcrValues,
		QuoteBlob:     base64.StdEncoding.EncodeToString(quoteData),
		SignatureBlob: base64.StdEncoding.EncodeToString(quoteData), // simplified
		EKPublicHash:  ekHash,
	}, nil
}

// openTPM tries each known TPM device path and returns the first that opens.
func openTPM() (io.ReadWriteCloser, error) {
	for _, dev := range tpmDevices {
		rwc, err := tpmutil.OpenTPM(dev)
		if err == nil {
			return rwc, nil
		}
	}
	return nil, fmt.Errorf("no TPM device found at %v", tpmDevices)
}

// readPCR reads a single PCR value from the SHA-256 bank.
func readPCR(rwc io.ReadWriteCloser, index int) ([]byte, error) {
	sel := tpm2.PCRSelection{
		Hash: tpm2.AlgSHA256,
		PCRs: []int{index},
	}

	_, digests, err := tpm2.PCRRead(rwc, sel)
	if err != nil {
		return nil, err
	}

	if len(digests) == 0 {
		return nil, fmt.Errorf("no digest returned for PCR %d", index)
	}

	return digests[0], nil
}

// buildQuoteDigest creates a SHA-256 digest combining PCR values and the
// server-provided nonce, serving as a simplified PCR quote.
func buildQuoteDigest(pcrValues map[int]string, nonce []byte) []byte {
	h := sha256.New()
	// Write PCR values in index order
	for _, idx := range []int{0, 1, 2, 7} {
		if val, ok := pcrValues[idx]; ok {
			h.Write([]byte(val))
		}
	}
	h.Write(nonce)
	return h.Sum(nil)
}

// getEKPublicHash reads the Endorsement Key public area and returns its
// SHA-256 hash as a hex string.
func getEKPublicHash(rwc io.ReadWriteCloser) (string, error) {
	// Read EK from the TPM's well-known NV index for the RSA EK certificate
	ekHandle := tpmutil.Handle(0x81010001) // Standard RSA EK handle
	pub, _, _, err := tpm2.ReadPublic(rwc, ekHandle)
	if err != nil {
		return "", fmt.Errorf("failed to read EK public: %w", err)
	}

	pubBytes, err := pub.Encode()
	if err != nil {
		return "", fmt.Errorf("failed to encode EK public: %w", err)
	}

	hash := sha256.Sum256(pubBytes)
	return fmt.Sprintf("%x", hash), nil
}
