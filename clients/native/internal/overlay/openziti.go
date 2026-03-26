package overlay

import (
	"context"
	"fmt"
)

type openZitiProvider struct {
	cfg OpenZitiConfig
}

func (o *openZitiProvider) Connect(_ context.Context) error {
	return fmt.Errorf("OpenZiti provider not yet implemented")
}

func (o *openZitiProvider) Disconnect(_ context.Context) error {
	return fmt.Errorf("OpenZiti provider not yet implemented")
}

func (o *openZitiProvider) Status(_ context.Context) (ProviderStatus, error) {
	return ProviderStatus{Connected: false}, nil
}
