package attestation

import "errors"

// ErrTPMNotAvailable is returned when TPM hardware is not present or the binary
// was built without the tpm build tag.
var ErrTPMNotAvailable = errors.New("TPM not available")

// SystemFingerprint contains hardware and platform identifiers collected from
// the host machine. Stable fields contribute to CompositeHash; volatile fields
// are recorded but excluded from the hash so that routine OS updates don't
// invalidate the fingerprint.
type SystemFingerprint struct {
	// Stable (included in composite hash)
	ProductUUID  string   `json:"product_uuid,omitempty"`
	BoardSerial  string   `json:"board_serial,omitempty"`
	SysVendor    string   `json:"sys_vendor,omitempty"`
	ProductName  string   `json:"product_name,omitempty"`
	CPUModel     string   `json:"cpu_model,omitempty"`
	CPUCount     int      `json:"cpu_count,omitempty"`
	MACAddresses []string `json:"mac_addresses,omitempty"` // sorted, physical only
	DiskSerials  []string `json:"disk_serials,omitempty"`  // sorted

	// Volatile (stored, not hashed)
	KernelVersion string `json:"kernel_version,omitempty"`
	OSRelease     string `json:"os_release,omitempty"`
	Architecture  string `json:"architecture,omitempty"`
	Platform      string `json:"platform,omitempty"`
	Hostname      string `json:"hostname,omitempty"`

	// Optional attestation layers
	TPMQuote        *TPMAttestation        `json:"tpm_quote,omitempty"`
	CloudIdentity   *CloudInstanceIdentity `json:"cloud_identity,omitempty"`
	FleetDMHostUUID string                 `json:"fleetdm_host_uuid,omitempty"`

	// Computed
	CompositeHash string `json:"composite_hash"`
	CollectedAt   string `json:"collected_at"`
}

// TPMAttestation holds a TPM 2.0 PCR quote and its cryptographic proof.
type TPMAttestation struct {
	PCRValues     map[int]string `json:"pcr_values"`
	QuoteBlob     string         `json:"quote_blob"`     // base64
	SignatureBlob string         `json:"signature_blob"` // base64
	EKPublicHash  string         `json:"ek_public_hash"`
}

// CloudInstanceIdentity carries a cloud provider's signed instance identity
// document (AWS IID, GCP identity token, Azure IMDS attestedData).
type CloudInstanceIdentity struct {
	Provider       string `json:"provider"`        // aws, gcp, azure
	InstanceID     string `json:"instance_id"`
	Region         string `json:"region"`
	AccountID      string `json:"account_id"`
	SignedDocument string `json:"signed_document"` // raw signed IID
}

// CollectorConfig controls which attestation signals are collected.
type CollectorConfig struct {
	FleetDMHostUUID string
	EnableTPM       bool
	TPMNonce        []byte // server-provided nonce for TPM PCR quote
}
