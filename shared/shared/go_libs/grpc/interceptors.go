// Package grpc provides security interceptors for authentication, rate limiting, and audit logging.
package grpc

import (
	"context"
	"fmt"
	"log"
	"runtime/debug"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// AuthInterceptor provides JWT authentication for gRPC servers.
type AuthInterceptor struct {
	secretKey     string
	publicMethods map[string]bool
}

// NewAuthInterceptor creates a new authentication interceptor.
//
// Example:
//
//	auth := NewAuthInterceptor("your-secret-key", []string{"/health.Check"})
//	server := NewServer(
//	    []grpc.ServerOption{
//	        grpc.UnaryInterceptor(auth.Unary()),
//	    },
//	)
func NewAuthInterceptor(secretKey string, publicMethods []string) *AuthInterceptor {
	methods := make(map[string]bool)
	for _, method := range publicMethods {
		methods[method] = true
	}

	return &AuthInterceptor{
		secretKey:     secretKey,
		publicMethods: methods,
	}
}

// Unary returns a unary server interceptor for authentication.
func (a *AuthInterceptor) Unary() grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (interface{}, error) {
		// Skip auth for public methods
		if a.publicMethods[info.FullMethod] {
			return handler(ctx, req)
		}

		// Extract token from metadata
		md, ok := metadata.FromIncomingContext(ctx)
		if !ok {
			return nil, status.Error(codes.Unauthenticated, "missing metadata")
		}

		authHeaders := md.Get("authorization")
		if len(authHeaders) == 0 {
			return nil, status.Error(codes.Unauthenticated, "missing authorization header")
		}

		authHeader := authHeaders[0]
		if !strings.HasPrefix(authHeader, "Bearer ") {
			return nil, status.Error(codes.Unauthenticated, "invalid authorization header")
		}

		tokenString := strings.TrimPrefix(authHeader, "Bearer ")

		// Validate JWT token
		token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
			}
			return []byte(a.secretKey), nil
		})

		if err != nil || !token.Valid {
			log.Printf("Invalid token for %s: %v", info.FullMethod, err)
			return nil, status.Error(codes.Unauthenticated, "invalid token")
		}

		// Extract user info from claims
		if claims, ok := token.Claims.(jwt.MapClaims); ok {
			if sub, ok := claims["sub"].(string); ok {
				log.Printf("Authenticated request to %s from user %s", info.FullMethod, sub)
			}
		}

		return handler(ctx, req)
	}
}

// RateLimitInterceptor provides rate limiting for gRPC servers.
type RateLimitInterceptor struct {
	requestsPerMinute int
	perUser           bool
	mu                sync.Mutex
	limits            map[string]*rateLimitEntry
}

type rateLimitEntry struct {
	count       int
	windowStart time.Time
}

// NewRateLimitInterceptor creates a new rate limiting interceptor.
//
// Example:
//
//	rateLimiter := NewRateLimitInterceptor(100, true)
//	server := NewServer(
//	    []grpc.ServerOption{
//	        grpc.UnaryInterceptor(rateLimiter.Unary()),
//	    },
//	)
func NewRateLimitInterceptor(requestsPerMinute int, perUser bool) *RateLimitInterceptor {
	return &RateLimitInterceptor{
		requestsPerMinute: requestsPerMinute,
		perUser:           perUser,
		limits:            make(map[string]*rateLimitEntry),
	}
}

