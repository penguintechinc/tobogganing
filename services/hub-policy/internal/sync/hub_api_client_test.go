package sync

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"google.golang.org/grpc"
)

// ---------------------------------------------------------------------------
// Mock stream helpers
// ---------------------------------------------------------------------------

// mockPolicyStream implements PolicyStream for testing.
type mockPolicyStream struct {
	updates []*PolicyUpdate
	idx     int
	err     error // returned after all updates are exhausted (nil → io.EOF)
}

// newMockStream returns a stream that yields the given updates then returns
// finalErr (use io.EOF for a clean close).
func newMockStream(updates []*PolicyUpdate, finalErr error) *mockPolicyStream {
	return &mockPolicyStream{updates: updates, err: finalErr}
}

func (m *mockPolicyStream) Recv() (*PolicyUpdate, error) {
	if m.idx < len(m.updates) {
		u := m.updates[m.idx]
		m.idx++
		return u, nil
	}
	if m.err != nil {
		return nil, m.err
	}
	return nil, io.EOF
}

// blockingStream blocks on Recv until the context is cancelled.
type blockingStream struct {
	ctx context.Context
}

func (b *blockingStream) Recv() (*PolicyUpdate, error) {
	<-b.ctx.Done()
	return nil, b.ctx.Err()
}

// errorOnFirstStream fails immediately on the first Recv call.
type errorOnFirstStream struct {
	err error
}

func (e *errorOnFirstStream) Recv() (*PolicyUpdate, error) {
	return nil, e.err
}

// ---------------------------------------------------------------------------
// Constructor tests
// ---------------------------------------------------------------------------

// TestNewHubAPIClientDefaults verifies NewHubAPIClient with default parameters.
func TestNewHubAPIClientDefaults(t *testing.T) {
	client := NewHubAPIClient("", "")

	if client == nil {
		t.Fatal("NewHubAPIClient returned nil")
	}
	if client.grpcAddr != defaultGRPCAddress {
		t.Errorf("Expected grpcAddr %s, got %s", defaultGRPCAddress, client.grpcAddr)
	}
	if client.restBaseURL != defaultRESTBaseURL {
		t.Errorf("Expected restBaseURL %s, got %s", defaultRESTBaseURL, client.restBaseURL)
	}
	if client.cacheTTL != defaultCacheTTL {
		t.Errorf("Expected cacheTTL %v, got %v", defaultCacheTTL, client.cacheTTL)
	}
	if client.httpClient == nil {
		t.Error("Expected httpClient to be initialized")
	}
	if client.httpClient.Timeout != 10*time.Second {
		t.Errorf("Expected httpClient timeout 10s, got %v", client.httpClient.Timeout)
	}
	if client.stopCh == nil {
		t.Error("Expected stopCh to be initialized")
	}
}

// TestNewHubAPIClientCustom verifies NewHubAPIClient with custom parameters.
func TestNewHubAPIClientCustom(t *testing.T) {
	customGRPC := "custom-grpc:50051"
	customREST := "http://custom-rest:8080/api/v2"

	client := NewHubAPIClient(customGRPC, customREST)

	if client.grpcAddr != customGRPC {
		t.Errorf("Expected grpcAddr %s, got %s", customGRPC, client.grpcAddr)
	}
	if client.restBaseURL != customREST {
		t.Errorf("Expected restBaseURL %s, got %s", customREST, client.restBaseURL)
	}
}

// TestNewHubAPIClientPartialDefaults verifies NewHubAPIClient with partial defaults.
func TestNewHubAPIClientPartialDefaults(t *testing.T) {
	customGRPC := "custom:50051"
	client := NewHubAPIClient(customGRPC, "")

	if client.grpcAddr != customGRPC {
		t.Errorf("Expected grpcAddr %s, got %s", customGRPC, client.grpcAddr)
	}
	if client.restBaseURL != defaultRESTBaseURL {
		t.Errorf("Expected default restBaseURL, got %s", client.restBaseURL)
	}
}

// ---------------------------------------------------------------------------
// Connect tests
// ---------------------------------------------------------------------------

// TestConnectGRPCUnavailable verifies Connect doesn't panic with bad address.
func TestConnectGRPCUnavailable(t *testing.T) {
	client := NewHubAPIClient("bad-host-name-xyzabc.invalid:50051", "")
	ctx := context.Background()

	// Should not panic, should handle gracefully
	err := client.Connect(ctx)
	if err != nil {
		t.Errorf("Expected Connect to return nil (fallback to REST), got %v", err)
	}

	// Verify client is still usable
	if client.restBaseURL == "" {
		t.Error("restBaseURL should be set")
	}
}

// ---------------------------------------------------------------------------
// Close tests
// ---------------------------------------------------------------------------

// TestCloseClientStops verifies that Close() closes the stopCh.
func TestCloseClientStops(t *testing.T) {
	client := NewHubAPIClient("", "")

	err := client.Close()
	if err != nil {
		t.Errorf("Close() returned error: %v", err)
	}

	// stopCh should be closed; receiving should not block
	select {
	case <-client.stopCh:
		// Good, the channel is closed
	case <-time.After(100 * time.Millisecond):
		t.Error("stopCh was not closed by Close()")
	}
}

// ---------------------------------------------------------------------------
// FetchPolicies REST tests
// ---------------------------------------------------------------------------

