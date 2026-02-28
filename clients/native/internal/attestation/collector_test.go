package attestation

import (
	"context"
	"testing"
)

func TestCollect_ReturnsPopulatedFingerprint(t *testing.T) {
	cfg := CollectorConfig{
		EnableTPM: false, // stub will return ErrTPMNotAvailable
	}
	c := NewCollector(cfg)

	fp, err := c.Collect(context.Background())
	if err != nil {
		t.Fatalf("Collect() returned error: %v", err)
	}

	if fp == nil {
		t.Fatal("Collect() returned nil fingerprint")
	}

	// Should always have platform and architecture
	if fp.Platform == "" {
		t.Error("Platform should not be empty")
	}
	if fp.Architecture == "" {
		t.Error("Architecture should not be empty")
	}
	if fp.CollectedAt == "" {
		t.Error("CollectedAt should not be empty")
	}
	if fp.CompositeHash == "" {
		t.Error("CompositeHash should not be empty")
	}
}

func TestCollect_CompositeHashIsDeterministic(t *testing.T) {
	cfg := CollectorConfig{EnableTPM: false}
	c := NewCollector(cfg)

	fp1, _ := c.Collect(context.Background())
	fp2, _ := c.Collect(context.Background())

	if fp1.CompositeHash != fp2.CompositeHash {
		t.Errorf("CompositeHash not deterministic: %s != %s",
			fp1.CompositeHash, fp2.CompositeHash)
	}
}

func TestComputeCompositeHash_DeterministicOutput(t *testing.T) {
	fp := &SystemFingerprint{
		ProductUUID:  "test-uuid-1234",
		BoardSerial:  "SN12345",
		SysVendor:    "TestVendor",
		ProductName:  "TestProduct",
		CPUModel:     "Intel Xeon",
		CPUCount:     4,
		MACAddresses: []string{"aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"},
		DiskSerials:  []string{"DISK001", "DISK002"},
	}

	hash1 := computeCompositeHash(fp)
	hash2 := computeCompositeHash(fp)

	if hash1 != hash2 {
		t.Errorf("Hash not deterministic: %s != %s", hash1, hash2)
	}

	if len(hash1) != 64 { // SHA-256 hex = 64 chars
		t.Errorf("Hash length should be 64, got %d", len(hash1))
	}
}

func TestComputeCompositeHash_OrderIndependent(t *testing.T) {
	fp1 := &SystemFingerprint{
		MACAddresses: []string{"bb:bb:bb", "aa:aa:aa"},
		DiskSerials:  []string{"DISK002", "DISK001"},
	}
	fp2 := &SystemFingerprint{
		MACAddresses: []string{"aa:aa:aa", "bb:bb:bb"},
		DiskSerials:  []string{"DISK001", "DISK002"},
	}

	hash1 := computeCompositeHash(fp1)
	hash2 := computeCompositeHash(fp2)

	if hash1 != hash2 {
		t.Errorf("Hash should be order-independent: %s != %s", hash1, hash2)
	}
}

func TestComputeCompositeHash_VolatileFieldsExcluded(t *testing.T) {
	fp1 := &SystemFingerprint{
		ProductUUID:   "same-uuid",
		KernelVersion: "5.15.0",
		OSRelease:     "Ubuntu 22.04",
		Hostname:      "host-a",
	}
	fp2 := &SystemFingerprint{
		ProductUUID:   "same-uuid",
		KernelVersion: "6.1.0",        // changed
		OSRelease:     "Ubuntu 24.04", // changed
		Hostname:      "host-b",       // changed
	}

	hash1 := computeCompositeHash(fp1)
	hash2 := computeCompositeHash(fp2)

	if hash1 != hash2 {
		t.Error("Volatile field changes should not affect hash")
	}
}

func TestCollect_PartialCollectionOnErrors(t *testing.T) {
	// Even if hardware collection fails, Collect should succeed
	// with a partial fingerprint
	cfg := CollectorConfig{
		EnableTPM:       true, // stub will fail with ErrTPMNotAvailable
		FleetDMHostUUID: "test-fleet-uuid",
	}
	c := NewCollector(cfg)

	fp, err := c.Collect(context.Background())
	if err != nil {
		t.Fatalf("Collect() should not fail on partial collection: %v", err)
	}

	if fp.FleetDMHostUUID != "test-fleet-uuid" {
		t.Errorf("FleetDMHostUUID should be 'test-fleet-uuid', got %s", fp.FleetDMHostUUID)
	}

	// TPM should be nil (stub returns ErrTPMNotAvailable)
	if fp.TPMQuote != nil {
		t.Error("TPMQuote should be nil in stub build")
	}
}
