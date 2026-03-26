package main

import (
	"fmt"
	"log"
	"os"

	"github.com/tobogganing/clients/native/internal/config"
	"github.com/spf13/cobra"
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "tobogganing-client",
		Short: "Tobogganing Native Client",
		Long:  "A native client for Tobogganing SASE solution",
		Run:   runClient,
	}

	var configFile string
	rootCmd.PersistentFlags().StringVar(&configFile, "config", "", "config file path")

	if err := rootCmd.Execute(); err != nil {
		log.Fatal(err)
	}
}

func runClient(cmd *cobra.Command, args []string) {
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

	fmt.Printf("Tobogganing Client - Headless Mode\n")
	fmt.Printf("Manager URL: %s\n", cfg.ManagerURL)
	fmt.Printf("Client Type: %s\n", cfg.ClientType)
	fmt.Printf("Auto Connect: %v\n", cfg.AutoConnect)
	
	if cfg.ManagerURL == "" {
		fmt.Println("No manager URL configured. Please set TOBOGGANING_MANAGER_URL environment variable or config file.")
		os.Exit(1)
	}
	
	fmt.Println("Client would start here...")
}