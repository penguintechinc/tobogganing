package attestation

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"syscall"
)

// dmiData holds values read from /sys/class/dmi/id/.
type dmiData struct {
	ProductUUID string
	BoardSerial string
	SysVendor   string
	ProductName string
}

// collectDMI reads DMI identifiers from sysfs. Returns empty fields on
// non-Linux platforms or if the files are unreadable (e.g. not root).
func collectDMI() (*dmiData, error) {
	if runtime.GOOS != "linux" {
		return &dmiData{}, nil
	}

	d := &dmiData{}
	base := "/sys/class/dmi/id"

	d.ProductUUID = readSysfsFile(filepath.Join(base, "product_uuid"))
	d.BoardSerial = readSysfsFile(filepath.Join(base, "board_serial"))
	d.SysVendor = readSysfsFile(filepath.Join(base, "sys_vendor"))
	d.ProductName = readSysfsFile(filepath.Join(base, "product_name"))

	if d.ProductUUID == "" && d.BoardSerial == "" && d.SysVendor == "" && d.ProductName == "" {
		return d, fmt.Errorf("no DMI data available (check permissions)")
	}

	return d, nil
}

// collectMACs returns sorted MAC addresses of physical network interfaces,
// filtering out loopback, virtual bridges, docker, and veth interfaces.
func collectMACs() ([]string, error) {
	ifaces, err := net.Interfaces()
	if err != nil {
		return nil, fmt.Errorf("failed to list interfaces: %w", err)
	}

	var macs []string
	for _, iface := range ifaces {
		// Skip loopback
		if iface.Flags&net.FlagLoopback != 0 {
			continue
		}

		// Skip interfaces with no hardware address
		mac := iface.HardwareAddr.String()
		if mac == "" {
			continue
		}

		// Skip virtual/container interfaces
		name := iface.Name
		if isVirtualInterface(name) {
			continue
		}

		macs = append(macs, mac)
	}

	sort.Strings(macs)
	return macs, nil
}

// isVirtualInterface returns true for interface names that indicate virtual
// devices (bridges, veth pairs, docker networks, tunnels, etc.).
func isVirtualInterface(name string) bool {
	virtualPrefixes := []string{
		"docker", "br-", "veth", "virbr", "vnet",
		"tun", "tap", "wg", "lo", "bond", "dummy",
		"flannel", "cni", "calico", "cilium",
	}
	lower := strings.ToLower(name)
	for _, prefix := range virtualPrefixes {
		if strings.HasPrefix(lower, prefix) {
			return true
		}
	}
	return false
}

// collectCPUInfo parses /proc/cpuinfo to extract the CPU model name and
// physical processor count. On non-Linux returns runtime.NumCPU().
func collectCPUInfo() (model string, count int, err error) {
	if runtime.GOOS != "linux" {
		return "", runtime.NumCPU(), nil
	}

	f, err := os.Open("/proc/cpuinfo")
	if err != nil {
		return "", runtime.NumCPU(), fmt.Errorf("failed to open /proc/cpuinfo: %w", err)
	}
	defer f.Close()

	physicalIDs := make(map[string]struct{})
	scanner := bufio.NewScanner(f)

	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "model name") {
			if model == "" {
				parts := strings.SplitN(line, ":", 2)
				if len(parts) == 2 {
					model = strings.TrimSpace(parts[1])
				}
			}
		}
		if strings.HasPrefix(line, "physical id") {
			parts := strings.SplitN(line, ":", 2)
			if len(parts) == 2 {
				physicalIDs[strings.TrimSpace(parts[1])] = struct{}{}
			}
		}
	}

	count = len(physicalIDs)
	if count == 0 {
		count = runtime.NumCPU()
	}

	return model, count, scanner.Err()
}

// collectDiskSerials reads serial numbers from /sys/block/*/device/serial,
// filtering out virtual block devices (loop, ram, dm-).
func collectDiskSerials() ([]string, error) {
	if runtime.GOOS != "linux" {
		return nil, nil
	}

	matches, err := filepath.Glob("/sys/block/*/device/serial")
	if err != nil {
		return nil, fmt.Errorf("failed to glob disk serials: %w", err)
	}

	var serials []string
	for _, path := range matches {
		// Extract block device name from path
		parts := strings.Split(path, "/")
		if len(parts) < 4 {
			continue
		}
		devName := parts[3] // /sys/block/<devName>/device/serial

		// Skip virtual block devices
		if isVirtualBlockDevice(devName) {
			continue
		}

		serial := readSysfsFile(path)
		if serial != "" {
			serials = append(serials, serial)
		}
	}

	sort.Strings(serials)
	return serials, nil
}

// isVirtualBlockDevice returns true for virtual block device names.
func isVirtualBlockDevice(name string) bool {
	virtualPrefixes := []string{"loop", "ram", "dm-", "nbd", "zram"}
	for _, prefix := range virtualPrefixes {
		if strings.HasPrefix(name, prefix) {
			return true
		}
	}
	return false
}

// collectOSInfo returns the kernel version and OS release string.
func collectOSInfo() (kernel string, osRelease string, err error) {
	// Kernel version from uname
	var utsname syscall.Utsname
	if err := syscall.Uname(&utsname); err == nil {
		kernel = utsnameBytesToString(utsname.Release)
	}

	// OS release from /etc/os-release
	if runtime.GOOS == "linux" {
		osRelease = parseOSRelease()
	} else {
		osRelease = runtime.GOOS
	}

	return kernel, osRelease, nil
}

// parseOSRelease reads PRETTY_NAME from /etc/os-release.
func parseOSRelease() string {
	f, err := os.Open("/etc/os-release")
	if err != nil {
		return ""
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "PRETTY_NAME=") {
			val := strings.TrimPrefix(line, "PRETTY_NAME=")
			return strings.Trim(val, "\"")
		}
	}
	return ""
}

// readSysfsFile reads and trims a single-line sysfs file. Returns empty
// string on any error (permission denied, file not found, etc.).
func readSysfsFile(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

// utsnameBytesToString converts a Utsname byte array field to a Go string,
// stopping at the first null byte. Works for both int8 (Linux) and uint8 fields.
func utsnameBytesToString(arr [65]int8) string {
	buf := make([]byte, 0, len(arr))
	for _, b := range arr {
		if b == 0 {
			break
		}
		buf = append(buf, byte(b))
	}
	return string(buf)
}
