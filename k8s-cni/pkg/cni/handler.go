// Package cni implements the core CNI plugin functionality for Tobogganing.
//
// This package provides:
// - High-performance ADD/DEL/CHECK command implementations
// - WireGuard tunnel management per pod
// - Integration with Tobogganing Manager service
// - Network namespace management
// - IP address allocation and management
// - Performance optimizations for minimal overhead
//
// The handler coordinates between the CNI runtime, WireGuard networking,
// and the Tobogganing Manager service to provide secure Zero Trust
// networking for Kubernetes pods.
package cni

import (
	"context"
	"fmt"
	"net"
	"runtime"
	"sync"
	"time"

	"github.com/containernetworking/cni/pkg/skel"
	"github.com/containernetworking/cni/pkg/types"
	current "github.com/containernetworking/cni/pkg/types/100"
	"github.com/sirupsen/logrus"
	"github.com/vishvananda/netlink"
	"github.com/vishvananda/netns"
	
	"github.com/tobogganing/k8s-cni/pkg/config"
	"github.com/tobogganing/k8s-cni/pkg/network"
	"github.com/tobogganing/k8s-cni/pkg/wireguard"
)

// Handler implements the main CNI plugin logic
type Handler struct {
	config        *config.NetworkConfig
	networkMgr    *network.Manager
	wireguardMgr  *wireguard.Manager
	mu            sync.RWMutex
	setupTimeout  time.Duration
	logger        *logrus.Entry
}

// NewHandler creates a new CNI handler with the given configuration
func NewHandler(conf *config.NetworkConfig) (*Handler, error) {
	logger := logrus.WithFields(logrus.Fields{
		"component": "cni-handler",
		"network":   conf.Name,
		"cluster":   conf.Tobogganing.ClusterID,
	})

	// Initialize network manager
	networkMgr, err := network.NewManager(&network.Config{
		IPAM:        conf.IPAM,
		ManagerURL:  conf.Tobogganing.ManagerURL,
		APIKey:      conf.Tobogganing.APIKey,
		ClusterID:   conf.Tobogganing.ClusterID,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create network manager: %w", err)
	}

	// Initialize WireGuard manager
	wireguardMgr, err := wireguard.NewManager(&wireguard.Config{
		InterfacePrefix:     conf.Tobogganing.WireGuard.InterfacePrefix,
		KeyPath:            conf.Tobogganing.WireGuard.KeyPath,
		MTU:                conf.Tobogganing.WireGuard.MTU,
		ListenPort:         conf.Tobogganing.WireGuard.ListenPort,
		PersistentKeepalive: conf.Tobogganing.WireGuard.PersistentKeepalive,
		ManagerURL:         conf.Tobogganing.ManagerURL,
		APIKey:             conf.Tobogganing.APIKey,
		ClusterID:          conf.Tobogganing.ClusterID,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create WireGuard manager: %w", err)
	}

	handler := &Handler{
		config:       conf,
		networkMgr:   networkMgr,
		wireguardMgr: wireguardMgr,
		setupTimeout: conf.Tobogganing.Performance.SetupTimeout,
		logger:       logger,
	}

	return handler, nil
}

// Add implements the CNI ADD command for setting up pod networking
func (h *Handler) Add(ctx context.Context, args *skel.CmdArgs) (*current.Result, error) {
	h.mu.Lock()
	defer h.mu.Unlock()

	h.logger.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"netns":       args.Netns,
		"ifName":      args.IfName,
	}).Info("setting up pod networking")

	// Create context with timeout
	ctx, cancel := context.WithTimeout(ctx, h.setupTimeout)
	defer cancel()

	// Generate unique interface name for this pod
	podIfName := h.generateInterfaceName(args.ContainerID)

	// Allocate IP address for the pod
	podIP, err := h.networkMgr.AllocateIP(ctx, args.ContainerID)
	if err != nil {
		return nil, fmt.Errorf("failed to allocate IP: %w", err)
	}

	h.logger.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"podIP":       podIP.String(),
		"interface":   podIfName,
	}).Info("allocated IP for pod")

	// Create WireGuard interface for the pod
	wgInterface, err := h.wireguardMgr.CreateInterface(ctx, podIfName, podIP)
	if err != nil {
		// Cleanup allocated IP on failure
		if releaseErr := h.networkMgr.ReleaseIP(ctx, args.ContainerID, podIP); releaseErr != nil {
			h.logger.WithError(releaseErr).Warn("failed to release IP after WireGuard creation failure")
		}
		return nil, fmt.Errorf("failed to create WireGuard interface: %w", err)
	}

	// Setup network namespace and interfaces
	result, err := h.setupPodNetworking(ctx, args, podIfName, podIP, wgInterface)
	if err != nil {
		// Cleanup WireGuard interface and IP on failure
		if cleanupErr := h.wireguardMgr.DestroyInterface(ctx, podIfName); cleanupErr != nil {
			h.logger.WithError(cleanupErr).Warn("failed to cleanup WireGuard interface after setup failure")
		}
		if releaseErr := h.networkMgr.ReleaseIP(ctx, args.ContainerID, podIP); releaseErr != nil {
			h.logger.WithError(releaseErr).Warn("failed to release IP after setup failure")
		}
		return nil, fmt.Errorf("failed to setup pod networking: %w", err)
	}

	h.logger.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"podIP":       podIP.String(),
		"interface":   podIfName,
	}).Info("successfully configured pod networking")

	return result, nil
}

