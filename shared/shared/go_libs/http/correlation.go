// Package http provides HTTP utilities including correlation ID middleware and resilient HTTP clients.
package http

import (
	"context"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// ContextKey is a type for context keys to avoid collisions.
type contextKey string

const (
	// CorrelationIDKey is the context key for storing correlation IDs.
	correlationIDKey contextKey = "correlation_id"

	// HeaderXCorrelationID is the standard correlation ID header name.
	HeaderXCorrelationID = "X-Correlation-ID"

	// HeaderXRequestID is an alternative request ID header name.
	HeaderXRequestID = "X-Request-ID"
)

// GenerateCorrelationID generates a new correlation ID using UUID v4.
func GenerateCorrelationID() string {
	return uuid.New().String()
}

// GetCorrelationID retrieves the correlation ID from the context.
// Returns empty string if no correlation ID is set.
func GetCorrelationID(ctx context.Context) string {
	if correlationID, ok := ctx.Value(correlationIDKey).(string); ok {
		return correlationID
	}
	return ""
}

// SetCorrelationID stores a correlation ID in the context.
func SetCorrelationID(ctx context.Context, correlationID string) context.Context {
	return context.WithValue(ctx, correlationIDKey, correlationID)
}

// extractCorrelationID extracts correlation ID from request headers or generates a new one.
// Checks X-Correlation-ID first, then X-Request-ID, then generates new UUID.
func extractCorrelationID(c *gin.Context) string {
	// Check X-Correlation-ID first (preferred)
	if correlationID := c.GetHeader(HeaderXCorrelationID); correlationID != "" {
		return correlationID
	}

	// Fall back to X-Request-ID
	if requestID := c.GetHeader(HeaderXRequestID); requestID != "" {
		return requestID
	}

	// Generate new correlation ID
	return GenerateCorrelationID()
}

// CorrelationMiddleware returns a Gin middleware that handles correlation IDs.
// It extracts or generates correlation IDs, stores them in context, and adds them to response headers.
//
// Example:
//
//	router := gin.Default()
//	router.Use(CorrelationMiddleware())
//
//	router.GET("/api/v1/example", func(c *gin.Context) {
//	    correlationID := GetCorrelationID(c.Request.Context())
//	    log.Printf("Processing request with correlation ID: %s", correlationID)
//	    c.JSON(200, gin.H{"status": "ok"})
//	})
func CorrelationMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Extract or generate correlation ID
		correlationID := extractCorrelationID(c)

		// Store in Gin context (for easy access in handlers)
		c.Set(string(correlationIDKey), correlationID)

		// Store in request context (for propagation to services)
		ctx := SetCorrelationID(c.Request.Context(), correlationID)
		c.Request = c.Request.WithContext(ctx)

		// Add to response headers
		c.Header(HeaderXCorrelationID, correlationID)
		c.Header(HeaderXRequestID, correlationID)

		// Process request
		c.Next()
	}
}

// GetCorrelationIDFromGin is a convenience function to get correlation ID from Gin context.
// This is useful when you have direct access to gin.Context but not context.Context.
func GetCorrelationIDFromGin(c *gin.Context) string {
	if correlationID, exists := c.Get(string(correlationIDKey)); exists {
		if id, ok := correlationID.(string); ok {
			return id
		}
	}
	return ""
}