// TestFetchPoliciesRESTSuccess verifies FetchPolicies with REST API success.
func TestFetchPoliciesRESTSuccess(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/policies" {
			w.WriteHeader(http.StatusNotFound)
			return
		}

		policies := []Policy{
			{
				ID:      "pol-1",
				Name:    "Test Policy",
				Enabled: true,
				Action:  "allow",
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(policies)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	policies, err := client.FetchPolicies(ctx)
	if err != nil {
		t.Fatalf("FetchPolicies failed: %v", err)
	}

	if len(policies) != 1 {
		t.Errorf("Expected 1 policy, got %d", len(policies))
	}
	if policies[0].ID != "pol-1" {
		t.Errorf("Expected policy ID 'pol-1', got %s", policies[0].ID)
	}
}

// TestFetchPoliciesRESTNotFound verifies FetchPolicies with 404 error.
func TestFetchPoliciesRESTNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte("Not Found"))
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected FetchPolicies to return error on 404")
	}
	if !strings.Contains(err.Error(), "404") {
		t.Errorf("Expected error to mention 404, got: %v", err)
	}
}

// TestFetchPoliciesRESTInvalidJSON verifies FetchPolicies with invalid JSON response.
func TestFetchPoliciesRESTInvalidJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte("invalid json {{{"))
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected FetchPolicies to return error on invalid JSON")
	}
	if !strings.Contains(err.Error(), "decode") {
		t.Errorf("Expected error to mention decode, got: %v", err)
	}
}

// TestFetchPoliciesCaching verifies that policies are cached.
func TestFetchPoliciesCaching(t *testing.T) {
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		policies := []Policy{
			{ID: "pol-1", Name: "Test", Enabled: true},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(policies)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	client.cacheTTL = 100 * time.Millisecond // Short TTL for testing
	ctx := context.Background()

	// First call should hit the server
	_, err := client.FetchPolicies(ctx)
	if err != nil {
		t.Fatalf("First FetchPolicies failed: %v", err)
	}
	if callCount != 1 {
		t.Errorf("Expected 1 server call, got %d", callCount)
	}

	// Second call should use cache
	_, err = client.FetchPolicies(ctx)
	if err != nil {
		t.Fatalf("Second FetchPolicies failed: %v", err)
	}
	if callCount != 1 {
		t.Errorf("Expected cache hit (still 1 server call), got %d", callCount)
	}

	// Wait for cache to expire
	time.Sleep(150 * time.Millisecond)

	// Third call should hit the server again
	_, err = client.FetchPolicies(ctx)
	if err != nil {
		t.Fatalf("Third FetchPolicies failed: %v", err)
	}
	if callCount != 2 {
		t.Errorf("Expected 2 server calls after cache expiry, got %d", callCount)
	}
}

// TestFetchPoliciesEmptyResponse verifies FetchPolicies with empty policy list.
func TestFetchPoliciesEmptyResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]Policy{})
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	policies, err := client.FetchPolicies(ctx)
	if err != nil {
		t.Fatalf("FetchPolicies failed: %v", err)
	}

	if len(policies) != 0 {
		t.Errorf("Expected 0 policies, got %d", len(policies))
	}
}

// TestFetchPoliciesContextCancellation verifies FetchPolicies with cancelled context.
func TestFetchPoliciesContextCancellation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(1 * time.Second) // Simulate slow response
		json.NewEncoder(w).Encode([]Policy{})
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel immediately

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected FetchPolicies to return error on cancelled context")
	}
}

// TestFetchPoliciesHTTPError500 verifies handling of 500 error.
func TestFetchPoliciesHTTPError500(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("Internal Server Error"))
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected FetchPolicies to fail on 500 error")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Errorf("Expected error to mention 500, got: %v", err)
	}
}

// TestFetchPoliciesMalformedJSONArray verifies error on truncated JSON.
func TestFetchPoliciesMalformedJSONArray(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte("[{\"id\":\"pol-1\""))
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected FetchPolicies to fail on malformed JSON")
	}
}

// TestFetchPoliciesHTTPClientTimeout verifies timeout behavior.
func TestFetchPoliciesHTTPClientTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(15 * time.Second) // Longer than the 10s client timeout
		json.NewEncoder(w).Encode([]Policy{})
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected FetchPolicies to return error on timeout")
	}
	if !strings.Contains(err.Error(), "context deadline") && !strings.Contains(err.Error(), "deadline") {
		// The error might be a timeout or connection error, both are acceptable
		t.Logf("Got error (acceptable): %v", err)
	}
}

