// Package grpc provides gRPC client utilities with connection management and retry logic.
package grpc

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"log"
	"os"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

// ClientOptions configures gRPC client behavior.
type ClientOptions struct {
	MaxRetries        int
	InitialBackoff    time.Duration
	MaxBackoff        time.Duration
	BackoffMultiplier float64
	Timeout           time.Duration
	EnableTLS         bool
	CACertPath        string
	ClientCertPath    string
	ClientKeyPath     string
	KeepaliveTime     time.Duration
	KeepaliveTimeout  time.Duration
}

// DefaultClientOptions returns sensible defaults for client configuration.
func DefaultClientOptions() *ClientOptions {
	return &ClientOptions{
		MaxRetries:        3,
		InitialBackoff:    100 * time.Millisecond,
		MaxBackoff:        5 * time.Second,
		BackoffMultiplier: 2.0,
		Timeout:           30 * time.Second,
		EnableTLS:         false,
		KeepaliveTime:     1 * time.Minute,
		KeepaliveTimeout:  20 * time.Second,
	}
}

// ClientOption is a functional option for configuring the client.
type ClientOption func(*ClientOptions)

// WithTLS enables TLS with optional client certificates.
func WithTLS(caCertPath, clientCertPath, clientKeyPath string) ClientOption {
	return func(opts *ClientOptions) {
		opts.EnableTLS = true
		opts.CACertPath = caCertPath
		opts.ClientCertPath = clientCertPath
		opts.ClientKeyPath = clientKeyPath
	}
}

// WithTimeout sets the default timeout for RPCs.
func WithTimeout(timeout time.Duration) ClientOption {
	return func(opts *ClientOptions) {
		opts.Timeout = timeout
	}
}

// WithRetries sets the maximum number of retries.
func WithRetries(maxRetries int) ClientOption {
	return func(opts *ClientOptions) {
		opts.MaxRetries = maxRetries
	}
}

// Client wraps a gRPC connection with retry logic.
type Client struct {
	conn   *grpc.ClientConn
	opts   *ClientOptions
	target string
}

// NewClient creates a new gRPC client with the given target and options.
//
// Example:
//
//	client, err := NewClient(
//	    "localhost:50051",
//	    WithTimeout(10*time.Second),
//	    WithRetries(5),
//	)
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer client.Close()
func NewClient(target string, options ...ClientOption) (*Client, error) {
	opts := DefaultClientOptions()
	for _, opt := range options {
		opt(opts)
	}

	// Create dial options
	dialOpts := []grpc.DialOption{
		grpc.WithKeepaliveParams(keepaliveClientParams(opts)),
	}

	// Configure credentials
	if opts.EnableTLS {
		creds, err := loadTLSCredentials(opts)
		if err != nil {
			log.Printf("Failed to load TLS credentials: %v", err)
			return nil, err
		}
		dialOpts = append(dialOpts, grpc.WithTransportCredentials(creds))
	} else {
		dialOpts = append(dialOpts, grpc.WithTransportCredentials(insecure.NewCredentials()))
	}

	// Create connection
	conn, err := grpc.Dial(target, dialOpts...)
	if err != nil {
		log.Printf("Failed to connect to %s: %v", target, err)
		return nil, err
	}

	log.Printf("gRPC client connected to %s", target)

	return &Client{
		conn:   conn,
		opts:   opts,
		target: target,
	}, nil
}

// Conn returns the underlying gRPC connection.
func (c *Client) Conn() *grpc.ClientConn {
	return c.conn
}

// CallWithRetry executes the given function with exponential backoff retry.
//
// Example:
//
//	var response *pb.Response
//	err := client.CallWithRetry(ctx, func(ctx context.Context) error {
//	    stub := pb.NewMyServiceClient(client.Conn())
//	    var err error
//	    response, err = stub.MyMethod(ctx, request)
//	    return err
//	})
func (c *Client) CallWithRetry(
	ctx context.Context,
	fn func(context.Context) error,
) error {
	backoff := c.opts.InitialBackoff
	var lastErr error

	for attempt := 0; attempt < c.opts.MaxRetries; attempt++ {
		// Create context with timeout
		callCtx, cancel := context.WithTimeout(ctx, c.opts.Timeout)

		// Execute function
		err := fn(callCtx)
		cancel()

		if err == nil {
			return nil
		}

		lastErr = err

		// Check if error is retryable
		if !isRetryable(err) {
			log.Printf("Non-retryable error: %v", err)
			return err
		}

		// Retry with exponential backoff
		if attempt < c.opts.MaxRetries-1 {
			log.Printf("RPC failed (attempt %d/%d), retrying in %v: %v",
				attempt+1, c.opts.MaxRetries, backoff, err)

			time.Sleep(backoff)

			// Increase backoff
			backoff = time.Duration(float64(backoff) * c.opts.BackoffMultiplier)
			if backoff > c.opts.MaxBackoff {
				backoff = c.opts.MaxBackoff
			}
		}
	}

	log.Printf("RPC failed after %d attempts: %v", c.opts.MaxRetries, lastErr)
	return lastErr
}

// Close closes the gRPC connection.
func (c *Client) Close() error {
	if c.conn != nil {
		log.Printf("Closing gRPC connection to %s", c.target)
		return c.conn.Close()
	}
	return nil
}

// isRetryable determines if a gRPC error should be retried.
func isRetryable(err error) bool {
	st, ok := status.FromError(err)
	if !ok {
		return false
	}

	code := st.Code()

	// Don't retry on these error codes
	switch code {
	case codes.InvalidArgument,
		codes.NotFound,
		codes.AlreadyExists,
		codes.PermissionDenied,
		codes.Unauthenticated:
		return false
	}

	// Retry on transient errors
	return true
}

// loadTLSCredentials loads TLS credentials from files.
func loadTLSCredentials(opts *ClientOptions) (credentials.TransportCredentials, error) {
	config := &tls.Config{}

	// Load CA certificate
	if opts.CACertPath != "" {
		caCert, err := os.ReadFile(opts.CACertPath)
		if err != nil {
			return nil, err
		}

		certPool := x509.NewCertPool()
		if !certPool.AppendCertsFromPEM(caCert) {
			return nil, err
		}
		config.RootCAs = certPool
	}

	// Load client certificate
	if opts.ClientCertPath != "" && opts.ClientKeyPath != "" {
		cert, err := tls.LoadX509KeyPair(opts.ClientCertPath, opts.ClientKeyPath)
		if err != nil {
			return nil, err
		}
		config.Certificates = []tls.Certificate{cert}
	}

	return credentials.NewTLS(config), nil
}

// keepaliveClientParams returns keepalive parameters for the client.
func keepaliveClientParams(opts *ClientOptions) grpc.KeepaliveParams {
	return grpc.KeepaliveParams{
		Time:                opts.KeepaliveTime,
		Timeout:             opts.KeepaliveTimeout,
		PermitWithoutStream: true,
	}
}
