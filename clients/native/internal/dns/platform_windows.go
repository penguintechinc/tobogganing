//go:build windows

package dns

import (
	"fmt"
	"os/exec"
)

// ConfigureSystemDNS sets a static DNS server address for the Wi-Fi
// interface using the Windows netsh utility.
//
// NOTE: This requires the process to be running with Administrator privileges.
func ConfigureSystemDNS(listenAddr string) error {
	cmd := exec.Command(
		"netsh", "interface", "ip", "set", "dns",
		"name=Wi-Fi", "static", listenAddr,
	)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("netsh set dns failed: %v — output: %s", err, output)
	}
	return nil
}

// RestoreSystemDNS reverts the Wi-Fi interface to DHCP-assigned DNS by
// setting the DNS source back to "dhcp" via netsh.
func RestoreSystemDNS() error {
	cmd := exec.Command(
		"netsh", "interface", "ip", "set", "dns",
		"name=Wi-Fi", "dhcp",
	)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("netsh restore dns failed: %v — output: %s", err, output)
	}
	return nil
}
