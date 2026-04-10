package overlay

import (
	"context"
	"errors"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/openziti/sdk-golang/ziti/edge"
)

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

// fakeAddr implements net.Addr.
type fakeAddr struct{ addr string }

func (a fakeAddr) Network() string { return "tcp" }
func (a fakeAddr) String() string  { return a.addr }

// fakeConn implements net.Conn for testing. All operations are no-ops except
// Close (which records the call and returns closeErr) and RemoteAddr.
type fakeConn struct {
	remoteAddr net.Addr
	closeErr   error
	closed     bool
}

func (c *fakeConn) Read(_ []byte) (int, error)        { return 0, nil }
func (c *fakeConn) Write(b []byte) (int, error)       { return len(b), nil }
func (c *fakeConn) Close() error                      { c.closed = true; return c.closeErr }
func (c *fakeConn) LocalAddr() net.Addr               { return nil }
func (c *fakeConn) RemoteAddr() net.Addr              { return c.remoteAddr }
func (c *fakeConn) SetDeadline(_ time.Time) error     { return nil }
func (c *fakeConn) SetReadDeadline(_ time.Time) error  { return nil }
func (c *fakeConn) SetWriteDeadline(_ time.Time) error { return nil }

// mockZitiContext is a controllable ZitiContext for testing.
type mockZitiContext struct {
	authenticateErr error
	dialErr         error
	dialConn        net.Conn
	closeCalled     bool
}

func (m *mockZitiContext) Authenticate() error { return m.authenticateErr }
func (m *mockZitiContext) Dial(_ string) (net.Conn, error) {
	if m.dialErr != nil {
		return nil, m.dialErr
	}
	return m.dialConn, nil
}
func (m *mockZitiContext) Close() { m.closeCalled = true }

// factoryReturning builds a ZitiContextFactory that always returns the given context.
func factoryReturning(ctx ZitiContext) ZitiContextFactory {
	return func(_ string) (ZitiContext, error) { return ctx, nil }
}

// factoryFailing builds a ZitiContextFactory that always returns the given error.
func factoryFailing(err error) ZitiContextFactory {
	return func(_ string) (ZitiContext, error) { return nil, err }
}

// ---------------------------------------------------------------------------
// mockInnerZiti implements innerZitiContext for adapter unit tests.
// ---------------------------------------------------------------------------

type mockInnerZiti struct {
	authenticateErr error
	dialErr         error
	dialResult      edge.Conn
	closeCalled     bool
}

func (m *mockInnerZiti) Authenticate() error { return m.authenticateErr }
func (m *mockInnerZiti) Dial(_ string) (edge.Conn, error) {
	return m.dialResult, m.dialErr
}
func (m *mockInnerZiti) Close() { m.closeCalled = true }

// ---------------------------------------------------------------------------
// zitiContextAdapter unit tests — exercises the 3 delegation methods directly.
// ---------------------------------------------------------------------------

func TestZitiContextAdapter_Authenticate_Success(t *testing.T) {
	inner := &mockInnerZiti{}
	a := &zitiContextAdapter{inner: inner}
	if err := a.Authenticate(); err != nil {
		t.Errorf("expected nil, got %v", err)
	}
}

func TestZitiContextAdapter_Authenticate_Error(t *testing.T) {
	authErr := errors.New("auth error")
	inner := &mockInnerZiti{authenticateErr: authErr}
	a := &zitiContextAdapter{inner: inner}
	err := a.Authenticate()
	if !errors.Is(err, authErr) {
		t.Errorf("expected authErr, got %v", err)
	}
}

func TestZitiContextAdapter_Dial_Success(t *testing.T) {
	inner := &mockInnerZiti{dialResult: nil} // nil edge.Conn is valid for a no-op check
	a := &zitiContextAdapter{inner: inner}
	conn, err := a.Dial("test-service")
	if err != nil {
		t.Errorf("expected nil err, got %v", err)
	}
	_ = conn // may be nil
}