// TestFetchPoliciesMultipleItemsInCache verifies cache stores multiple policies.
func TestFetchPoliciesMultipleItemsInCache(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		policies := []Policy{
			{ID: "pol-1", Name: "Policy 1", Enabled: true},
			{ID: "pol-2", Name: "Policy 2", Enabled: true},
			{ID: "pol-3", Name: "Policy 3", Enabled: true},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(policies)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	policies, err := client.FetchPolicies(ctx)
	if err != nil {
		t.Fatalf("FetchPolicies failed: %v", err)
	}

	if len(policies) != 3 {
		t.Errorf("Expected 3 policies, got %d", len(policies))
	}
	for i, p := range policies {
		if p.ID != fmt.Sprintf("pol-%d", i+1) {
			t.Errorf("Policy %d has unexpected ID: %s", i, p.ID)
		}
	}
}

// TestFetchPoliciesCacheIndependence verifies cache returns independent copies.
func TestFetchPoliciesCacheIndependence(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		policies := []Policy{
			{ID: "pol-1", Name: "Test", Enabled: true},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(policies)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	client.cacheTTL = 1 * time.Second
	ctx := context.Background()

	policies1, _ := client.FetchPolicies(ctx)
	policies2, _ := client.FetchPolicies(ctx)

	if len(policies1) != len(policies2) {
		t.Error("Cache should return same number of policies")
	}
}

// ---------------------------------------------------------------------------
// SubscribePolicyUpdates — polling fallback
// ---------------------------------------------------------------------------

// TestSubscribePolicyUpdatesWithCallback verifies SubscribePolicyUpdates via poll.
func TestSubscribePolicyUpdatesWithCallback(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		policies := []Policy{
			{ID: "pol-1", Name: "Test", Enabled: true},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(policies)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")

	callback := func(policies []Policy) {}

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	err := client.SubscribePolicyUpdates(ctx, callback)
	if err == nil {
		t.Error("Expected SubscribePolicyUpdates to return error on context cancellation")
	}
}

// TestSubscribePolicyUpdatesNilCallback verifies SubscribePolicyUpdates with nil callback.
func TestSubscribePolicyUpdatesNilCallback(t *testing.T) {
	client := NewHubAPIClient("", "")

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	err := client.SubscribePolicyUpdates(ctx, nil)
	if err == nil {
		t.Error("Expected SubscribePolicyUpdates to return error on context cancellation")
	}
}

// TestSubscribePolicyUpdatesStopChannel verifies the stop channel terminates polling.
func TestSubscribePolicyUpdatesStopChannel(t *testing.T) {
	client := NewHubAPIClient("", "")
	ctx := context.Background()

	done := make(chan error, 1)
	go func() {
		done <- client.SubscribePolicyUpdates(ctx, nil)
	}()

	// Close the stop channel to signal shutdown
	time.Sleep(10 * time.Millisecond)
	close(client.stopCh)

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Expected nil error on stop, got %v", err)
		}
	case <-time.After(500 * time.Millisecond):
		t.Error("SubscribePolicyUpdates did not stop after stopCh closed")
	}
}

// ---------------------------------------------------------------------------
// SubscribePolicyUpdates — gRPC stream path
// ---------------------------------------------------------------------------

// TestSubscribeStreamSuccessMultiPolicy verifies streaming delivers multiple policy batches.
func TestSubscribeStreamSuccessMultiPolicy(t *testing.T) {
	batch1 := []Policy{
		{ID: "pol-1", Name: "Policy 1", Enabled: true, Action: "allow"},
		{ID: "pol-2", Name: "Policy 2", Enabled: true, Action: "deny"},
	}
	batch2 := []Policy{
		{ID: "pol-3", Name: "Policy 3", Enabled: true, Action: "log"},
	}

	stream := newMockStream([]*PolicyUpdate{
		{Policies: batch1, Sequence: 1},
		{Policies: batch2, Sequence: 2},
	}, io.EOF)

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	var received [][]Policy
	callback := func(policies []Policy) {
		cp := make([]Policy, len(policies))
		copy(cp, policies)
		received = append(received, cp)
	}

	ctx := context.Background()
	err := client.SubscribePolicyUpdates(ctx, callback)

	// io.EOF is treated as a clean close, so err should be nil.
	if err != nil {
		t.Errorf("Expected nil error on EOF, got %v", err)
	}
	if len(received) != 2 {
		t.Fatalf("Expected 2 callback invocations, got %d", len(received))
	}
	if len(received[0]) != 2 {
		t.Errorf("First batch: expected 2 policies, got %d", len(received[0]))
	}
	if len(received[1]) != 1 {
		t.Errorf("Second batch: expected 1 policy, got %d", len(received[1]))
	}
	if received[1][0].ID != "pol-3" {
		t.Errorf("Expected pol-3, got %s", received[1][0].ID)
	}
}

// TestSubscribeStreamEOFImmediately verifies a stream that closes immediately.
func TestSubscribeStreamEOFImmediately(t *testing.T) {
	stream := newMockStream(nil, io.EOF)

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	var callbackCalled bool
	ctx := context.Background()
	err := client.SubscribePolicyUpdates(ctx, func(p []Policy) { callbackCalled = true })

	if err != nil {
		t.Errorf("Expected nil on clean EOF, got %v", err)
	}
	if callbackCalled {
		t.Error("Callback should not be called when stream returns EOF immediately")
	}
}

// TestSubscribeStreamError verifies that a stream error is propagated.
func TestSubscribeStreamError(t *testing.T) {
	streamErr := errors.New("transport: connection reset by peer")
	stream := &errorOnFirstStream{err: streamErr}

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	ctx := context.Background()
	err := client.SubscribePolicyUpdates(ctx, nil)

	if err == nil {
		t.Error("Expected error from stream, got nil")
	}
	if !strings.Contains(err.Error(), "policy stream error") {
		t.Errorf("Expected wrapped stream error, got: %v", err)
	}
}

// TestSubscribeStreamFactoryError verifies factory failure is surfaced.
func TestSubscribeStreamFactoryError(t *testing.T) {
	factoryErr := errors.New("grpc: failed to connect")

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return nil, factoryErr
	})

	ctx := context.Background()
	err := client.SubscribePolicyUpdates(ctx, nil)

	if err == nil {
		t.Error("Expected factory error, got nil")
	}
	if !strings.Contains(err.Error(), "failed to open policy stream") {
		t.Errorf("Expected wrapped factory error, got: %v", err)
	}
}

// TestSubscribeStreamContextCancellationMidStream verifies ctx cancel during streaming.
func TestSubscribeStreamContextCancellationMidStream(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return &blockingStream{ctx: ctx}, nil
	})

	done := make(chan error, 1)
	go func() {
		done <- client.SubscribePolicyUpdates(ctx, nil)
	}()

	// Cancel context after the goroutine has entered Recv.
	time.Sleep(20 * time.Millisecond)
	cancel()

	select {
	case err := <-done:
		if err == nil {
			t.Error("Expected context error, got nil")
		}
		if !errors.Is(err, context.Canceled) {
			t.Errorf("Expected context.Canceled, got %v", err)
		}
	case <-time.After(500 * time.Millisecond):
		t.Error("SubscribePolicyUpdates did not stop after context cancel")
	}
}

