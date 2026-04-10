package main

import (
	"context"
	"os/signal"
	"syscall"
	"time"

	"github.com/tobogganing/hub-policy/internal/cerberus"
	"github.com/tobogganing/hub-policy/internal/compiler"
	"github.com/tobogganing/hub-policy/internal/push"
	log "github.com/sirupsen/logrus"
)

// pollInterval controls the ticker duration for the policy compile + push loop.
// Exposed at package level to allow tests to override it.
var pollInterval = 30 * time.Second

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if err := run(ctx); err != nil {
		log.Fatal(err)
	}
}

// run executes the hub-policy controller loop until ctx is cancelled.
func run(ctx context.Context) error {
	log.SetFormatter(&log.JSONFormatter{})

	cerberusClient := cerberus.NewClientFromEnv()
	if cerberusClient == nil {
		log.Info("Cerberus integration disabled (CERBERUS_URL not set)")
	}

	pushClient := push.NewClientFromEnv()
	comp := compiler.New()

	// TODO: wire hub_api_client sync loop → compiler.Compile() → push to MarchProxy
	_ = comp

	// Periodic compile + push loop (placeholder)
	go func() {
		ticker := time.NewTicker(pollInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				rules := compiler.CompiledRuleSet{}
				if cerberusClient != nil {
					ips, domains := cerberusClient.GetCurrentBlocklists(ctx)
					rules.BlockCIDRs = append(rules.BlockCIDRs, ips...)
					rules.BlockDomains = append(rules.BlockDomains, domains...)
				}
				if err := pushClient.Push(ctx, rules); err != nil {
					log.WithError(err).Error("Failed to push rules to MarchProxy")
				}
			}
		}
	}()

	<-ctx.Done()
	log.Info("hub-policy shutting down")
	return nil
}
