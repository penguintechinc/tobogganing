package http

import (
	"context"
	"fmt"
	"io"
	"log"
	"math"
	"math/rand"
	"net/http"
	"time"
)

// RetryConfig configures retry behavior for HTTP requests.
type RetryConfig struct {
	MaxRetries      int           // Maximum number of retry attempts
	BaseDelay       time.Duration // Base delay for exponential backoff
	MaxDelay        time.Duration // Maximum delay between retries
	ExponentialBase float64       // Base for exponential backoff calculation
	Jitter          bool          // Whether to add random jitter to delays
}

// DefaultRetryConfig returns sensible default retry configuration.
func DefaultRetryConfig() RetryConfig {
	return RetryConfig{
		MaxRetries:      3,
		BaseDelay:       1 * time.Second,
		MaxDelay:        30 * time.Second,
		ExponentialBase: 2.0,
		Jitter:          true,
	}
}

// CircuitState represents the state of a circuit breaker.
type CircuitState int

const (
	// CircuitClosed indicates normal operation.
	CircuitClosed CircuitState = iota
	// CircuitOpen indicates the circuit is open and rejecting requests.
	CircuitOpen
	// CircuitHalfOpen indicates the circuit is testing if the service recovered.
	CircuitHalfOpen
)

// CircuitBreakerConfig configures circuit breaker behavior.
type CircuitBreakerConfig struct {
	Enabled          bool          // Whether circuit breaker is enabled
	FailureThreshold int           // Number of failures before opening circuit
	SuccessThreshold int           // Number of successes before closing circuit
	Timeout          time.Duration // Time to wait before entering half-open state
}

// DefaultCircuitBreakerConfig returns default circuit breaker configuration (disabled).
func DefaultCircuitBreakerConfig() CircuitBreakerConfig {
	return CircuitBreakerConfig{
		Enabled:          false,
		FailureThreshold: 5,
		SuccessThreshold: 2,
		Timeout:          60 * time.Second,
	}
}

// circuitBreakerState tracks the internal state of a circuit breaker.
type circuitBreakerState struct {
	state           CircuitState
	failureCount    int
	successCount    int
	lastFailureTime time.Time
}

// ClientOption is a functional option for configuring Client.
type ClientOption func(*Client)

// WithTimeout sets the request timeout.
func WithTimeout(timeout time.Duration) ClientOption {
	return func(c *Client) {
		c.client.Timeout = timeout
	}
}

// WithRetryConfig sets the retry configuration.
func WithRetryConfig(config RetryConfig) ClientOption {
	return func(c *Client) {
		c.retryConfig = config
	}
}

// WithCircuitBreaker enables and configures the circuit breaker.
func WithCircuitBreaker(config CircuitBreakerConfig) ClientOption {
	return func(c *Client) {
		c.circuitConfig = config
	}
}

// WithHeaders sets default headers for all requests.
func WithHeaders(headers map[string]string) ClientOption {
	return func(c *Client) {
		c.defaultHeaders = headers
	}
}

// WithLogger sets a custom logger function.
func WithLogger(logger func(format string, args ...interface{})) ClientOption {
	return func(c *Client) {
		c.logger = logger
	}
}

// Client is a production-ready HTTP client with retries and circuit breaker.
type Client struct {
	client          *http.Client
	retryConfig     RetryConfig
	circuitConfig   CircuitBreakerConfig
	circuitState    circuitBreakerState
	defaultHeaders  map[string]string
	logger          func(format string, args ...interface{})
}

// NewClient creates a new HTTP client with the provided options.
//
// Example:
//
//	client := NewClient(
//	    WithTimeout(30 * time.Second),
//	    WithRetryConfig(RetryConfig{MaxRetries: 3, BaseDelay: 1 * time.Second}),
//	    WithCircuitBreaker(CircuitBreakerConfig{Enabled: true, FailureThreshold: 5}),
//	)
//	defer client.Close()
//
//	resp, err := client.Get(context.Background(), "https://api.example.com/users")
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer resp.Body.Close()
func NewClient(opts ...ClientOption) *Client {
	c := &Client{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		retryConfig:   DefaultRetryConfig(),
		circuitConfig: DefaultCircuitBreakerConfig(),
		circuitState: circuitBreakerState{
			state: CircuitClosed,
		},
		defaultHeaders: make(map[string]string),
		logger:         log.Printf,
	}

	for _, opt := range opts {
		opt(c)
	}

	return c
}