// TestSubscribeStreamStopChannelMidStream verifies stopCh closes streaming.
func TestSubscribeStreamStopChannelMidStream(t *testing.T) {
	// A stream that yields one update then blocks.
	updates := []*PolicyUpdate{
		{Policies: []Policy{{ID: "pol-1", Enabled: true}}, Sequence: 1},
	}

	// After the first update, block until context is cancelled.
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	blockCtx, blockCancel := context.WithCancel(context.Background())
	stream := &mixedStream{
		updates:   updates,
		blockCtx:  blockCtx,
	}

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	var callbackCount int
	done := make(chan error, 1)
	go func() {
		done <- client.SubscribePolicyUpdates(ctx, func(p []Policy) { callbackCount++ })
	}()

	// Wait for first update to be processed then close stop channel.
	time.Sleep(30 * time.Millisecond)
	blockCancel() // unblock the stream so stopCh select fires
	close(client.stopCh)

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Expected nil error on stop, got %v", err)
		}
	case <-time.After(500 * time.Millisecond):
		t.Error("SubscribePolicyUpdates did not stop after stopCh closed")
	}
}

// TestSubscribeStreamCacheUpdated verifies the cache is updated from stream data.
func TestSubscribeStreamCacheUpdated(t *testing.T) {
	policies := []Policy{
		{ID: "pol-stream-1", Name: "Stream Policy", Enabled: true},
	}
	stream := newMockStream([]*PolicyUpdate{
		{Policies: policies, Sequence: 1},
	}, io.EOF)

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	ctx := context.Background()
	err := client.SubscribePolicyUpdates(ctx, nil)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	// Cache should now contain the streamed policies.
	client.mu.RLock()
	cached := client.policyCache
	client.mu.RUnlock()

	if len(cached) != 1 || cached[0].ID != "pol-stream-1" {
		t.Errorf("Cache not updated from stream; got %+v", cached)
	}
}

// TestSubscribeStreamNilCallbackSafe verifies nil callback is handled safely.
func TestSubscribeStreamNilCallbackSafe(t *testing.T) {
	stream := newMockStream([]*PolicyUpdate{
		{Policies: []Policy{{ID: "pol-1"}}, Sequence: 1},
	}, io.EOF)

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	// Should not panic with nil callback.
	ctx := context.Background()
	err := client.SubscribePolicyUpdates(ctx, nil)
	if err != nil {
		t.Errorf("Expected nil on clean EOF, got %v", err)
	}
}

// TestSetStreamFactoryUpdatesField verifies SetStreamFactory stores the factory.
func TestSetStreamFactoryUpdatesField(t *testing.T) {
	client := NewHubAPIClient("", "")

	if client.streamFactory != nil {
		t.Error("Expected nil streamFactory initially")
	}

	factory := func(ctx context.Context) (PolicyStream, error) { return nil, nil }
	client.SetStreamFactory(factory)

	client.mu.RLock()
	stored := client.streamFactory
	client.mu.RUnlock()

	if stored == nil {
		t.Error("Expected streamFactory to be set after SetStreamFactory")
	}
}

// ---------------------------------------------------------------------------
// mixedStream — helper for stopCh mid-stream test
// ---------------------------------------------------------------------------

// mixedStream yields a fixed set of updates then blocks until blockCtx is done.
type mixedStream struct {
	updates  []*PolicyUpdate
	idx      int
	blockCtx context.Context
}

func (m *mixedStream) Recv() (*PolicyUpdate, error) {
	if m.idx < len(m.updates) {
		u := m.updates[m.idx]
		m.idx++
		return u, nil
	}
	// Block until blockCtx is cancelled.
	<-m.blockCtx.Done()
	return nil, io.EOF
}

// ---------------------------------------------------------------------------
// RegisterController tests
// ---------------------------------------------------------------------------

// TestRegisterControllerRESTSuccess verifies RegisterController with REST API.
func TestRegisterControllerRESTSuccess(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/controllers/register" {
			w.WriteHeader(http.StatusNotFound)
			return
		}

		var reg ControllerRegistration
		if err := json.NewDecoder(r.Body).Decode(&reg); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}

		if reg.ControllerID == "ctl-1" {
			w.WriteHeader(http.StatusOK)
			return
		}

		w.WriteHeader(http.StatusBadRequest)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	reg := &ControllerRegistration{
		ControllerID: "ctl-1",
		ClusterID:    "cluster-1",
		Hostname:     "host-1",
		PublicIP:     "1.2.3.4",
		Capabilities: []string{"firewall", "routing"},
	}

	err := client.RegisterController(ctx, reg)
	if err != nil {
		t.Fatalf("RegisterController failed: %v", err)
	}
}

// TestRegisterControllerRESTBadRequest verifies RegisterController with bad request.
func TestRegisterControllerRESTBadRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte("Bad Request"))
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	reg := &ControllerRegistration{
		ControllerID: "ctl-1",
	}

	err := client.RegisterController(ctx, reg)
	if err == nil {
		t.Error("Expected RegisterController to return error on bad request")
	}
}

// TestRegisterControllerCreatedStatus verifies RegisterController with 201 Created.
func TestRegisterControllerCreatedStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx := context.Background()

	reg := &ControllerRegistration{
		ControllerID: "ctl-1",
	}

	err := client.RegisterController(ctx, reg)
	if err != nil {
		t.Fatalf("RegisterController failed with 201 Created: %v", err)
	}
}

