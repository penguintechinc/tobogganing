package overlay

import (
	"context"
	"sync"
	"testing"
)

func TestNewOpenZitiProvider_ReturnsNonNil(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "/nonexistent/identity.json",
		ServiceName:  "test-service",
	})
	if p == nil {
		t.Fatal("expected non-nil provider")
	}
}

func TestOpenZitiProvider_ImplementsOpenZitiProvider(t *testing.T) {
	// Compile-time check.
	var _ OpenZitiProvider = NewOpenZitiProvider(OpenZitiConfig{})
}

func TestOpenZitiProvider_ImplementsOverlayProvider(t *testing.T) {
	var _ OverlayProvider = NewOpenZitiProvider(OpenZitiConfig{})
}

func TestOpenZitiProvider_Status_DisconnectedByDefault(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "/nonexistent/identity.json",
		ServiceName:  "test-service",
	})

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false before any Connect call")
	}
}

func TestOpenZitiProvider_Connect_MissingIdentityFile_ReturnsError(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "/absolutely/nonexistent/identity_file_xyz_12345.json",
		ServiceName:  "test-service",
	})

	err := p.Connect(context.Background())
	if err == nil {
		t.Fatal("expected error when identity file does not exist")
	}
}

func TestOpenZitiProvider_Connect_EmptyIdentityFile_ReturnsError(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "",
		ServiceName:  "test-service",
	})

	err := p.Connect(context.Background())
	if err == nil {
		t.Fatal("expected error when identity file path is empty")
	}
}

func TestOpenZitiProvider_SetJWTToken_UpdatesToken(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{})

	// Should not panic or error.
	p.SetJWTToken("test-jwt-token-value")

	// Verify the token was stored (access internal field via type assertion).
	impl, ok := p.(*openZitiProvider)
	if !ok {
		t.Fatal("type assertion to *openZitiProvider failed")
	}
	impl.mu.Lock()
	got := impl.jwtToken
	impl.mu.Unlock()

	if got != "test-jwt-token-value" {
		t.Errorf("expected jwtToken=%q, got %q", "test-jwt-token-value", got)
	}
}

func TestOpenZitiProvider_SetJWTToken_EmptyToken(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{})
	// Should not panic.
	p.SetJWTToken("")

	impl := p.(*openZitiProvider)
	impl.mu.Lock()
	got := impl.jwtToken
	impl.mu.Unlock()

	if got != "" {
		t.Errorf("expected empty jwtToken, got %q", got)
	}
}

func TestOpenZitiProvider_SetJWTToken_Concurrent(t *testing.T) {
	// Run with -race to detect data races.
	p := NewOpenZitiProvider(OpenZitiConfig{})

	const goroutines = 50
	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func(n int) {
			defer wg.Done()
			p.SetJWTToken("token-value")
		}(i)
	}
	wg.Wait()
}

func TestOpenZitiProvider_Disconnect_WhenNotConnected_NoError(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "/nonexistent/file.json",
		ServiceName:  "test",
	})

	// Disconnecting without ever connecting should not error.
	err := p.Disconnect(context.Background())
	if err != nil {
		t.Errorf("expected no error disconnecting when not connected, got: %v", err)
	}
}

func TestOpenZitiProvider_Status_AfterFailedConnect_StillDisconnected(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "/nonexistent/identity.json",
		ServiceName:  "test-service",
	})

	_ = p.Connect(context.Background()) // Will fail

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false after failed Connect")
	}
}

func TestOpenZitiProvider_Status_Concurrent(t *testing.T) {
	// Run with -race.
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "/nonexistent/identity.json",
	})

	const goroutines = 20
	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			_, _ = p.Status(context.Background())
		}()
	}
	wg.Wait()
}
