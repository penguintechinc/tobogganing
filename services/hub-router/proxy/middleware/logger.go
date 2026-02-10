package middleware

import (
    "time"

    "github.com/gin-gonic/gin"
    log "github.com/sirupsen/logrus"
)

func Logger() gin.HandlerFunc {
    return func(c *gin.Context) {
        start := time.Now()
        path := c.Request.URL.Path
        raw := c.Request.URL.RawQuery
        
        c.Next()
        
        latency := time.Since(start)
        clientIP := c.ClientIP()
        method := c.Request.Method
        statusCode := c.Writer.Status()
        
        if raw != "" {
            path = path + "?" + raw
        }
        
        entry := log.WithFields(log.Fields{
            "client_ip":   clientIP,
            "latency":     latency,
            "method":      method,
            "path":        path,
            "status_code": statusCode,
            "user_agent":  c.Request.UserAgent(),
        })
        
        if statusCode >= 500 {
            entry.Error("Server error")
        } else if statusCode >= 400 {
            entry.Warn("Client error")
        } else {
            entry.Info("Request completed")
        }
    }
}