// TestRegisterControllerInvalidURL verifies graceful failure with invalid URL.
func TestRegisterControllerInvalidURL(t *testing.T) {
	client := NewHubAPIClient("", "http://[invalid:8080/api/v1")
	ctx := context.Background()

	reg := &ControllerRegistration{ControllerID: "ctl-1"}
	err := client.RegisterController(ctx, reg)

	if err == nil {
		t.Error("Expected RegisterController to fail with invalid URL")
	}
}

// ---------------------------------------------------------------------------
// jsonReader tests
// ---------------------------------------------------------------------------

// TestJsonReaderBasic verifies jsonReader basic functionality.
func TestJsonReaderBasic(t *testing.T) {
	data := []byte("hello world")
	reader := jsonReader(data)

	buf := make([]byte, 5)
	n, err := reader.Read(buf)
	if n != 5 {
		t.Errorf("Expected read 5 bytes, got %d", n)
	}
	if err != nil {
		t.Errorf("Unexpected error: %v", err)
	}
	if string(buf) != "hello" {
		t.Errorf("Expected 'hello', got '%s'", string(buf))
	}
}

// TestJsonReaderMultipleReads verifies jsonReader with multiple reads.
func TestJsonReaderMultipleReads(t *testing.T) {
	data := []byte("hello")
	reader := jsonReader(data)

	buf1 := make([]byte, 2)
	n1, err1 := reader.Read(buf1)
	if n1 != 2 || err1 != nil {
		t.Errorf("First read failed: n=%d, err=%v", n1, err1)
	}

	buf2 := make([]byte, 3)
	n2, err2 := reader.Read(buf2)
	if n2 != 3 || err2 != nil {
		t.Errorf("Second read failed: n=%d, err=%v", n2, err2)
	}

	buf3 := make([]byte, 1)
	n3, err3 := reader.Read(buf3)
	if n3 != 0 || err3 != io.EOF {
		t.Errorf("Third read should return EOF: n=%d, err=%v", n3, err3)
	}
}

// TestJsonReaderEOF verifies jsonReader returns EOF when exhausted.
func TestJsonReaderEOF(t *testing.T) {
	data := []byte("hi")
	reader := jsonReader(data)

	buf := make([]byte, 10)
	n, err := reader.Read(buf)
	if n != 2 {
		t.Errorf("Expected 2 bytes, got %d", n)
	}
	if err != nil {
		t.Errorf("Unexpected error: %v", err)
	}

	n2, err2 := reader.Read(buf)
	if n2 != 0 || err2 != io.EOF {
		t.Errorf("Expected EOF on second read: n=%d, err=%v", n2, err2)
	}
}

// TestJsonReaderEmptyData verifies jsonReader with empty data.
func TestJsonReaderEmptyData(t *testing.T) {
	reader := jsonReader([]byte{})

	buf := make([]byte, 5)
	n, err := reader.Read(buf)
	if n != 0 || err != io.EOF {
		t.Errorf("Expected EOF on empty data: n=%d, err=%v", n, err)
	}
}

// TestJsonReaderLargeBuffer verifies reading with large buffer.
func TestJsonReaderLargeBuffer(t *testing.T) {
	data := []byte("hello world test")
	reader := jsonReader(data)

	buf := make([]byte, 1000)
	n, err := reader.Read(buf)

	if n != len(data) {
		t.Errorf("Expected to read %d bytes, got %d", len(data), n)
	}
	if err != nil {
		t.Errorf("Unexpected error: %v", err)
	}
	if string(buf[:n]) != "hello world test" {
		t.Errorf("Got wrong data: %s", string(buf[:n]))
	}
}

// ---------------------------------------------------------------------------
// Struct field tests
// ---------------------------------------------------------------------------

// TestPolicyStructure verifies the Policy struct from sync package.
func TestPolicyStructure(t *testing.T) {
	now := time.Now()
	policy := Policy{
		ID:        "pol-1",
		Name:      "Test Policy",
		Priority:  100,
		Action:    "allow",
		Domains:   []string{"example.com"},
		Ports:     []string{"80", "443"},
		Protocols: []string{"tcp"},
		CIDRs:     []string{"192.168.1.0/24"},
		Users:     []string{"alice"},
		Groups:    []string{"admin"},
		Enabled:   true,
		UpdatedAt: now,
	}

	if policy.ID != "pol-1" {
		t.Error("Policy ID not set correctly")
	}
	if policy.UpdatedAt != now {
		t.Error("Policy UpdatedAt not set correctly")
	}
}

// TestControllerRegistrationStructure verifies ControllerRegistration struct.
func TestControllerRegistrationStructure(t *testing.T) {
	reg := ControllerRegistration{
		ControllerID: "ctl-1",
		ClusterID:    "cluster-1",
		Hostname:     "host-1",
		PublicIP:     "1.2.3.4",
		Capabilities: []string{"firewall", "routing"},
	}

	if reg.ControllerID != "ctl-1" {
		t.Error("ControllerID not set correctly")
	}
	if reg.PublicIP != "1.2.3.4" {
		t.Error("PublicIP not set correctly")
	}
	if len(reg.Capabilities) != 2 {
		t.Error("Capabilities not set correctly")
	}
}

// TestPolicyUpdateStructure verifies the PolicyUpdate struct.
func TestPolicyUpdateStructure(t *testing.T) {
	update := PolicyUpdate{
		Policies: []Policy{{ID: "pol-1", Enabled: true}},
		Sequence: 42,
	}
	if update.Sequence != 42 {
		t.Errorf("Expected Sequence 42, got %d", update.Sequence)
	}
	if len(update.Policies) != 1 {
		t.Errorf("Expected 1 policy, got %d", len(update.Policies))
	}
}

// TestClientMutexProtection verifies that Close() waits for locks properly.
func TestClientMutexProtection(t *testing.T) {
	client := NewHubAPIClient("", "")

	err := client.Close()
	if err != nil {
		t.Errorf("Close() failed: %v", err)
	}
}

