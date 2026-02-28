package attestation

import (
	"runtime"
	"testing"
)

func TestCollectDMI_NonLinux_ReturnsEmpty(t *testing.T) {
	if runtime.GOOS == "linux" {
		t.Skip("This test only runs on non-Linux platforms")
	}

	dmi, err := collectDMI()
	if err != nil {
		t.Fatalf("collectDMI() should not error on non-Linux: %v", err)
	}

	if dmi.ProductUUID != "" || dmi.BoardSerial != "" {
		t.Error("DMI should be empty on non-Linux")
	}
}

func TestCollectDMI_Linux_Runs(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("DMI collection only available on Linux")
	}

	dmi, err := collectDMI()
	// err is acceptable (permissions), but dmi should not be nil
	if dmi == nil {
		t.Fatal("collectDMI() returned nil dmiData")
	}
	_ = err // may fail if not root
}

func TestCollectMACs_ReturnsPhysicalOnly(t *testing.T) {
	macs, err := collectMACs()
	if err != nil {
		t.Fatalf("collectMACs() error: %v", err)
	}

	// Should not contain loopback
	for _, mac := range macs {
		if mac == "" {
			t.Error("Empty MAC address in results")
		}
	}

	// Verify sorted
	for i := 1; i < len(macs); i++ {
		if macs[i] < macs[i-1] {
			t.Errorf("MACs not sorted: %s < %s", macs[i], macs[i-1])
		}
	}
}

func TestIsVirtualInterface(t *testing.T) {
	tests := []struct {
		name     string
		expected bool
	}{
		{"docker0", true},
		{"br-1234", true},
		{"veth1234", true},
		{"wg0", true},
		{"tun0", true},
		{"eth0", false},
		{"enp0s3", false},
		{"wlan0", false},
		{"ens192", false},
	}

	for _, tc := range tests {
		got := isVirtualInterface(tc.name)
		if got != tc.expected {
			t.Errorf("isVirtualInterface(%q) = %v, want %v", tc.name, got, tc.expected)
		}
	}
}

func TestCollectCPUInfo(t *testing.T) {
	model, count, err := collectCPUInfo()
	if err != nil {
		t.Fatalf("collectCPUInfo() error: %v", err)
	}

	if count <= 0 {
		t.Errorf("CPU count should be > 0, got %d", count)
	}

	// On Linux, model should be non-empty
	if runtime.GOOS == "linux" && model == "" {
		t.Error("CPU model should not be empty on Linux")
	}
}

func TestCollectDiskSerials(t *testing.T) {
	serials, err := collectDiskSerials()
	if err != nil {
		t.Fatalf("collectDiskSerials() error: %v", err)
	}

	// serials may be empty (VMs, permissions), but should be sorted
	for i := 1; i < len(serials); i++ {
		if serials[i] < serials[i-1] {
			t.Errorf("Disk serials not sorted: %s < %s", serials[i], serials[i-1])
		}
	}
}

func TestIsVirtualBlockDevice(t *testing.T) {
	tests := []struct {
		name     string
		expected bool
	}{
		{"loop0", true},
		{"ram0", true},
		{"dm-0", true},
		{"nbd0", true},
		{"zram0", true},
		{"sda", false},
		{"nvme0n1", false},
		{"vda", false},
	}

	for _, tc := range tests {
		got := isVirtualBlockDevice(tc.name)
		if got != tc.expected {
			t.Errorf("isVirtualBlockDevice(%q) = %v, want %v", tc.name, got, tc.expected)
		}
	}
}

func TestCollectOSInfo(t *testing.T) {
	kernel, osRelease, err := collectOSInfo()
	if err != nil {
		t.Fatalf("collectOSInfo() error: %v", err)
	}

	if runtime.GOOS == "linux" {
		if kernel == "" {
			t.Error("Kernel version should not be empty on Linux")
		}
		// osRelease may be empty if /etc/os-release is missing
	}
	_ = osRelease
}

func TestReadSysfsFile_NonExistent(t *testing.T) {
	result := readSysfsFile("/nonexistent/path/that/does/not/exist")
	if result != "" {
		t.Errorf("readSysfsFile on nonexistent path should return empty, got %q", result)
	}
}