// Close closes the HTTP client and releases resources.
func (c *Client) Close() {
	c.client.CloseIdleConnections()
}

// calculateDelay computes the delay for exponential backoff with optional jitter.
func (c *Client) calculateDelay(attempt int) time.Duration {
	delay := time.Duration(
		float64(c.retryConfig.BaseDelay) * math.Pow(c.retryConfig.ExponentialBase, float64(attempt)),
	)

	if delay > c.retryConfig.MaxDelay {
		delay = c.retryConfig.MaxDelay
	}

	if c.retryConfig.Jitter {
		// Add jitter: 50-150% of base delay
		jitterFactor := 0.5 + rand.Float64()
		delay = time.Duration(float64(delay) * jitterFactor)
	}

	return delay
}

// checkCircuitBreaker checks if the circuit breaker allows the request.
func (c *Client) checkCircuitBreaker() error {
	if !c.circuitConfig.Enabled {
		return nil
	}

	now := time.Now()

	if c.circuitState.state == CircuitOpen {
		elapsed := now.Sub(c.circuitState.lastFailureTime)
		if elapsed >= c.circuitConfig.Timeout {
			c.logger("Circuit breaker entering HALF_OPEN state")
			c.circuitState.state = CircuitHalfOpen
			c.circuitState.successCount = 0
		} else {
			return fmt.Errorf("circuit breaker is OPEN (retry after %.1fs)", (c.circuitConfig.Timeout - elapsed).Seconds())
		}
	}

	return nil
}

// recordSuccess records a successful request for the circuit breaker.
func (c *Client) recordSuccess() {
	if !c.circuitConfig.Enabled {
		return
	}

	if c.circuitState.state == CircuitHalfOpen {
		c.circuitState.successCount++
		if c.circuitState.successCount >= c.circuitConfig.SuccessThreshold {
			c.logger("Circuit breaker closing after successful requests")
			c.circuitState.state = CircuitClosed
			c.circuitState.failureCount = 0
		}
	} else if c.circuitState.state == CircuitClosed {
		c.circuitState.failureCount = 0
	}
}

// recordFailure records a failed request for the circuit breaker.
func (c *Client) recordFailure() {
	if !c.circuitConfig.Enabled {
		return
	}

	c.circuitState.lastFailureTime = time.Now()

	if c.circuitState.state == CircuitHalfOpen {
		c.logger("Circuit breaker opening after failure in HALF_OPEN state")
		c.circuitState.state = CircuitOpen
		c.circuitState.failureCount = 0
	} else if c.circuitState.state == CircuitClosed {
		c.circuitState.failureCount++
		if c.circuitState.failureCount >= c.circuitConfig.FailureThreshold {
			c.logger("Circuit breaker opening after %d failures", c.circuitState.failureCount)
			c.circuitState.state = CircuitOpen
		}
	}
}

// prepareHeaders combines default headers with request-specific headers and adds correlation ID.
func (c *Client) prepareHeaders(ctx context.Context, headers map[string]string) map[string]string {
	combined := make(map[string]string)

	// Copy default headers
	for k, v := range c.defaultHeaders {
		combined[k] = v
	}

	// Copy request-specific headers (override defaults)
	for k, v := range headers {
		combined[k] = v
	}

	// Add correlation ID if available and not already set
	if correlationID := GetCorrelationID(ctx); correlationID != "" {
		if _, exists := combined[HeaderXCorrelationID]; !exists {
			combined[HeaderXCorrelationID] = correlationID
			combined[HeaderXRequestID] = correlationID
		}
	}

	return combined
}

// shouldRetry determines if a request should be retried based on status code.
func shouldRetry(statusCode int) bool {
	// Don't retry client errors (4xx) except 429 (rate limit)
	if statusCode >= 400 && statusCode < 500 && statusCode != 429 {
		return false
	}
	// Retry server errors (5xx) and rate limits (429)
	return statusCode >= 500 || statusCode == 429
}