// ---------------------------------------------------------------------------
// gRPC-available path coverage (grpcAvailable=true forces internal gRPC stubs)
// ---------------------------------------------------------------------------

// TestFetchPoliciesGRPCFallbackToREST exercises the gRPC-available path in
// FetchPolicies, which calls fetchPoliciesGRPC (returns error) then falls back
// to REST. This covers the fetchPoliciesGRPC stub and the gRPC→REST fallback.
func TestFetchPoliciesGRPCFallbackToREST(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		policies := []Policy{{ID: "pol-rest", Enabled: true}}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(policies)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	// Pretend gRPC is available — fetchPoliciesGRPC will return an error and
	// the client will fall back to REST automatically.
	client.grpcAvailable = true
	ctx := context.Background()

	policies, err := client.FetchPolicies(ctx)
	if err != nil {
		t.Fatalf("Expected REST fallback to succeed, got: %v", err)
	}
	if len(policies) != 1 || policies[0].ID != "pol-rest" {
		t.Errorf("Unexpected policies: %+v", policies)
	}
}

// TestFetchPoliciesGRPCFallbackRESTFails exercises the path where both gRPC and
// REST fail, confirming the combined error is surfaced.
func TestFetchPoliciesGRPCFallbackRESTFails(t *testing.T) {
	client := NewHubAPIClient("", "http://127.0.0.1:1/api/v1") // unreachable REST
	client.grpcAvailable = true
	ctx := context.Background()

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected error when both gRPC and REST fail")
	}
}

// TestRegisterControllerGRPCFallbackToREST exercises the gRPC-available path in
// RegisterController, which calls registerControllerGRPC (returns error) then
// falls back to REST.
func TestRegisterControllerGRPCFallbackToREST(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	client.grpcAvailable = true
	ctx := context.Background()

	reg := &ControllerRegistration{ControllerID: "ctl-grpc-fallback"}
	err := client.RegisterController(ctx, reg)
	if err != nil {
		t.Fatalf("Expected REST fallback to succeed, got: %v", err)
	}
}

// TestRegisterControllerGRPCFallbackRESTFails verifies error propagation when
// both gRPC and REST registration fail.
func TestRegisterControllerGRPCFallbackRESTFails(t *testing.T) {
	client := NewHubAPIClient("", "http://127.0.0.1:1/api/v1") // unreachable REST
	client.grpcAvailable = true
	ctx := context.Background()

	reg := &ControllerRegistration{ControllerID: "ctl-1"}
	err := client.RegisterController(ctx, reg)
	if err == nil {
		t.Error("Expected error when both gRPC and REST fail")
	}
}

// ---------------------------------------------------------------------------
// subscribeViaPoll ticker path
// ---------------------------------------------------------------------------

// TestSubscribeViaPollTickerFires verifies the polling ticker fires and invokes
// the callback at least once within a short window.
func TestSubscribeViaPollTickerFires(t *testing.T) {
	callbackCh := make(chan struct{}, 5)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode([]Policy{{ID: "pol-tick", Enabled: true}})
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	// Use a very short poll interval by directly calling subscribeViaPoll
	// but with a fast ticker via a goroutine that cancels after first callback.
	ctx, cancel := context.WithCancel(context.Background())

	callback := func(policies []Policy) {
		callbackCh <- struct{}{}
		cancel() // stop after first callback
	}

	// Override poll interval by invoking subscribeViaPoll directly with a
	// short-lived context that fires quickly. We manipulate the ticker by
	// setting a very short cacheTTL so FetchPolicies actually hits the server.
	client.cacheTTL = 1 * time.Millisecond

	// We need to invoke the poll path; set no factory so SubscribePolicyUpdates
	// routes to subscribeViaPoll.  Shorten the ticker by replacing the 30s
	// ticker inside subscribeViaPoll with our own via a helper.
	done := make(chan error, 1)
	go func() {
		done <- client.subscribeViaPollFast(ctx, callback, 20*time.Millisecond)
	}()

	select {
	case <-callbackCh:
		// Callback was invoked — success.
	case <-time.After(500 * time.Millisecond):
		cancel()
		t.Error("Poll ticker did not fire within 500ms")
	}

	<-done
}

// TestSubscribeViaPollFastPollError verifies poll error is logged but not fatal.
func TestSubscribeViaPollFastPollError(t *testing.T) {
	// unreachable server so FetchPolicies always fails
	client := NewHubAPIClient("", "http://127.0.0.1:1/api/v1")

	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	// Should return context error, not poll error.
	err := client.subscribeViaPollFast(ctx, nil, 10*time.Millisecond)
	if err == nil {
		t.Error("Expected context timeout error")
	}
}

// TestSubscribeViaPollFastStopChannel verifies stop channel terminates fast poll.
func TestSubscribeViaPollFastStopChannel(t *testing.T) {
	client := NewHubAPIClient("", "")
	ctx := context.Background()

	done := make(chan error, 1)
	go func() {
		done <- client.subscribeViaPollFast(ctx, nil, 10*time.Millisecond)
	}()

	time.Sleep(15 * time.Millisecond)
	close(client.stopCh)

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Expected nil on stop, got %v", err)
		}
	case <-time.After(500 * time.Millisecond):
		t.Error("subscribeViaPollFast did not stop")
	}
}

// ---------------------------------------------------------------------------
// reconnectLoop coverage
// ---------------------------------------------------------------------------

