package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gorilla/mux"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/auth"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/handlers"
)

func main() {
	log.Println("🐧 WaddlePerf TestServer starting...")

	// Load configuration from environment
	dbConfig := database.Config{
		Host:     getEnv("DB_HOST", "localhost"),
		Port:     getEnv("DB_PORT", "3306"),
		User:     getEnv("DB_USER", "waddleperf"),
		Password: getEnv("DB_PASS", ""),
		Database: getEnv("DB_NAME", "waddleperf"),
	}

	authEnabled := getEnv("AUTH_ENABLED", "true") == "true"
	port := getEnv("PORT", "8080")
	maxConcurrent := getEnv("MAX_CONCURRENT_TESTS", "100")

	log.Printf("Config: auth_enabled=%v, max_concurrent=%s", authEnabled, maxConcurrent)

	// Connect to database
	db, err := database.New(dbConfig)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	// Initialize components
	authenticator := auth.New(db, authEnabled)
	testHandlers := handlers.New(db)

	// Setup router
	router := mux.NewRouter()

	// Health check (no auth required)
	router.HandleFunc("/health", testHandlers.HealthHandler).Methods("GET")

	// SpeedTest endpoints (no auth required for public speedtest functionality)
	speedtest := router.PathPrefix("/speedtest").Subrouter()
	speedtest.Use(corsMiddleware)
	speedtest.HandleFunc("/download", testHandlers.SpeedTestDownloadHandler).Methods("GET")
	speedtest.HandleFunc("/upload", testHandlers.SpeedTestUploadHandler).Methods("POST", "OPTIONS")
	speedtest.HandleFunc("/ping", testHandlers.SpeedTestPingHandler).Methods("GET")
	speedtest.HandleFunc("/info", testHandlers.SpeedTestInfoHandler).Methods("GET")
	speedtest.HandleFunc("/result", testHandlers.SpeedTestResultHandler).Methods("POST", "OPTIONS")

	// API routes (with auth)
	api := router.PathPrefix("/api/v1").Subrouter()
	api.Use(authenticator.Middleware)
	api.Use(corsMiddleware)
	api.Use(requestSizeLimitMiddleware)

	api.HandleFunc("/test/http", testHandlers.HTTPTestHandler).Methods("POST")
	api.HandleFunc("/test/tcp", testHandlers.TCPTestHandler).Methods("POST")
	api.HandleFunc("/test/udp", testHandlers.UDPTestHandler).Methods("POST")
	api.HandleFunc("/test/icmp", testHandlers.ICMPTestHandler).Methods("POST")
	api.HandleFunc("/test/http_trace", testHandlers.HTTPTraceHandler).Methods("POST")
	api.HandleFunc("/test/tcp_trace", testHandlers.TCPTraceHandler).Methods("POST")
	api.HandleFunc("/test/udp_trace", testHandlers.UDPTraceHandler).Methods("POST")
	api.HandleFunc("/test/traceroute", testHandlers.TracerouteHandler).Methods("POST")

	// Create HTTP server
	server := &http.Server{
		Addr:         fmt.Sprintf(":%s", port),
		Handler:      router,
		ReadTimeout:  120 * time.Second, // Increased for speedtest uploads
		WriteTimeout: 120 * time.Second, // Increased for speedtest downloads
		IdleTimeout:  180 * time.Second,
	}

	// Start server in goroutine
	go func() {
		log.Printf("✓ TestServer listening on port %s", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed: %v", err)
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server stopped gracefully")
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Device-Serial, X-Device-Hostname, X-Device-OS, X-Device-OS-Version")

		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// requestSizeLimitMiddleware limits request body size to prevent DoS
func requestSizeLimitMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Limit request body to 1MB (plenty for test requests)
		r.Body = http.MaxBytesReader(w, r.Body, 1*1024*1024)
		next.ServeHTTP(w, r)
	})
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
