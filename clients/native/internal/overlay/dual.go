package overlay

import (
	"context"
	"fmt"
)

type dualProvider struct {
	primary   OverlayProvider
	secondary OverlayProvider
}

func (d *dualProvider) Connect(ctx context.Context) error {
	if err := d.primary.Connect(ctx); err != nil {
		return d.secondary.Connect(ctx)
	}
	return nil
}

func (d *dualProvider) Disconnect(ctx context.Context) error {
	err1 := d.primary.Disconnect(ctx)
	err2 := d.secondary.Disconnect(ctx)
	if err1 != nil && err2 != nil {
		return fmt.Errorf("primary: %w; secondary: %v", err1, err2)
	}
	if err1 != nil {
		return err1
	}
	return err2
}

func (d *dualProvider) Status(ctx context.Context) (ProviderStatus, error) {
	if status, err := d.primary.Status(ctx); err == nil && status.Connected {
		return status, nil
	}
	return d.secondary.Status(ctx)
}