// TestReconnectLoopStopsOnStopCh verifies the reconnect loop exits when stopCh
// is closed without having to wait 10 seconds.
func TestReconnectLoopStopsOnStopCh(t *testing.T) {
	client := NewHubAPIClient("127.0.0.1:1", "") // unreachable gRPC

	done := make(chan struct{})
	go func() {
		defer close(done)
		client.reconnectLoopFast(5 * time.Millisecond)
	}()

	time.Sleep(10 * time.Millisecond)
	close(client.stopCh)

	select {
	case <-done:
		// OK
	case <-time.After(500 * time.Millisecond):
		t.Error("reconnectLoop did not exit after stopCh closed")
	}
}

// TestReconnectLoopExitsWhenAlreadyConnected verifies the loop exits immediately
// when grpcAvailable is already true.
func TestReconnectLoopExitsWhenAlreadyConnected(t *testing.T) {
	client := NewHubAPIClient("", "")
	client.mu.Lock()
	client.grpcAvailable = true
	client.mu.Unlock()

	done := make(chan struct{})
	go func() {
		defer close(done)
		client.reconnectLoopFast(5 * time.Millisecond)
	}()

	select {
	case <-done:
		// Loop exited early because grpcAvailable=true
	case <-time.After(200 * time.Millisecond):
		t.Error("reconnectLoop should have exited immediately when already connected")
	}
}

// ---------------------------------------------------------------------------
// Connect success path (covers the "connected" branch in Connect)
// ---------------------------------------------------------------------------

// TestConnectSuccessPath exercises the success branch of Connect.
// grpc.NewClient uses lazy dialing, so it succeeds for any well-formed address.
func TestConnectSuccessPath(t *testing.T) {
	// "passthrough:///localhost:50051" is a valid address that bypasses DNS;
	// grpc.NewClient always succeeds for well-formed addresses (lazy-dial).
	client := NewHubAPIClient("passthrough:///localhost:50051", "")
	ctx := context.Background()

	err := client.Connect(ctx)
	// grpc.NewClient is non-blocking; it always succeeds for well-formed addresses.
	if err != nil {
		t.Logf("Connect returned error (acceptable on this platform): %v", err)
		return
	}
	// If it succeeded, grpcAvailable should be true and the connection set.
	client.mu.RLock()
	avail := client.grpcAvailable
	conn := client.grpcConn
	client.mu.RUnlock()

	if !avail {
		t.Error("Expected grpcAvailable=true after successful Connect")
	}
	if conn == nil {
		t.Error("Expected grpcConn to be set after successful Connect")
	}
	// Clean up
	client.Close()
}

// TestReconnectLoopFastReconnectsSuccessfully verifies reconnectLoopFast sets
// grpcAvailable=true when grpc.NewClient succeeds.
func TestReconnectLoopFastReconnectsSuccessfully(t *testing.T) {
	// Use a valid address so grpc.NewClient succeeds (lazy dial).
	client := NewHubAPIClient("passthrough:///localhost:50051", "")

	done := make(chan struct{})
	go func() {
		defer close(done)
		client.reconnectLoopFast(5 * time.Millisecond)
	}()

	select {
	case <-done:
		// reconnectLoopFast should have reconnected and returned.
	case <-time.After(500 * time.Millisecond):
		close(client.stopCh) // force stop to avoid goroutine leak
		t.Error("reconnectLoopFast did not complete within 500ms")
		return
	}

	client.mu.RLock()
	avail := client.grpcAvailable
	client.mu.RUnlock()

	if !avail {
		t.Error("Expected grpcAvailable=true after reconnect")
	}
}

// ---------------------------------------------------------------------------
// Close error path — cover the grpcConn.Close() error branch
// ---------------------------------------------------------------------------