// Do executes an HTTP request with retry logic and circuit breaker.
func (c *Client) Do(ctx context.Context, req *http.Request) (*http.Response, error) {
	// Check circuit breaker
	if err := c.checkCircuitBreaker(); err != nil {
		return nil, err
	}

	var lastErr error

	for attempt := 0; attempt <= c.retryConfig.MaxRetries; attempt++ {
		c.logger("HTTP %s %s (attempt %d/%d)", req.Method, req.URL.String(), attempt+1, c.retryConfig.MaxRetries+1)

		// Clone request for retry (body might be consumed)
		reqClone := req.Clone(ctx)

		// Execute request
		resp, err := c.client.Do(reqClone)
		if err != nil {
			lastErr = err
			c.logger("HTTP %s %s failed (attempt %d): %v", req.Method, req.URL.String(), attempt+1, err)
			c.recordFailure()

			// If this was the last attempt, return error
			if attempt >= c.retryConfig.MaxRetries {
				return nil, lastErr
			}

			// Calculate and apply delay
			delay := c.calculateDelay(attempt)
			c.logger("Retrying in %.2fs...", delay.Seconds())
			time.Sleep(delay)
			continue
		}

		// Check if response indicates failure
		if resp.StatusCode >= 400 {
			// Read and close body for error responses
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()

			lastErr = fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
			c.logger("HTTP %s %s -> %d", req.Method, req.URL.String(), resp.StatusCode)

			// Don't retry client errors (except 429)
			if !shouldRetry(resp.StatusCode) {
				c.recordFailure()
				return nil, lastErr
			}

			c.recordFailure()

			// If this was the last attempt, return error
			if attempt >= c.retryConfig.MaxRetries {
				return nil, lastErr
			}

			// Calculate and apply delay
			delay := c.calculateDelay(attempt)
			c.logger("Retrying in %.2fs...", delay.Seconds())
			time.Sleep(delay)
			continue
		}

		// Success
		c.logger("HTTP %s %s -> %d", req.Method, req.URL.String(), resp.StatusCode)
		c.recordSuccess()
		return resp, nil
	}

	return nil, lastErr
}

// Get executes a GET request with retry logic.
func (c *Client) Get(ctx context.Context, url string, headers ...map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}

	var reqHeaders map[string]string
	if len(headers) > 0 {
		reqHeaders = headers[0]
	}

	combinedHeaders := c.prepareHeaders(ctx, reqHeaders)
	for k, v := range combinedHeaders {
		req.Header.Set(k, v)
	}

	return c.Do(ctx, req)
}

// Post executes a POST request with retry logic.
func (c *Client) Post(ctx context.Context, url string, body io.Reader, headers ...map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, body)
	if err != nil {
		return nil, err
	}

	var reqHeaders map[string]string
	if len(headers) > 0 {
		reqHeaders = headers[0]
	}

	combinedHeaders := c.prepareHeaders(ctx, reqHeaders)
	for k, v := range combinedHeaders {
		req.Header.Set(k, v)
	}

	return c.Do(ctx, req)
}

// Put executes a PUT request with retry logic.
func (c *Client) Put(ctx context.Context, url string, body io.Reader, headers ...map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, url, body)
	if err != nil {
		return nil, err
	}

	var reqHeaders map[string]string
	if len(headers) > 0 {
		reqHeaders = headers[0]
	}

	combinedHeaders := c.prepareHeaders(ctx, reqHeaders)
	for k, v := range combinedHeaders {
		req.Header.Set(k, v)
	}

	return c.Do(ctx, req)
}

// Patch executes a PATCH request with retry logic.
func (c *Client) Patch(ctx context.Context, url string, body io.Reader, headers ...map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPatch, url, body)
	if err != nil {
		return nil, err
	}

	var reqHeaders map[string]string
	if len(headers) > 0 {
		reqHeaders = headers[0]
	}

	combinedHeaders := c.prepareHeaders(ctx, reqHeaders)
	for k, v := range combinedHeaders {
		req.Header.Set(k, v)
	}

	return c.Do(ctx, req)
}

// Delete executes a DELETE request with retry logic.
func (c *Client) Delete(ctx context.Context, url string, headers ...map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, url, nil)
	if err != nil {
		return nil, err
	}

	var reqHeaders map[string]string
	if len(headers) > 0 {
		reqHeaders = headers[0]
	}

	combinedHeaders := c.prepareHeaders(ctx, reqHeaders)
	for k, v := range combinedHeaders {
		req.Header.Set(k, v)
	}

	return c.Do(ctx, req)
}

// Head executes a HEAD request with retry logic.
func (c *Client) Head(ctx context.Context, url string, headers ...map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, nil)
	if err != nil {
		return nil, err
	}

	var reqHeaders map[string]string
	if len(headers) > 0 {
		reqHeaders = headers[0]
	}

	combinedHeaders := c.prepareHeaders(ctx, reqHeaders)
	for k, v := range combinedHeaders {
		req.Header.Set(k, v)
	}

	return c.Do(ctx, req)
}
