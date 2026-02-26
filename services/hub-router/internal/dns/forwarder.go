package dns

import (
	"context"
	"strings"
	"sync"
	"time"

	"github.com/miekg/dns"
	log "github.com/sirupsen/logrus"
)

// Forwarder is a UDP+TCP DNS listener that enforces a domain blocklist and
// forwards allowed queries to an upstream DNS resolver.  In the initial
// implementation the upstream is reached via plain DNS-over-UDP; future work
// will route through the Squawk DoH endpoint (configured as SquawkServer).
type Forwarder struct {
	config     Config
	udpServer  *dns.Server
	tcpServer  *dns.Server
	blocked    map[string]bool
	mu         sync.RWMutex
	cancelFunc context.CancelFunc
}

// NewForwarder creates a Forwarder from the supplied configuration.
// Blocked domain names are normalised to lower-case at construction time.
func NewForwarder(cfg Config) *Forwarder {
	blocked := make(map[string]bool, len(cfg.BlockedDomains))
	for _, d := range cfg.BlockedDomains {
		blocked[strings.ToLower(d)] = true
	}
	return &Forwarder{
		config:  cfg,
		blocked: blocked,
	}
}

// Start begins listening for DNS queries on the configured address.
// When cfg.Enabled is false the method returns immediately without
// starting any goroutines.  Start is non-blocking: it spawns internal
// goroutines and returns once both servers are launched.  The provided
// context controls the lifetime of those goroutines.
func (f *Forwarder) Start(ctx context.Context) error {
	if !f.config.Enabled {
		log.Info("DNS forwarder disabled")
		return nil
	}

	ctx, cancel := context.WithCancel(ctx)
	f.cancelFunc = cancel

	handler := dns.HandlerFunc(f.handleDNS)

	f.udpServer = &dns.Server{
		Addr:    f.config.ListenAddr,
		Net:     "udp",
		Handler: handler,
	}
	f.tcpServer = &dns.Server{
		Addr:    f.config.ListenAddr,
		Net:     "tcp",
		Handler: handler,
	}

	go func() {
		if err := f.udpServer.ListenAndServe(); err != nil {
			log.WithError(err).Error("DNS UDP server exited")
		}
	}()
	go func() {
		if err := f.tcpServer.ListenAndServe(); err != nil {
			log.WithError(err).Error("DNS TCP server exited")
		}
	}()

	log.WithField("addr", f.config.ListenAddr).Info("DNS forwarder started")

	go func() {
		<-ctx.Done()
		f.Stop()
	}()

	return nil
}

// Stop gracefully shuts down both DNS servers and cancels the internal context.
// It is safe to call Stop multiple times.
func (f *Forwarder) Stop() {
	if f.udpServer != nil {
		if err := f.udpServer.Shutdown(); err != nil {
			log.WithError(err).Warn("DNS UDP server shutdown error")
		}
	}
	if f.tcpServer != nil {
		if err := f.tcpServer.Shutdown(); err != nil {
			log.WithError(err).Warn("DNS TCP server shutdown error")
		}
	}
	if f.cancelFunc != nil {
		f.cancelFunc()
	}
	log.Info("DNS forwarder stopped")
}

// handleDNS is the miekg/dns.HandlerFunc invoked for every incoming query.
// It checks the domain against the blocklist; blocked queries receive REFUSED.
// Allowed queries are forwarded to the upstream resolver via UDP and the
// response is written back to the caller.
func (f *Forwarder) handleDNS(w dns.ResponseWriter, r *dns.Msg) {
	start := time.Now()

	qtype := "unknown"
	if len(r.Question) > 0 {
		qtype = dns.TypeToString[r.Question[0].Qtype]
	}

	// Blocklist check — O(1) map lookup under a read lock.
	if len(r.Question) > 0 {
		domain := strings.ToLower(strings.TrimSuffix(r.Question[0].Name, "."))
		f.mu.RLock()
		blocked := f.blocked[domain]
		f.mu.RUnlock()

		if blocked {
			dnsBlockedTotal.Inc()
			dnsQueriesTotal.WithLabelValues(qtype, "blocked").Inc()
			msg := new(dns.Msg)
			msg.SetRcode(r, dns.RcodeRefused)
			if err := w.WriteMsg(msg); err != nil {
				log.WithError(err).Warn("Failed to write DNS block response")
			}
			return
		}
	}

	// Forward to upstream.
	// TODO: route through Squawk DoH endpoint (f.config.SquawkServer) using
	// an HTTPS client once the Squawk Go client package is vendored.
	client := new(dns.Client)
	client.Net = "udp"
	upstream := "1.1.1.1:53"

	resp, _, err := client.Exchange(r, upstream)
	if err != nil {
		dnsQueriesTotal.WithLabelValues(qtype, "error").Inc()
		log.WithError(err).Warn("DNS forward failed")
		msg := new(dns.Msg)
		msg.SetRcode(r, dns.RcodeServerFailure)
		if writeErr := w.WriteMsg(msg); writeErr != nil {
			log.WithError(writeErr).Warn("Failed to write DNS error response")
		}
		return
	}

	dnsQueriesTotal.WithLabelValues(qtype, "success").Inc()
	dnsQueryDuration.WithLabelValues(qtype).Observe(time.Since(start).Seconds())

	if err := w.WriteMsg(resp); err != nil {
		log.WithError(err).Warn("Failed to write DNS response")
	}
}

// UpdateBlocklist atomically replaces the domain blocklist.
// All entries are normalised to lower-case.
func (f *Forwarder) UpdateBlocklist(domains []string) {
	newBlocked := make(map[string]bool, len(domains))
	for _, d := range domains {
		newBlocked[strings.ToLower(d)] = true
	}

	f.mu.Lock()
	f.blocked = newBlocked
	f.mu.Unlock()

	log.WithField("count", len(domains)).Info("DNS blocklist updated")
}

// IsRunning returns true if the DNS servers have been initialised.
func (f *Forwarder) IsRunning() bool {
	return f.udpServer != nil
}