func TestZitiContextAdapter_Dial_Error(t *testing.T) {
	dialErr := errors.New("dial error")
	inner := &mockInnerZiti{dialErr: dialErr}
	a := &zitiContextAdapter{inner: inner}
	_, err := a.Dial("test-service")
	if !errors.Is(err, dialErr) {
		t.Errorf("expected dialErr, got %v", err)
	}
}

func TestZitiContextAdapter_Close(t *testing.T) {
	inner := &mockInnerZiti{}
	a := &zitiContextAdapter{inner: inner}
	a.Close()
	if !inner.closeCalled {
		t.Error("expected inner.Close() to be called")
	}
}

// ---------------------------------------------------------------------------
// Interface / constructor tests
// ---------------------------------------------------------------------------

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
	var _ OpenZitiProvider = NewOpenZitiProvider(OpenZitiConfig{})
}

func TestOpenZitiProvider_ImplementsOverlayProvider(t *testing.T) {
	var _ OverlayProvider = NewOpenZitiProvider(OpenZitiConfig{})
}

func TestNewOpenZitiProviderWithFactory_ReturnsNonNil(t *testing.T) {
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{}, factoryFailing(errors.New("unused")))
	if p == nil {
		t.Fatal("expected non-nil provider")
	}
}

// ---------------------------------------------------------------------------
// Status tests
// ---------------------------------------------------------------------------

func TestOpenZitiProvider_Status_DisconnectedByDefault(t *testing.T) {
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{}, factoryFailing(errors.New("unused")))
	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false before any Connect call")
	}
	if status.Endpoint != "" {
		t.Errorf("expected empty Endpoint, got %q", status.Endpoint)
	}
}

func TestOpenZitiProvider_Status_ConnectedAfterSuccessfulConnect(t *testing.T) {
	conn := &fakeConn{remoteAddr: fakeAddr{"10.0.0.1:1234"}}
	mock := &mockZitiContext{dialConn: conn}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factoryReturning(mock))

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !status.Connected {
		t.Error("expected Connected=true after successful Connect")
	}
	if status.Endpoint != "10.0.0.1:1234" {
		t.Errorf("expected endpoint %q, got %q", "10.0.0.1:1234", status.Endpoint)
	}
}

func TestOpenZitiProvider_Status_ConnectedWithNilRemoteAddr(t *testing.T) {
	// conn.RemoteAddr() returns nil — endpoint should be empty.
	conn := &fakeConn{remoteAddr: nil}
	mock := &mockZitiContext{dialConn: conn}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factoryReturning(mock))

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if !status.Connected {
		t.Error("expected Connected=true")
	}
	if status.Endpoint != "" {
		t.Errorf("expected empty Endpoint when RemoteAddr is nil, got %q", status.Endpoint)
	}
}

func TestOpenZitiProvider_Status_DisconnectedInitially(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{})
	status, err := p.Status(context.Background())
	if err != nil {
		t.Errorf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected not connected on fresh provider")
	}
}

// ---------------------------------------------------------------------------
// Connect success path
// ---------------------------------------------------------------------------

func TestOpenZitiProvider_Connect_Success(t *testing.T) {
	conn := &fakeConn{remoteAddr: fakeAddr{"10.0.0.2:9999"}}
	mock := &mockZitiContext{dialConn: conn}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "my-service"}, factoryReturning(mock))

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
}

func TestOpenZitiProvider_Connect_IdempotentWhenAlreadyConnected(t *testing.T) {
	callCount := 0
	conn := &fakeConn{}
	mock := &mockZitiContext{dialConn: conn}
	factory := func(_ string) (ZitiContext, error) {
		callCount++
		return mock, nil
	}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factory)

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("first Connect: %v", err)
	}
	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("second Connect: %v", err)
	}

	// Factory should only be called once because the second call is a no-op.
	if callCount != 1 {
		t.Errorf("expected factory called once, got %d", callCount)
	}
}