// Del implements the CNI DEL command for tearing down pod networking
func (h *Handler) Del(ctx context.Context, args *skel.CmdArgs) error {
	h.mu.Lock()
	defer h.mu.Unlock()

	h.logger.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"netns":       args.Netns,
		"ifName":      args.IfName,
	}).Info("tearing down pod networking")

	// Generate interface name for this pod
	podIfName := h.generateInterfaceName(args.ContainerID)

	// Get allocated IP for cleanup
	podIP := h.networkMgr.GetAllocatedIP(args.ContainerID)

	// Cleanup WireGuard interface
	if err := h.wireguardMgr.DestroyInterface(ctx, podIfName); err != nil {
		h.logger.WithError(err).Warn("failed to destroy WireGuard interface")
	}

	// Release IP address
	if podIP != nil {
		if err := h.networkMgr.ReleaseIP(ctx, args.ContainerID, podIP); err != nil {
			h.logger.WithError(err).Warn("failed to release IP address")
		}
	}

	// Cleanup network namespace interfaces
	if err := h.cleanupPodNetworking(ctx, args, podIfName); err != nil {
		h.logger.WithError(err).Warn("failed to cleanup pod networking")
	}

	h.logger.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"interface":   podIfName,
	}).Info("successfully cleaned up pod networking")

	return nil
}

// Check implements the CNI CHECK command for verifying pod networking
func (h *Handler) Check(ctx context.Context, args *skel.CmdArgs, prevResult *current.Result) error {
	h.mu.RLock()
	defer h.mu.RUnlock()

	h.logger.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"netns":       args.Netns,
		"ifName":      args.IfName,
	}).Info("checking pod networking")

	if prevResult == nil {
		return fmt.Errorf("no previous result to check against")
	}

	// Generate interface name for this pod
	podIfName := h.generateInterfaceName(args.ContainerID)

	// Check if WireGuard interface exists and is configured
	if err := h.wireguardMgr.CheckInterface(ctx, podIfName); err != nil {
		return fmt.Errorf("WireGuard interface check failed: %w", err)
	}

	// Check network namespace configuration
	if err := h.checkPodNetworking(ctx, args, prevResult); err != nil {
		return fmt.Errorf("pod networking check failed: %w", err)
	}

	h.logger.WithFields(logrus.Fields{
		"containerID": args.ContainerID,
		"interface":   podIfName,
	}).Info("pod networking check passed")

	return nil
}

// Close cleans up resources used by the handler
func (h *Handler) Close() error {
	var errs []error

	if h.wireguardMgr != nil {
		if err := h.wireguardMgr.Close(); err != nil {
			errs = append(errs, fmt.Errorf("failed to close WireGuard manager: %w", err))
		}
	}

	if h.networkMgr != nil {
		if err := h.networkMgr.Close(); err != nil {
			errs = append(errs, fmt.Errorf("failed to close network manager: %w", err))
		}
	}

	if len(errs) > 0 {
		return fmt.Errorf("cleanup errors: %v", errs)
	}

	return nil
}

