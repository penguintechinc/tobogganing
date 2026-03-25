//go:build linux

package dns

import (
	"fmt"
	"os"
)

const (
	resolvConf       = "/etc/resolv.conf"
	resolvConfBackup = "/etc/resolv.conf.tobogganing.bak"
)

// ConfigureSystemDNS updates /etc/resolv.conf to point at listenAddr.
// The original file is preserved at resolvConfBackup so that
// RestoreSystemDNS can reinstate it on disconnect.
//
// If a backup already exists (e.g. from a previous unclean shutdown) it is
// reused without overwriting, protecting the original configuration.
func ConfigureSystemDNS(listenAddr string) error {
	if _, err := os.Stat(resolvConfBackup); os.IsNotExist(err) {
		data, err := os.ReadFile(resolvConf)
		if err != nil {
			return fmt.Errorf("failed to read %s for backup: %w", resolvConf, err)
		}
		if err := os.WriteFile(resolvConfBackup, data, 0644); err != nil {
			return fmt.Errorf("failed to write backup to %s: %w", resolvConfBackup, err)
		}
	}

	content := fmt.Sprintf("# Tobogganing DNS — managed file, do not edit\nnameserver %s\n", listenAddr)
	if err := os.WriteFile(resolvConf, []byte(content), 0644); err != nil {
		return fmt.Errorf("failed to write %s: %w", resolvConf, err)
	}
	return nil
}

// RestoreSystemDNS reinstates the original /etc/resolv.conf from the backup
// created by ConfigureSystemDNS and removes the backup file.
// If no backup exists the function returns without error (idempotent).
func RestoreSystemDNS() error {
	if _, err := os.Stat(resolvConfBackup); err != nil {
		// No backup — nothing to restore.
		return nil
	}

	data, err := os.ReadFile(resolvConfBackup)
	if err != nil {
		return fmt.Errorf("failed to read backup %s: %w", resolvConfBackup, err)
	}
	if err := os.WriteFile(resolvConf, data, 0644); err != nil {
		return fmt.Errorf("failed to restore %s: %w", resolvConf, err)
	}
	if err := os.Remove(resolvConfBackup); err != nil {
		return fmt.Errorf("failed to remove backup %s: %w", resolvConfBackup, err)
	}
	return nil
}
