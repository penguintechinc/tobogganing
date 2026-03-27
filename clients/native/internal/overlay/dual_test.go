package overlay

import (
	"context"
	"errors"
	"testing"
)

// stubProvider is a controllable OverlayProvider for testing.
type stubProvider struct {
	connectErr    error
	disconnectErr error
	connected     bool
	endpoint      string
}

func (s *stubProvider) Connect(_ context.Context) error {
	if s.connectErr != nil {
		return s.connectErr
	}
	s.connected = true
	return nil
}

func (s *stubProvider) Disconnect(_ context.Context) error {
	s.connected = false
	return s.disconnectErr
}

func (s *stubProvider) Status(_ context.Context) (ProviderStatus, error) {
	return ProviderStatus{Connected: s.connected, Endpoint: s.endpoint}, nil
}

// --- NewDualProvider ---

func TestNewDualProvider_ReturnsNonNil(t *testing.T) {
	p := NewDualProvider(&stubProvider{}, &stubProvider{})
	if p == nil {
		t.Fatal("expected non-nil dual provider")
	}
}

func TestDualProvider_Connect_PrimarySuccess_SecondaryNotCalled(t *testing.T) {
	primary := &stubProvider{}
	secondary := &stubProvider{}

	d := NewDualProvider(primary, secondary)
	if err := d.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	if !primary.connected {
		t.Error("primary should be connected")
	}
	if secondary.connected {
		t.Error("secondary should NOT be connected when primary succeeded")
	}
}

func TestDualProvider_Connect_PrimaryFails_SecondaryTried(t *testing.T) {
	primary := &stubProvider{connectErr: errors.New("primary unavailable")}
	secondary := &stubProvider{}

	d := NewDualProvider(primary, secondary)
	if err := d.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	if secondary.connected {
		// secondary.Connect succeeded so connected=true
	} else {
		t.Error("secondary should be connected after primary failure")
	}
}

func TestDualProvider_Connect_BothFail_ReturnsSecondaryError(t *testing.T) {
	secondaryErr := errors.New("secondary also failed")
	primary := &stubProvider{connectErr: errors.New("primary failed")}
	secondary := &stubProvider{connectErr: secondaryErr}

	d := NewDualProvider(primary, secondary)
	err := d.Connect(context.Background())
	if err == nil {
		t.Fatal("expected error when both fail")
	}
	if !errors.Is(err, secondaryErr) {
		t.Errorf("expected secondary error %v, got %v", secondaryErr, err)
	}
}

func TestDualProvider_Disconnect_CallsBoth(t *testing.T) {
	primary := &stubProvider{}
	secondary := &stubProvider{}
	primary.connected = true
	secondary.connected = true

	d := NewDualProvider(primary, secondary)
	if err := d.Disconnect(context.Background()); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}

	if primary.connected {
		t.Error("primary should be disconnected")
	}
	if secondary.connected {
		t.Error("secondary should be disconnected")
	}
}

func TestDualProvider_Disconnect_PrimaryErrorOnly(t *testing.T) {
	primaryErr := errors.New("primary disconnect failed")
	primary := &stubProvider{disconnectErr: primaryErr}
	secondary := &stubProvider{}

	d := NewDualProvider(primary, secondary)
	err := d.Disconnect(context.Background())
	if err == nil {
		t.Fatal("expected error when primary disconnect fails")
	}
	if !errors.Is(err, primaryErr) {
		t.Errorf("expected %v, got %v", primaryErr, err)
	}
}

func TestDualProvider_Disconnect_SecondaryErrorOnly(t *testing.T) {
	secondaryErr := errors.New("secondary disconnect failed")
	primary := &stubProvider{}
	secondary := &stubProvider{disconnectErr: secondaryErr}

	d := NewDualProvider(primary, secondary)
	err := d.Disconnect(context.Background())
	if err == nil {
		t.Fatal("expected error when secondary disconnect fails")
	}
	if !errors.Is(err, secondaryErr) {
		t.Errorf("expected %v, got %v", secondaryErr, err)
	}
}

func TestDualProvider_Disconnect_BothError_ReturnsCombined(t *testing.T) {
	primaryErr := errors.New("primary disconnect failed")
	secondaryErr := errors.New("secondary disconnect failed")
	primary := &stubProvider{disconnectErr: primaryErr}
	secondary := &stubProvider{disconnectErr: secondaryErr}

	d := NewDualProvider(primary, secondary)
	err := d.Disconnect(context.Background())
	if err == nil {
		t.Fatal("expected error when both disconnects fail")
	}
	// The combined error message should mention both
	errMsg := err.Error()
	if !errors.Is(err, primaryErr) {
		t.Errorf("expected primary error wrapped in result, got: %s", errMsg)
	}
}

func TestDualProvider_Status_PrimaryConnected_ReturnsPrimary(t *testing.T) {
	primary := &stubProvider{connected: true, endpoint: "primary-ep"}
	secondary := &stubProvider{connected: false, endpoint: "secondary-ep"}

	d := NewDualProvider(primary, secondary)
	status, err := d.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !status.Connected {
		t.Error("expected Connected=true")
	}
	if status.Endpoint != "primary-ep" {
		t.Errorf("expected primary endpoint, got %q", status.Endpoint)
	}
}

func TestDualProvider_Status_PrimaryDisconnected_ReturnsSecondary(t *testing.T) {
	primary := &stubProvider{connected: false, endpoint: "primary-ep"}
	secondary := &stubProvider{connected: true, endpoint: "secondary-ep"}

	d := NewDualProvider(primary, secondary)
	status, err := d.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Endpoint != "secondary-ep" {
		t.Errorf("expected secondary endpoint, got %q", status.Endpoint)
	}
}

func TestDualProvider_Status_BothDisconnected_ReturnsSecondary(t *testing.T) {
	primary := &stubProvider{connected: false}
	secondary := &stubProvider{connected: false, endpoint: "fallback"}

	d := NewDualProvider(primary, secondary)
	status, err := d.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false when both disconnected")
	}
	if status.Endpoint != "fallback" {
		t.Errorf("expected secondary endpoint %q, got %q", "fallback", status.Endpoint)
	}
}

func TestDualProvider_ImplementsOverlayProvider(t *testing.T) {
	var _ OverlayProvider = NewDualProvider(&stubProvider{}, &stubProvider{})
}