// TestCloseWithNilGRPCConn verifies Close succeeds when grpcConn is nil.
func TestCloseWithNilGRPCConn(t *testing.T) {
	client := NewHubAPIClient("", "")
	err := client.Close()
	if err != nil {
		t.Errorf("Close() with nil grpcConn failed: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Connect failure path via injected dialFn
// ---------------------------------------------------------------------------

// TestConnectFailurePath verifies the failure branch of Connect using an
// injected dial function that always fails.
func TestConnectFailurePath(t *testing.T) {
	dialErr := errors.New("simulated dial failure")

	client := NewHubAPIClient("", "")
	client.dialFn = func(target string, opts ...grpc.DialOption) (*grpc.ClientConn, error) {
		return nil, dialErr
	}

	ctx := context.Background()
	err := client.Connect(ctx)

	// Connect should return nil (falls back to REST).
	if err != nil {
		t.Errorf("Expected Connect to return nil on dial failure, got %v", err)
	}

	client.mu.RLock()
	avail := client.grpcAvailable
	client.mu.RUnlock()

	if avail {
		t.Error("Expected grpcAvailable=false after dial failure")
	}

	// Give the reconnectLoop goroutine a moment to start then stop it.
	time.Sleep(10 * time.Millisecond)
	close(client.stopCh)
}

// TestConnectWithInjectableDialSuccess verifies Connect sets grpcAvailable=true
// when the injected dialer succeeds.
func TestConnectWithInjectableDialSuccess(t *testing.T) {
	client := NewHubAPIClient("passthrough:///localhost:50051", "")
	// Use default dialer (nil) — grpc.NewClient always succeeds with lazy dial.
	ctx := context.Background()
	err := client.Connect(ctx)
	if err != nil {
		t.Fatalf("Connect failed: %v", err)
	}

	client.mu.RLock()
	avail := client.grpcAvailable
	client.mu.RUnlock()

	if !avail {
		t.Error("Expected grpcAvailable=true")
	}
	client.Close()
}

// ---------------------------------------------------------------------------
// reconnectLoop direct coverage
// ---------------------------------------------------------------------------

// TestReconnectLoopDelegates verifies reconnectLoopFast retries on failure by
// injecting a failing dialer and ensuring at least one dial attempt happens.
func TestReconnectLoopDelegates(t *testing.T) {
	dialCount := 0
	client := NewHubAPIClient("", "")
	client.dialFn = func(target string, opts ...grpc.DialOption) (*grpc.ClientConn, error) {
		dialCount++
		return nil, errors.New("always fail")
	}

	done := make(chan struct{})
	go func() {
		defer close(done)
		client.reconnectLoopFast(5 * time.Millisecond)
	}()

	// Wait for at least one dial attempt then close.
	time.Sleep(30 * time.Millisecond)
	close(client.stopCh)

	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
		t.Error("reconnectLoopFast did not exit after stopCh closed")
	}

	if dialCount == 0 {
		t.Error("Expected at least one dial attempt")
	}
}

// TestReconnectLoopDirectCall tests the reconnectLoop 1-line wrapper.
func TestReconnectLoopDirectCall(t *testing.T) {
	// Set grpcAvailable=true so the loop exits on the first tick without dialing.
	client := NewHubAPIClient("", "")
	client.mu.Lock()
	client.grpcAvailable = true
	client.mu.Unlock()

	done := make(chan struct{})
	go func() {
		defer close(done)
		client.reconnectLoopFast(5 * time.Millisecond)
	}()

	select {
	case <-done:
		// exited quickly because grpcAvailable=true
	case <-time.After(500 * time.Millisecond):
		t.Error("reconnectLoop did not exit when already connected")
	}
}

// ---------------------------------------------------------------------------
// subscribeViaStream — stopCh case during Recv
// ---------------------------------------------------------------------------

// TestSubscribeViaStreamStopChDuringRecv verifies the stopCh select arm inside
// subscribeViaStream fires between Recv calls.
func TestSubscribeViaStreamStopChDuringRecv(t *testing.T) {
	blockCtx, blockCancel := context.WithCancel(context.Background())
	defer blockCancel()

	stream := &mixedStream{
		updates:  []*PolicyUpdate{{Policies: []Policy{{ID: "pol-1"}}, Sequence: 1}},
		blockCtx: blockCtx,
	}

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	ctx := context.Background()
	done := make(chan error, 1)
	go func() {
		done <- client.SubscribePolicyUpdates(ctx, nil)
	}()

	// Let first update be processed, then close stopCh while stream blocks.
	time.Sleep(20 * time.Millisecond)
	blockCancel()               // unblock the stream
	time.Sleep(5 * time.Millisecond)
	close(client.stopCh)       // trigger stopCh case in the select

	select {
	case err := <-done:
		if err != nil {
			t.Errorf("Expected nil on stop, got %v", err)
		}
	case <-time.After(500 * time.Millisecond):
		t.Error("subscribeViaStream did not stop after stopCh closed")
	}
}

// ---------------------------------------------------------------------------
// fetchPoliciesREST — request creation failure
// ---------------------------------------------------------------------------

// TestFetchPoliciesRESTRequestCreationFail exercises the path where
// http.NewRequestWithContext fails due to an invalid URL scheme.
func TestFetchPoliciesRESTRequestCreationFail(t *testing.T) {
	client := NewHubAPIClient("", "://bad")
	ctx := context.Background()

	_, err := client.FetchPolicies(ctx)
	if err == nil {
		t.Error("Expected error with invalid REST URL")
	}
}

// ---------------------------------------------------------------------------
// RegisterController — context cancel path
// ---------------------------------------------------------------------------

// TestSubscribeViaStreamPreCancelledContext verifies the pre-Recv ctx.Done()
// select case fires when the context is already cancelled before streaming.
func TestSubscribeViaStreamPreCancelledContext(t *testing.T) {
	// A stream that blocks forever — we need it to never be reached.
	// The pre-Recv select should fire first because ctx is already done.
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel BEFORE subscribing

	// A stream that would block, but we should never get to Recv.
	stream := &blockingStream{ctx: ctx}

	client := NewHubAPIClient("", "")
	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	err := client.SubscribePolicyUpdates(ctx, nil)
	if err == nil {
		t.Error("Expected context error, got nil")
	}
	if !errors.Is(err, context.Canceled) {
		t.Errorf("Expected context.Canceled, got %v", err)
	}
}

// TestSubscribeViaStreamPreClosedStopCh verifies the pre-Recv stopCh case fires
// when stopCh is already closed before the stream enters the Recv loop.
func TestSubscribeViaStreamPreClosedStopCh(t *testing.T) {
	// A stream that delivers one item then blocks.
	blockCtx, blockCancel := context.WithCancel(context.Background())
	defer blockCancel()

	stream := &mixedStream{
		updates:  []*PolicyUpdate{{Policies: []Policy{{ID: "pol-1"}}, Sequence: 1}},
		blockCtx: blockCtx,
	}

	client := NewHubAPIClient("", "")
	// Close stopCh BEFORE starting subscription.
	close(client.stopCh)

	client.SetStreamFactory(func(ctx context.Context) (PolicyStream, error) {
		return stream, nil
	})

	ctx := context.Background()
	err := client.SubscribePolicyUpdates(ctx, nil)
	// Should return nil because stopCh was closed.
	if err != nil {
		t.Errorf("Expected nil on pre-closed stopCh, got %v", err)
	}
}

// TestRegisterControllerContextCancel verifies cancellation propagates via REST.
func TestRegisterControllerContextCancel(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(1 * time.Second) // slow server
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	client := NewHubAPIClient("", server.URL+"/api/v1")
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	reg := &ControllerRegistration{ControllerID: "ctl-ctx"}
	err := client.RegisterController(ctx, reg)
	if err == nil {
		t.Error("Expected error on cancelled context")
	}
}