// generateInterfaceName creates a unique interface name for the pod
func (h *Handler) generateInterfaceName(containerID string) string {
	prefix := h.config.Tobogganing.WireGuard.InterfacePrefix
	if prefix == "" {
		prefix = "tob"
	}
	
	// Use first 12 characters of container ID for uniqueness
	shortID := containerID
	if len(shortID) > 12 {
		shortID = shortID[:12]
	}
	
	return fmt.Sprintf("%s-%s", prefix, shortID)
}

// setupPodNetworking configures networking inside the pod's network namespace
func (h *Handler) setupPodNetworking(ctx context.Context, args *skel.CmdArgs, podIfName string, podIP net.IP, wgInterface *wireguard.Interface) (*current.Result, error) {
	// Enter the pod's network namespace
	podNs, err := netns.GetFromPath(args.Netns)
	if err != nil {
		return nil, fmt.Errorf("failed to get network namespace: %w", err)
	}
	defer podNs.Close()

	// Switch to pod's network namespace
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	originNs, err := netns.Get()
	if err != nil {
		return nil, fmt.Errorf("failed to get current netns: %w", err)
	}
	defer originNs.Close()

	if err := netns.Set(podNs); err != nil {
		return nil, fmt.Errorf("failed to switch to pod netns: %w", err)
	}
	defer func() {
		if err := netns.Set(originNs); err != nil {
			h.logger.WithError(err).Error("failed to switch back to runtime netns")
		}
	}()

	// Create veth pair
	vethHost := podIfName + "-host"
	vethPod := args.IfName

	veth := &netlink.Veth{
		LinkAttrs: netlink.LinkAttrs{
			Name: vethHost,
			MTU:  h.config.Tobogganing.WireGuard.MTU,
		},
		PeerName: vethPod,
	}

	if err := netlink.LinkAdd(veth); err != nil {
		return nil, fmt.Errorf("failed to create veth pair: %w", err)
	}

	// Get the pod-side veth interface
	podVeth, err := netlink.LinkByName(vethPod)
	if err != nil {
		return nil, fmt.Errorf("failed to get pod veth: %w", err)
	}

	// Configure IP address on pod interface
	addr := &netlink.Addr{
		IPNet: &net.IPNet{
			IP:   podIP,
			Mask: net.CIDRMask(32, 32), // /32 for point-to-point
		},
	}

	if err := netlink.AddrAdd(podVeth, addr); err != nil {
		return nil, fmt.Errorf("failed to add IP address: %w", err)
	}

	// Bring up the pod interface
	if err := netlink.LinkSetUp(podVeth); err != nil {
		return nil, fmt.Errorf("failed to bring up pod interface: %w", err)
	}

	// Move host-side veth to root namespace and connect to WireGuard
	hostVeth, err := netlink.LinkByName(vethHost)
	if err != nil {
		return nil, fmt.Errorf("failed to get host veth: %w", err)
	}

	// Switch back to root namespace to move interface
	if err := netns.Set(originNs); err != nil {
		return nil, fmt.Errorf("failed to switch back to root netns: %w", err)
	}

	if err := netlink.LinkSetNsFd(hostVeth, int(originNs)); err != nil {
		return nil, fmt.Errorf("failed to move host veth to root netns: %w", err)
	}

	// Configure host-side veth and connect to WireGuard bridge
	if err := h.connectToWireGuard(ctx, vethHost, wgInterface); err != nil {
		return nil, fmt.Errorf("failed to connect to WireGuard: %w", err)
	}

	// Create CNI result
	result := &current.Result{
		CNIVersion: h.config.CNIVersion,
		IPs: []*current.IPConfig{
			{
				Address: net.IPNet{
					IP:   podIP,
					Mask: net.CIDRMask(32, 32),
				},
				Interface: current.Int(0), // Pod interface index
			},
		},
		Interfaces: []*current.Interface{
			{
				Name:    vethPod,
				Mac:     podVeth.Attrs().HardwareAddr.String(),
				Sandbox: args.Netns,
			},
		},
		Routes: []*types.Route{
			{
				Dst: net.IPNet{
					IP:   net.IPv4zero,
					Mask: net.CIDRMask(0, 32),
				},
				GW: podIP, // Default route through WireGuard
			},
		},
	}

	return result, nil
}