// ---------------------------------------------------------------------------
// Connect failure paths
// ---------------------------------------------------------------------------

func TestOpenZitiProvider_Connect_FactoryError_ReturnsError(t *testing.T) {
	factoryErr := errors.New("identity file not found")
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{IdentityFile: "/bad/path.json"}, factoryFailing(factoryErr))

	err := p.Connect(context.Background())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, factoryErr) {
		t.Errorf("expected factory error wrapped, got %v", err)
	}
}

func TestOpenZitiProvider_Connect_AuthenticateError_ReturnsError(t *testing.T) {
	authErr := errors.New("auth failed")
	mock := &mockZitiContext{authenticateErr: authErr}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{}, factoryReturning(mock))

	err := p.Connect(context.Background())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, authErr) {
		t.Errorf("expected auth error wrapped, got %v", err)
	}
}

func TestOpenZitiProvider_Connect_DialError_ReturnsError(t *testing.T) {
	dialErr := errors.New("service unreachable")
	mock := &mockZitiContext{dialErr: dialErr}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factoryReturning(mock))

	err := p.Connect(context.Background())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, dialErr) {
		t.Errorf("expected dial error wrapped, got %v", err)
	}
}

func TestOpenZitiProvider_Connect_DialError_LeavesDisconnected(t *testing.T) {
	dialErr := errors.New("service unreachable")
	mock := &mockZitiContext{dialErr: dialErr}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factoryReturning(mock))

	_ = p.Connect(context.Background())

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false after failed dial")
	}
}

func TestOpenZitiProvider_Connect_MissingIdentityFile_ReturnsError(t *testing.T) {
	// Uses the real default factory — no live service, just file read failure.
	p := NewOpenZitiProvider(OpenZitiConfig{
		IdentityFile: "/absolutely/nonexistent/identity_file_xyz_12345.json",
		ServiceName:  "test-service",
	})
	if err := p.Connect(context.Background()); err == nil {
		t.Fatal("expected error when identity file does not exist")
	}
}

func TestOpenZitiProvider_Connect_EmptyIdentityFile_ReturnsError(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{IdentityFile: "", ServiceName: "test-service"})
	if err := p.Connect(context.Background()); err == nil {
		t.Fatal("expected error when identity file path is empty")
	}
}

func TestOpenZitiProvider_Status_AfterFailedConnect_StillDisconnected(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{IdentityFile: "/nonexistent/identity.json"})
	_ = p.Connect(context.Background())

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false after failed Connect")
	}
}

// ---------------------------------------------------------------------------
// Disconnect tests
// ---------------------------------------------------------------------------

func TestOpenZitiProvider_Disconnect_WhenNotConnected_NoError(t *testing.T) {
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{}, factoryFailing(errors.New("unused")))
	if err := p.Disconnect(context.Background()); err != nil {
		t.Errorf("expected no error disconnecting when not connected, got: %v", err)
	}
}

func TestOpenZitiProvider_Disconnect_ClosesConnAndContext(t *testing.T) {
	conn := &fakeConn{}
	mock := &mockZitiContext{dialConn: conn}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factoryReturning(mock))

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if err := p.Disconnect(context.Background()); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}

	if !conn.closed {
		t.Error("expected conn.Close() to be called")
	}
	if !mock.closeCalled {
		t.Error("expected ZitiContext.Close() to be called")
	}
}

func TestOpenZitiProvider_Disconnect_SetsDisconnected(t *testing.T) {
	conn := &fakeConn{}
	mock := &mockZitiContext{dialConn: conn}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factoryReturning(mock))

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if err := p.Disconnect(context.Background()); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}

	status, err := p.Status(context.Background())
	if err != nil {
		t.Fatalf("Status: %v", err)
	}
	if status.Connected {
		t.Error("expected Connected=false after Disconnect")
	}
}

