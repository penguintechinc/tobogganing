package attestation

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"sort"
	"time"

	"github.com/sirupsen/logrus"
)

// Collector gathers system attestation signals from the host machine.
type Collector struct {
	cfg CollectorConfig
	log *logrus.Entry
}

// NewCollector creates a Collector with the given configuration.
func NewCollector(cfg CollectorConfig) *Collector {
	return &Collector{
		cfg: cfg,
		log: logrus.WithField("component", "attestation"),
	}
}

// Collect gathers all available attestation signals and returns a composite
// SystemFingerprint. Individual collector failures are logged as warnings
// — partial fingerprints are still valid (they just score lower).
func (c *Collector) Collect(ctx context.Context) (*SystemFingerprint, error) {
	fp := &SystemFingerprint{
		Architecture: runtime.GOARCH,
		Platform:     runtime.GOOS,
		CollectedAt:  time.Now().UTC().Format(time.RFC3339),
	}

	// Hostname
	if h, err := os.Hostname(); err == nil {
		fp.Hostname = h
	}

	// DMI / hardware IDs
	dmi, err := collectDMI()
	if err != nil {
		c.log.WithError(err).Warn("DMI collection failed")
	} else {
		fp.ProductUUID = dmi.ProductUUID
		fp.BoardSerial = dmi.BoardSerial
		fp.SysVendor = dmi.SysVendor
		fp.ProductName = dmi.ProductName
	}

	// CPU info
	cpuModel, cpuCount, err := collectCPUInfo()
	if err != nil {
		c.log.WithError(err).Warn("CPU info collection failed")
	} else {
		fp.CPUModel = cpuModel
		fp.CPUCount = cpuCount
	}

	// MAC addresses (physical only, sorted)
	macs, err := collectMACs()
	if err != nil {
		c.log.WithError(err).Warn("MAC address collection failed")
	} else {
		fp.MACAddresses = macs
	}

	// Disk serials
	serials, err := collectDiskSerials()
	if err != nil {
		c.log.WithError(err).Warn("Disk serial collection failed")
	} else {
		fp.DiskSerials = serials
	}

	// OS info (volatile)
	kernel, osRelease, err := collectOSInfo()
	if err != nil {
		c.log.WithError(err).Warn("OS info collection failed")
	} else {
		fp.KernelVersion = kernel
		fp.OSRelease = osRelease
	}

	// Cloud identity (auto-detect)
	cloud, err := collectCloudIdentity(ctx)
	if err != nil {
		c.log.WithError(err).Debug("Cloud identity not detected")
	}
	fp.CloudIdentity = cloud

	// TPM quote (build-tag gated)
	if c.cfg.EnableTPM {
		tpm, err := CollectTPMAttestation(c.cfg.TPMNonce)
		if err != nil {
			if err != ErrTPMNotAvailable {
				c.log.WithError(err).Warn("TPM attestation failed")
			} else {
				c.log.Debug("TPM not available (stub build or no hardware)")
			}
		} else {
			fp.TPMQuote = tpm
		}
	}

	// FleetDM host UUID (passed in config, not collected)
	fp.FleetDMHostUUID = c.cfg.FleetDMHostUUID

	// Compute composite hash over stable fields
	fp.CompositeHash = computeCompositeHash(fp)

	return fp, nil
}

// computeCompositeHash produces a SHA-256 hex digest of the canonical JSON
// representation of stable fingerprint fields. The fields are sorted by key
// to ensure deterministic output regardless of collection order.
func computeCompositeHash(fp *SystemFingerprint) string {
	// Build a deterministic map of stable fields only
	stable := map[string]interface{}{
		"product_uuid": fp.ProductUUID,
		"board_serial": fp.BoardSerial,
		"sys_vendor":   fp.SysVendor,
		"product_name": fp.ProductName,
		"cpu_model":    fp.CPUModel,
		"cpu_count":    fp.CPUCount,
	}

	// Sort MAC addresses and disk serials for determinism
	macs := make([]string, len(fp.MACAddresses))
	copy(macs, fp.MACAddresses)
	sort.Strings(macs)
	stable["mac_addresses"] = macs

	disks := make([]string, len(fp.DiskSerials))
	copy(disks, fp.DiskSerials)
	sort.Strings(disks)
	stable["disk_serials"] = disks

	// Marshal to canonical JSON (encoding/json sorts map keys)
	data, err := json.Marshal(stable)
	if err != nil {
		return ""
	}

	hash := sha256.Sum256(data)
	return fmt.Sprintf("%x", hash)
}
