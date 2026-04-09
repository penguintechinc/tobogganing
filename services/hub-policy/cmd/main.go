package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/tobogganing/hub-policy/internal/cerberus"
	"github.com/tobogganing/hub-policy/internal/compiler"
	"github.com/tobogganing/hub-policy/internal/push"
	log "github.com/sirupsen/logrus"
)

func main() {
	log.SetFormatter(&log.JSONFormatter{})

	cerberusClient := cerberus.NewClientFromEnv()
	if cerberusClient == nil {
		log.Info("Cerberus integration disabled (CERBERUS_URL not set)")
	}

	pushClient := push.NewClientFromEnv()
	comp := compiler.New()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// TODO: wire hub_api_client sync loop → compiler.Compile() → push to MarchProxy
	_ = comp
	_ = ctx

	// Periodic compile + push loop (placeholder)
	go func() {
		ticker := time.NewTicker(30 * time.Second)
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

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Info("hub-policy shutting down")
}