func TestOpenZitiProvider_Disconnect_ConnCloseError_Propagates(t *testing.T) {
	closeErr := errors.New("close failed")
	conn := &fakeConn{closeErr: closeErr}
	mock := &mockZitiContext{dialConn: conn}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factoryReturning(mock))

	if err := p.Connect(context.Background()); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	err := p.Disconnect(context.Background())
	if err == nil {
		t.Fatal("expected error from conn.Close()")
	}
	if !errors.Is(err, closeErr) {
		t.Errorf("expected closeErr wrapped, got %v", err)
	}
	// ZitiContext.Close should still have been called even when conn.Close errors.
	if !mock.closeCalled {
		t.Error("expected ZitiContext.Close() to be called even on conn.Close error")
	}
}

func TestOpenZitiProvider_Disconnect_Idempotent(t *testing.T) {
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{}, factoryFailing(errors.New("unused")))
	for i := 0; i < 3; i++ {
		if err := p.Disconnect(context.Background()); err != nil {
			t.Errorf("Disconnect #%d: %v", i+1, err)
		}
	}
}

func TestOpenZitiProvider_ConnectThenDisconnectThenConnect(t *testing.T) {
	calls := 0
	factory := func(_ string) (ZitiContext, error) {
		calls++
		return &mockZitiContext{dialConn: &fakeConn{}}, nil
	}
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{ServiceName: "svc"}, factory)
	ctx := context.Background()

	if err := p.Connect(ctx); err != nil {
		t.Fatalf("first Connect: %v", err)
	}
	if err := p.Disconnect(ctx); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}
	// After disconnect the provider should accept a new connect.
	if err := p.Connect(ctx); err != nil {
		t.Fatalf("second Connect: %v", err)
	}
	if calls != 2 {
		t.Errorf("expected factory called 2 times, got %d", calls)
	}
}

// ---------------------------------------------------------------------------
// SetJWTToken tests
// ---------------------------------------------------------------------------

func TestOpenZitiProvider_SetJWTToken_UpdatesToken(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{})
	p.SetJWTToken("test-jwt-token-value")

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
	p.SetJWTToken("")

	impl, ok := p.(*openZitiProvider)
	if !ok {
		t.Fatal("type assertion to *openZitiProvider failed")
	}
	impl.mu.Lock()
	got := impl.jwtToken
	impl.mu.Unlock()
	if got != "" {
		t.Errorf("expected empty jwtToken, got %q", got)
	}
}

func TestOpenZitiProvider_SetJWTToken_Multiple(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{})
	for i := 0; i < 10; i++ {
		p.SetJWTToken("token-" + string(rune(48+i)))
	}
	impl, _ := p.(*openZitiProvider)
	impl.mu.Lock()
	defer impl.mu.Unlock()
	if impl.jwtToken == "" {
		t.Error("jwtToken should be set after SetJWTToken calls")
	}
}

// ---------------------------------------------------------------------------
// Concurrency tests (run with -race)
// ---------------------------------------------------------------------------

func TestOpenZitiProvider_SetJWTToken_Concurrent(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{})
	const goroutines = 50
	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			p.SetJWTToken("token-value")
		}()
	}
	wg.Wait()
}

func TestOpenZitiProvider_Status_Concurrent(t *testing.T) {
	p := NewOpenZitiProviderWithFactory(OpenZitiConfig{}, factoryFailing(errors.New("unused")))
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

func TestOpenZitiProvider_SetJWTToken_ConcurrentWithStatus(t *testing.T) {
	p := NewOpenZitiProvider(OpenZitiConfig{})
	const routines = 30
	var wg sync.WaitGroup
	wg.Add(routines * 2)
	for i := 0; i < routines; i++ {
		go func() {
			defer wg.Done()
			p.SetJWTToken("token-value")
		}()
	}
	for i := 0; i < routines; i++ {
		go func() {
			defer wg.Done()
			_, _ = p.Status(context.Background())
		}()
	}
	wg.Wait()
}
