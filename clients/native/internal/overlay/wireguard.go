package overlay

import "context"

type wireguardProvider struct {
	connectFn    func() error
	disconnectFn func() error
	connected    bool
}

func (w *wireguardProvider) Connect(_ context.Context) error {
	if err := w.connectFn(); err != nil {
		return err
	}
	w.connected = true
	return nil
}

func (w *wireguardProvider) Disconnect(_ context.Context) error {
	err := w.disconnectFn()
	w.connected = false
	return err
}

func (w *wireguardProvider) Status(_ context.Context) (ProviderStatus, error) {
	return ProviderStatus{Connected: w.connected}, nil
}
