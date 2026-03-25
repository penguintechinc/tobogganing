//go:build darwin

package dns

import (
	"fmt"
	"os/exec"
)

// ConfigureSystemDNS sets the DNS server for the primary Wi-Fi network
// service to listenAddr using the macOS networksetup utility.
//
// NOTE: This requires the process to be running as root or with the
// com.apple.security.network.client entitlement and appropriate sudo rules.
func ConfigureSystemDNS(listenAddr string) error {
	cmd := exec.Command("networksetup", "-setdnsservers", "Wi-Fi", listenAddr)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("networksetup -setdnsservers failed: %v — output: %s", err, output)
	}
	return nil
}

// RestoreSystemDNS clears any custom DNS servers from the Wi-Fi service,
// reverting to the network-provided (DHCP) DNS configuration.
func RestoreSystemDNS() error {
	cmd := exec.Command("networksetup", "-setdnsservers", "Wi-Fi", "Empty")
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("networksetup -setdnsservers Empty failed: %v — output: %s", err, output)
	}
	return nil
}
