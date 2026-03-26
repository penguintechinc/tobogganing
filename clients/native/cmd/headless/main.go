package main

import (
	"log"
	"os"

	pglog "github.com/penguintechinc/penguin-libs/packages/go-common/logging"
	"github.com/spf13/cobra"
	"github.com/tobogganing/clients/native/internal/config"
	"go.uber.org/zap"
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "sasewaddle-client",
		Short: "SASEWaddle Native Client",
		Long:  "A native client for SASEWaddle SASE solution",
		Run:   runClient,
	}

	var configFile string
	rootCmd.PersistentFlags().StringVar(&configFile, "config", "", "config file path")

	if err := rootCmd.Execute(); err != nil {
		log.Fatal(err)
	}
}

func runClient(cmd *cobra.Command, args []string) {
	logger, err := pglog.NewSanitizedLogger("sasewaddle-client-headless")
	if err != nil {
		log.Fatalf("Failed to initialize logger: %v", err)
	}
	defer logger.Sync() //nolint:errcheck

	cfg := config.DefaultConfig()

	configFile, _ := cmd.Flags().GetString("config")
	if configFile != "" {
		if err := config.LoadFromFile(cfg, configFile); err != nil {
			log.Fatalf("Failed to load config: %v", err)
		}
	} else {
		if err := config.LoadFromDefaults(cfg); err != nil {
			log.Fatalf("Failed to load default config: %v", err)
		}
	}

	logger.Info("SASEWaddle Client - Headless Mode",
		zap.String("manager_url", cfg.ManagerURL),
		zap.String("client_type", cfg.ClientType),
		zap.Bool("auto_connect", cfg.AutoConnect),
	)

	if cfg.ManagerURL == "" {
		logger.Error("No manager URL configured",
			zap.String("hint", "set SASEWADDLE_MANAGER_URL environment variable or provide a config file"),
		)
		os.Exit(1)
	}

	logger.Info("Client starting...")
}
