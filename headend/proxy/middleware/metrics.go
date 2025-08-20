package middleware

import (
    "strconv"
    "time"

    "github.com/gin-gonic/gin"
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    httpDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
        Name: "http_duration_seconds",
        Help: "Duration of HTTP requests.",
    }, []string{"path", "method", "status"})
    
    httpRequests = promauto.NewCounterVec(prometheus.CounterOpts{
        Name: "http_requests_total",
        Help: "Total number of HTTP requests.",
    }, []string{"path", "method", "status"})
)

func Metrics() gin.HandlerFunc {
    return func(c *gin.Context) {
        path := c.Request.URL.Path
        start := time.Now()
        
        c.Next()
        
        status := strconv.Itoa(c.Writer.Status())
        elapsed := time.Since(start).Seconds()
        
        httpDuration.WithLabelValues(path, c.Request.Method, status).Observe(elapsed)
        httpRequests.WithLabelValues(path, c.Request.Method, status).Inc()
    }
}