package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/gorilla/mux"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/auth"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/database"
	"github.com/penguintechinc/tobogganing/engines/testserver/internal/handlers"
)

func main() {
	log.Println("🐧 WaddlePerf TestServer starting...")

	// Load configuration from environment — names match the platform
	// convention (hub_api/config: DB_TYPE/DB_HOST/DB_PORT/DB_USER/DB_PASS/DB_NAME).
	dbConfig := database.Config{
		Type:     database.DBType(getEnv("DB_TYPE", string(database.DBTypePostgreSQL))),
		Host:     getEnv("DB_HOST", "localhost"),
		Port:     getEnv("DB_PORT", "5432"),
		User:     getEnv("DB_USER", "testserver"),
		Password: getEnv("DB_PASS", ""),
		Database: getEnv("DB_NAME", "testserver"),
	}

	authEnabled := getEnv("AUTH_ENABLED", "true") == "true"
	port := getEnv("PORT", "8080")
	maxConcurrent := getEnv("MAX_CONCURRENT_TESTS", "100")

	log.Printf("Config: db_type=%s, auth_enabled=%v, max_concurrent=%s", dbConfig.Type, authEnabled, maxConcurrent)

	// The backing store starts degraded so /health and every DB-independent
	// endpoint serve immediately — connectDB dials (with database.New()'s
	// own retry+backoff) in the background and swaps in the live *database.DB
	// on success, without blocking server startup and without ever exiting
	// the process on failure.
	store := newSwitchableStore()
	testHandlers := handlers.NewWithStore(store)
	authenticator := auth.NewWithAuthDB(store, authEnabled)

	go connectDB(dbConfig, store)
	defer func() {
		if db := store.db.Load(); db != nil {
			if err := db.Close(); err != nil {
				log.Printf("error closing database connection: %v", err)
			}
		}
	}()

	// Setup router
	router := mux.NewRouter()

	// Health check (no auth required, no DB dependency)
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
	serverErr := make(chan error, 1)
	go func() {
		log.Printf("✓ TestServer listening on port %s", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	// Wait for interrupt signal or a fatal listener error
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, os.Interrupt, syscall.SIGTERM)

	select {
	case err := <-serverErr:
		log.Printf("Server failed: %v", err)
	case <-quit:
		log.Println("Shutting down server...")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Printf("Server forced to shutdown: %v", err)
	}

	log.Println("Server stopped gracefully")
}

var errDBUnavailable = errors.New("database unavailable")

// switchableStore satisfies both handlers.TestResultStore and auth.AuthDB
// and is safe for concurrent use. It starts with no backing *database.DB
// (every call returns errDBUnavailable) and connectDB atomically swaps in
// the live connection once dialing succeeds — callers never see a nil
// pointer and never block on the initial connection attempt.
type switchableStore struct {
	db atomic.Pointer[database.DB]
}

func newSwitchableStore() *switchableStore {
	return &switchableStore{}
}

func (s *switchableStore) InsertTestResult(result *database.TestResult) (int64, error) {
	db := s.db.Load()
	if db == nil {
		return 0, errDBUnavailable
	}
	return db.InsertTestResult(result)
}

func (s *switchableStore) ValidateAPIKey(apiKey string) (*database.User, error) {
	db := s.db.Load()
	if db == nil {
		return nil, errDBUnavailable
	}
	return db.ValidateAPIKey(apiKey)
}

func (s *switchableStore) ValidateJWT(tokenHash string) (*database.User, error) {
	db := s.db.Load()
	if db == nil {
		return nil, errDBUnavailable
	}
	return db.ValidateJWT(tokenHash)
}

// connectDB dials the database (database.New() already retries with
// backoff internally) and swaps it into store on success. It runs in its
// own goroutine so server startup — and /health specifically — never waits
// on it, and it never calls log.Fatalf/os.Exit: a permanently unreachable
// database degrades probe-result storage and auth, not the whole process.
func connectDB(cfg database.Config, store *switchableStore) {
	db, err := database.New(cfg)
	if err != nil {
		log.Printf("WARNING: database unavailable, continuing in degraded mode: %v", err)
		return
	}
	store.db.Store(db)
	log.Println("✓ database connected — auth and result storage now active")
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
