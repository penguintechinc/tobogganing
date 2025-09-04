// Package main implements a high-performance Kubernetes CNI plugin for Tobogganing SASE.
//
// This CNI plugin provides:
// - WireGuard tunnel setup per Kubernetes pod
// - Integration with Tobogganing Manager for centralized orchestration
// - High-performance networking with minimal overhead
// - Support for IPv4 and IPv6 networking
// - Dynamic IP address management (IPAM)
// - Network namespace isolation
// - Zero Trust security model integration
//
// The plugin follows the CNI specification v1.0.0 and implements all required commands:
// ADD, DEL, CHECK, and VERSION for complete Kubernetes integration.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"runtime"

	"github.com/containernetworking/cni/pkg/skel"
	"github.com/containernetworking/cni/pkg/types"
	current "github.com/containernetworking/cni/pkg/types/100"
	"github.com/containernetworking/cni/pkg/version"
	"github.com/sirupsen/logrus"
	"github.com/tobogganing/k8s-cni/pkg/cni"
	"github.com/tobogganing/k8s-cni/pkg/config"
)

var (
	// BuildVersion is set at compile time
	BuildVersion = "dev"
	// GitCommit is set at compile time
	GitCommit = "unknown"
)

// pluginVersion defines supported CNI spec versions
var pluginVersion = version.PluginSupports("0.3.0", "0.3.1", "0.4.0", "1.0.0")

func main() {
	// Initialize logging
	initLogging()

	// Parse command line to determine operation
	skel.PluginMain(cmdAdd, cmdDel, cmdCheck, pluginVersion, "Tobogganing CNI plugin")
}

func initLogging() {
	// Set up structured logging
	logrus.SetFormatter(&logrus.JSONFormatter{})
	logrus.SetOutput(os.Stderr)
	
	// Set log level from environment
	if level := os.Getenv("TOBOGGANING_CNI_LOG_LEVEL"); level != "" {
		if l, err := logrus.ParseLevel(level); err == nil {
			logrus.SetLevel(l)
		}
	} else {
		logrus.SetLevel(logrus.InfoLevel)
	}
	
	logrus.WithFields(logrus.Fields{
		"version":   BuildVersion,
		"gitCommit": GitCommit,
		"runtime":   runtime.Version(),
	}).Info("Tobogganing CNI plugin starting")
}

// cmdAdd implements the ADD command for setting up pod networking
func cmdAdd(args *skel.CmdArgs) error {
	logrus.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"netns":       args.Netns,
		"ifName":      args.IfName,
	}).Info("CNI ADD command")

	// Parse network configuration
	conf, err := config.ParseNetworkConfig(args.StdinData)
	if err != nil {
		return fmt.Errorf("failed to parse network config: %w", err)
	}

	// Create CNI handler
	handler, err := cni.NewHandler(conf)
	if err != nil {
		return fmt.Errorf("failed to create CNI handler: %w", err)
	}
	defer func() {
		if closeErr := handler.Close(); closeErr != nil {
			logrus.WithError(closeErr).Warn("failed to close CNI handler")
		}
	}()

	// Setup pod networking
	ctx := context.Background()
	result, err := handler.Add(ctx, args)
	if err != nil {
		return fmt.Errorf("failed to setup pod networking: %w", err)
	}

	// Return result to CNI runtime
	return types.PrintResult(result, conf.CNIVersion)
}

// cmdDel implements the DEL command for tearing down pod networking
func cmdDel(args *skel.CmdArgs) error {
	logrus.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"netns":       args.Netns,
		"ifName":      args.IfName,
	}).Info("CNI DEL command")

	// Parse network configuration
	conf, err := config.ParseNetworkConfig(args.StdinData)
	if err != nil {
		// For DELETE operations, we should be more lenient with config parsing
		// as the pod might be terminating due to config issues
		logrus.WithError(err).Warn("failed to parse network config during delete, continuing")
		return nil
	}

	// Create CNI handler
	handler, err := cni.NewHandler(conf)
	if err != nil {
		logrus.WithError(err).Warn("failed to create CNI handler during delete, continuing")
		return nil
	}
	defer func() {
		if closeErr := handler.Close(); closeErr != nil {
			logrus.WithError(closeErr).Warn("failed to close CNI handler")
		}
	}()

	// Cleanup pod networking
	ctx := context.Background()
	if err := handler.Del(ctx, args); err != nil {
		// Log the error but don't fail the delete operation
		// as the pod is being terminated anyway
		logrus.WithError(err).Warn("failed to cleanup pod networking, continuing")
	}

	return nil
}

// cmdCheck implements the CHECK command for verifying pod networking
func cmdCheck(args *skel.CmdArgs) error {
	logrus.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"netns":       args.Netns,
		"ifName":      args.IfName,
	}).Info("CNI CHECK command")

	// Parse network configuration
	conf, err := config.ParseNetworkConfig(args.StdinData)
	if err != nil {
		return fmt.Errorf("failed to parse network config: %w", err)
	}

	// Parse previous result
	var prevResult *current.Result
	if conf.PrevResult != nil {
		if result, err := current.GetResult(conf.PrevResult); err != nil {
			return fmt.Errorf("failed to parse previous result: %w", err)
		} else {
			prevResult = result
		}
	}

	// Create CNI handler
	handler, err := cni.NewHandler(conf)
	if err != nil {
		return fmt.Errorf("failed to create CNI handler: %w", err)
	}
	defer func() {
		if closeErr := handler.Close(); closeErr != nil {
			logrus.WithError(closeErr).Warn("failed to close CNI handler")
		}
	}()

	// Check pod networking
	ctx := context.Background()
	if err := handler.Check(ctx, args, prevResult); err != nil {
		return fmt.Errorf("networking check failed: %w", err)
	}

	return nil
}

// buildInfo returns build information for debugging
func buildInfo() map[string]interface{} {
	return map[string]interface{}{
		"version":   BuildVersion,
		"gitCommit": GitCommit,
		"goVersion": runtime.Version(),
		"compiler":  runtime.Compiler,
		"platform":  runtime.GOOS + "/" + runtime.GOARCH,
	}
}

// init sets up any required initialization
func init() {
	// Set maximum number of OS threads for better performance
	runtime.GOMAXPROCS(runtime.NumCPU())
	
	// Enable debug information in case of panic
	if os.Getenv("TOBOGGANING_CNI_DEBUG") == "true" {
		runtime.SetBlockProfileRate(1)
		runtime.SetMutexProfileFraction(1)
	}
}