// Unary returns a unary server interceptor for rate limiting.
func (r *RateLimitInterceptor) Unary() grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (interface{}, error) {
		// Determine client identifier
		clientID := "anonymous"

		md, ok := metadata.FromIncomingContext(ctx)
		if ok {
			if r.perUser {
				// Extract user from token
				authHeaders := md.Get("authorization")
				if len(authHeaders) > 0 {
					tokenString := strings.TrimPrefix(authHeaders[0], "Bearer ")
					token, _ := jwt.Parse(tokenString, nil)
					if token != nil {
						if claims, ok := token.Claims.(jwt.MapClaims); ok {
							if sub, ok := claims["sub"].(string); ok {
								clientID = sub
							}
						}
					}
				}
			} else {
				// Use peer address
				if forwarded := md.Get("x-forwarded-for"); len(forwarded) > 0 {
					clientID = forwarded[0]
				}
			}
		}

		// Check rate limit
		r.mu.Lock()
		entry, exists := r.limits[clientID]
		if !exists {
			entry = &rateLimitEntry{
				count:       0,
				windowStart: time.Now(),
			}
			r.limits[clientID] = entry
		}

		now := time.Now()
		if now.Sub(entry.windowStart) >= time.Minute {
			entry.count = 0
			entry.windowStart = now
		}

		if entry.count >= r.requestsPerMinute {
			r.mu.Unlock()
			log.Printf("Rate limit exceeded for %s", clientID)
			return nil, status.Error(codes.ResourceExhausted, "rate limit exceeded")
		}

		entry.count++
		r.mu.Unlock()

		return handler(ctx, req)
	}
}

// AuditInterceptor provides audit logging for gRPC servers.
type AuditInterceptor struct{}

// NewAuditInterceptor creates a new audit logging interceptor.
func NewAuditInterceptor() *AuditInterceptor {
	return &AuditInterceptor{}
}

// Unary returns a unary server interceptor for audit logging.
func (a *AuditInterceptor) Unary() grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (interface{}, error) {
		start := time.Now()

		// Get correlation ID
		correlationID := "unknown"
		if md, ok := metadata.FromIncomingContext(ctx); ok {
			if ids := md.Get("x-correlation-id"); len(ids) > 0 {
				correlationID = ids[0]
			}
		}

		log.Printf("gRPC request started: method=%s correlation_id=%s",
			info.FullMethod, correlationID)

		// Call handler
		resp, err := handler(ctx, req)

		// Log completion
		duration := time.Since(start)
		if err != nil {
			log.Printf("gRPC request failed: method=%s duration=%v correlation_id=%s error=%v",
				info.FullMethod, duration, correlationID, err)
		} else {
			log.Printf("gRPC request completed: method=%s duration=%v correlation_id=%s status=OK",
				info.FullMethod, duration, correlationID)
		}

		return resp, err
	}
}

// CorrelationInterceptor provides correlation ID propagation for request tracing.
type CorrelationInterceptor struct{}

// NewCorrelationInterceptor creates a new correlation ID interceptor.
func NewCorrelationInterceptor() *CorrelationInterceptor {
	return &CorrelationInterceptor{}
}

// Unary returns a unary server interceptor for correlation ID propagation.
func (c *CorrelationInterceptor) Unary() grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (interface{}, error) {
		// Get or create correlation ID
		correlationID := uuid.New().String()

		if md, ok := metadata.FromIncomingContext(ctx); ok {
			if ids := md.Get("x-correlation-id"); len(ids) > 0 {
				correlationID = ids[0]
			}
		}

		// Add correlation ID to outgoing context
		md := metadata.Pairs("x-correlation-id", correlationID)
		ctx = metadata.NewOutgoingContext(ctx, md)

		return handler(ctx, req)
	}
}

// RecoveryInterceptor provides panic recovery for gRPC servers.
type RecoveryInterceptor struct{}

// NewRecoveryInterceptor creates a new recovery interceptor.
func NewRecoveryInterceptor() *RecoveryInterceptor {
	return &RecoveryInterceptor{}
}

// Unary returns a unary server interceptor for panic recovery.
func (r *RecoveryInterceptor) Unary() grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (resp interface{}, err error) {
		defer func() {
			if r := recover(); r != nil {
				stack := debug.Stack()
				log.Printf("Panic recovered in %s: %v\n%s",
					info.FullMethod, r, stack)
				err = status.Errorf(codes.Internal, "internal server error: %v", r)
			}
		}()

		return handler(ctx, req)
	}
}
