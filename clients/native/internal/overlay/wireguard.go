package overlay

import (
	"context"
	"fmt"
	"os/exec"
	"runtime"
	"strings"
)

type wireguardProvider struct {
	cfg WireGuardConfig
}

func (w *wireguardProvider) Connect(ctx context.Context) error {
	if err := w.writeConfig(); err != nil {
		return fmt.Errorf("write wireguard config: %w", err)
	}
	return w.runWgQuick(ctx, "up")
}

func (w *wireguardProvider) Disconnect(ctx context.Context) error {
	return w.runWgQuick(ctx, "down")
}

func (w *wireguardProvider) Status(ctx context.Context) (ProviderStatus, error) {
	cmd := exec.CommandContext(ctx, "wg", "show", w.cfg.Interface)
	out, err := cmd.Output()
	if err != nil {
		return ProviderStatus{Connected: false}, nil
	}
	return ProviderStatus{
		Connected: strings.Contains(string(out), "latest handshake"),
	}, nil
}

func (w *wireguardProvider) writeConfig() error {
	// Config writing to /etc/wireguard/{interface}.conf (or platform equivalent)
	// Placeholder until full config write is implemented
	return nil
}

func (w *wireguardProvider) runWgQuick(ctx context.Context, action string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.CommandContext(ctx, "wg-quick.exe", action, w.cfg.Interface)
	default:
		cmd = exec.CommandContext(ctx, "wg-quick", action, w.cfg.Interface)
	}
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("wg-quick %s %s: %w\n%s", action, w.cfg.Interface, err, out)
	}
	return nil
}
