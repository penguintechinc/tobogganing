// Package grpc provides gRPC server utilities with health checks and graceful shutdown.
package grpc

import (
	"context"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
)

// ServerOptions configures gRPC server behavior.
type ServerOptions struct {
	MaxWorkers          int
	MaxConcurrentRPCs   int
	EnableReflection    bool
	EnableHealthCheck   bool
	Port                string
	MaxConnectionIdle   time.Duration
	MaxConnectionAge    time.Duration
	KeepaliveTime       time.Duration
	KeepaliveTimeout    time.Duration
	GracefulStopTimeout time.Duration
}

// DefaultServerOptions returns sensible defaults for server configuration.
func DefaultServerOptions() *ServerOptions {
	return &ServerOptions{
		MaxWorkers:          10,
		MaxConcurrentRPCs:   100,
		EnableReflection:    true,
		EnableHealthCheck:   true,
		Port:                "50051",
		MaxConnectionIdle:   5 * time.Minute,
		MaxConnectionAge:    10 * time.Minute,
		KeepaliveTime:       1 * time.Minute,
		KeepaliveTimeout:    20 * time.Second,
		GracefulStopTimeout: 30 * time.Second,
	}
}

// ServerOption is a functional option for configuring the server.
type ServerOption func(*ServerOptions)

// WithPort sets the server port.
func WithPort(port string) ServerOption {
	return func(opts *ServerOptions) {
		opts.Port = port
	}
}

// WithMaxConcurrentRPCs sets the maximum concurrent RPCs.
func WithMaxConcurrentRPCs(max int) ServerOption {
	return func(opts *ServerOptions) {
		opts.MaxConcurrentRPCs = max
	}
}

// WithReflection enables or disables server reflection.
func WithReflection(enable bool) ServerOption {
	return func(opts *ServerOptions) {
		opts.EnableReflection = enable
	}
}

// NewServer creates a new gRPC server with the given options and interceptors.
//
// Example:
//
//	server := NewServer(
//	    WithPort("50051"),
//	    WithMaxConcurrentRPCs(100),
//	)
func NewServer(
	interceptors []grpc.ServerOption,
	options ...ServerOption,
) *grpc.Server {
	opts := DefaultServerOptions()
	for _, opt := range options {
		opt(opts)
	}

	// Build server options
	serverOpts := []grpc.ServerOption{
		grpc.MaxConcurrentStreams(uint32(opts.MaxConcurrentRPCs)),
		grpc.ConnectionTimeout(opts.MaxConnectionIdle),
		grpc.KeepaliveParams(keepaliveServerParams(opts)),
	}

	// Add interceptors
	serverOpts = append(serverOpts, interceptors...)

	// Create server
	server := grpc.NewServer(serverOpts...)

	// Register health check
	if opts.EnableHealthCheck {
		healthServer := health.NewServer()
		grpc_health_v1.RegisterHealthServer(server, healthServer)
		healthServer.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)
		log.Println("Health check service registered")
	}

	// Enable reflection
	if opts.EnableReflection {
		reflection.Register(server)
		log.Println("Server reflection enabled")
	}

	log.Printf("gRPC server created (max_concurrent_rpcs=%d)", opts.MaxConcurrentRPCs)

	return server
}

// StartServerWithGracefulShutdown starts the server and handles graceful shutdown.
//
// Example:
//
//	server := NewServer()
//	// Register your services here
//	StartServerWithGracefulShutdown(server, DefaultServerOptions())
func StartServerWithGracefulShutdown(server *grpc.Server, opts *ServerOptions) error {
	// Create listener
	lis, err := net.Listen("tcp", ":"+opts.Port)
	if err != nil {
		log.Printf("Failed to listen on port %s: %v", opts.Port, err)
		return err
	}

	log.Printf("gRPC server listening on port %s", opts.Port)

	// Start server in goroutine
	errChan := make(chan error, 1)
	go func() {
		if err := server.Serve(lis); err != nil {
			errChan <- err
		}
	}()

	// Setup graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGTERM, syscall.SIGINT)

	// Wait for signal or error
	select {
	case err := <-errChan:
		log.Printf("Server error: %v", err)
		return err
	case sig := <-sigChan:
		log.Printf("Received signal %v, initiating graceful shutdown", sig)

		// Graceful stop with timeout
		done := make(chan struct{})
		go func() {
			server.GracefulStop()
			close(done)
		}()

		select {
		case <-done:
			log.Println("Server stopped gracefully")
		case <-time.After(opts.GracefulStopTimeout):
			log.Println("Graceful stop timeout, forcing shutdown")
			server.Stop()
		}
	}

	return nil
}

// keepaliveServerParams returns keepalive parameters for the server.
func keepaliveServerParams(opts *ServerOptions) grpc.KeepaliveParams {
	return grpc.KeepaliveParams{
		Time:    opts.KeepaliveTime,
		Timeout: opts.KeepaliveTimeout,
	}
}