// cleanupPodNetworking removes networking configuration from the pod
func (h *Handler) cleanupPodNetworking(ctx context.Context, args *skel.CmdArgs, podIfName string) error {
	// Host-side veth cleanup
	vethHost := podIfName + "-host"
	if hostVeth, err := netlink.LinkByName(vethHost); err == nil {
		if err := netlink.LinkDel(hostVeth); err != nil {
			h.logger.WithError(err).Warn("failed to delete host veth interface")
		}
	}

	// Pod-side cleanup happens automatically when network namespace is destroyed
	return nil
}

// checkPodNetworking verifies the pod's networking configuration
func (h *Handler) checkPodNetworking(ctx context.Context, args *skel.CmdArgs, prevResult *current.Result) error {
	// Enter the pod's network namespace
	podNs, err := netns.GetFromPath(args.Netns)
	if err != nil {
		return fmt.Errorf("failed to get network namespace: %w", err)
	}
	defer podNs.Close()

	// Switch to pod's network namespace
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	originNs, err := netns.Get()
	if err != nil {
		return fmt.Errorf("failed to get current netns: %w", err)
	}
	defer originNs.Close()

	if err := netns.Set(podNs); err != nil {
		return fmt.Errorf("failed to switch to pod netns: %w", err)
	}
	defer func() {
		if err := netns.Set(originNs); err != nil {
			h.logger.WithError(err).Error("failed to switch back to runtime netns")
		}
	}()

	// Check if pod interface exists
	podIface, err := netlink.LinkByName(args.IfName)
	if err != nil {
		return fmt.Errorf("pod interface %s not found: %w", args.IfName, err)
	}

	// Check if interface is up
	if podIface.Attrs().Flags&net.FlagUp == 0 {
		return fmt.Errorf("pod interface %s is down", args.IfName)
	}

	// Check IP configuration
	addrs, err := netlink.AddrList(podIface, netlink.FAMILY_V4)
	if err != nil {
		return fmt.Errorf("failed to get interface addresses: %w", err)
	}

	if len(addrs) == 0 {
		return fmt.Errorf("no IP addresses configured on pod interface")
	}

	// Verify IP matches expected
	expectedIP := prevResult.IPs[0].Address.IP
	found := false
	for _, addr := range addrs {
		if addr.IP.Equal(expectedIP) {
			found = true
			break
		}
	}

	if !found {
		return fmt.Errorf("expected IP %s not found on pod interface", expectedIP)
	}

	return nil
}

// connectToWireGuard connects the host veth interface to the WireGuard network
func (h *Handler) connectToWireGuard(ctx context.Context, vethHost string, wgInterface *wireguard.Interface) error {
	// This would typically involve:
	// 1. Creating a bridge interface
	// 2. Adding the veth and WireGuard interfaces to the bridge
	// 3. Setting up routing and firewall rules
	
	// For now, we'll do basic interface configuration
	hostVeth, err := netlink.LinkByName(vethHost)
	if err != nil {
		return fmt.Errorf("failed to get host veth: %w", err)
	}

	// Bring up the host interface
	if err := netlink.LinkSetUp(hostVeth); err != nil {
		return fmt.Errorf("failed to bring up host veth: %w", err)
	}

	h.logger.WithFields(logrus.Fields{
		"vethHost":    vethHost,
		"wgInterface": wgInterface.Name,
	}).Info("connected pod to WireGuard network")

	return nil
}

// String returns a string representation of the handler
func (h *Handler) String() string {
	return fmt.Sprintf("CNIHandler{network=%s, cluster=%s}", 
		h.config.Name, h.config.Tobogganing.ClusterID)
}