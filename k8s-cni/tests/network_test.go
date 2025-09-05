package tests

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/tobogganing/k8s-cni/pkg/config"
	"github.com/tobogganing/k8s-cni/pkg/network"
)

func TestIPPoolGeneration(t *testing.T) {
	tests := []struct {
		name           string
		subnet         string
		gateway        string
		expectedCount  int
		expectError    bool
	}{
		{
			name:          "small IPv4 subnet /30",
			subnet:        "10.200.0.0/30",
			gateway:       "10.200.0.1",
			expectedCount: 1, // 4 IPs total, minus network, broadcast, gateway = 1 available
			expectError:   false,
		},
		{
			name:          "medium IPv4 subnet /28", 
			subnet:        "10.200.0.0/28",
			gateway:       "10.200.0.1",
			expectedCount: 13, // 16 IPs total, minus network, broadcast, gateway = 13 available
			expectError:   false,
		},
		{
			name:          "IPv6 subnet /126",
			subnet:        "2001:db8::/126",
			gateway:       "2001:db8::1",
			expectedCount: 2, // 4 IPs total, minus network, gateway = 2 available (no broadcast in IPv6)
			expectError:   false,
		},
		{
			name:        "invalid subnet",
			subnet:      "invalid-subnet",
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			conf := &network.Config{
				IPAM: config.IPAMConfig{
					Type:    "tobogganing-ipam",
					Subnet:  tt.subnet,
					Gateway: tt.gateway,
				},
				ManagerURL: "https://test-manager.example.com",
				APIKey:     "test-key",
				ClusterID:  "test-cluster",
			}

			mgr, err := network.NewManager(conf)
			if tt.expectError {
				assert.Error(t, err)
				return
			}

			require.NoError(t, err)
			require.NotNil(t, mgr)

			stats := mgr.GetPoolStats()
			if stats["type"] == "local-pool" {
				assert.Equal(t, tt.expectedCount, stats["availableCount"])
				assert.Equal(t, 0, stats["usedCount"])
			}

			mgr.Close()
		})
	}
}

func TestLocalIPAllocation(t *testing.T) {
	conf := &network.Config{
		IPAM: config.IPAMConfig{
			Type:    "tobogganing-ipam",
			Subnet:  "10.200.1.0/28", // 16 IPs, 13 available after network, broadcast, gateway
			Gateway: "10.200.1.1",
		},
		ManagerURL: "https://test-manager.example.com",
		APIKey:     "test-key",
		ClusterID:  "test-cluster",
	}

	mgr, err := network.NewManager(conf)
	require.NoError(t, err)
	defer mgr.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Test multiple allocations
	containers := []string{"container1", "container2", "container3"}
	allocatedIPs := make(map[string]net.IP)

	// Allocate IPs
	for _, containerID := range containers {
		ip, err := mgr.AllocateIP(ctx, containerID)
		require.NoError(t, err)
		require.NotNil(t, ip)

		// Check IP is in correct subnet
		_, subnet, err := net.ParseCIDR("10.200.1.0/28")
		require.NoError(t, err)
		assert.True(t, subnet.Contains(ip), "IP %s should be in subnet %s", ip, subnet)

		// Check IP is not the gateway
		assert.False(t, ip.Equal(net.ParseIP("10.200.1.1")), "IP should not be gateway")

		// Check IP is unique
		for prevContainer, prevIP := range allocatedIPs {
			assert.False(t, ip.Equal(prevIP), "IP %s already allocated to %s", ip, prevContainer)
		}

		allocatedIPs[containerID] = ip
	}

	// Verify GetAllocatedIP works
	for containerID, expectedIP := range allocatedIPs {
		actualIP := mgr.GetAllocatedIP(containerID)
		assert.True(t, actualIP.Equal(expectedIP), "Expected %s, got %s for container %s", 
			expectedIP, actualIP, containerID)
	}

	// Test double allocation returns same IP
	ip1, err := mgr.AllocateIP(ctx, "container1")
	require.NoError(t, err)
	assert.True(t, ip1.Equal(allocatedIPs["container1"]), "Double allocation should return same IP")

	// Release IPs and verify they can be reallocated
	for containerID, ip := range allocatedIPs {
		err := mgr.ReleaseIP(ctx, containerID, ip)
		assert.NoError(t, err)

		// Verify IP is no longer tracked
		actualIP := mgr.GetAllocatedIP(containerID)
		assert.Nil(t, actualIP, "IP should be nil after release")
	}

	// Test reallocation after release
	newIP, err := mgr.AllocateIP(ctx, "container1")
	require.NoError(t, err)
	require.NotNil(t, newIP)
	
	_, subnet, err := net.ParseCIDR("10.200.1.0/28")
	require.NoError(t, err)
	assert.True(t, subnet.Contains(newIP), "Reallocated IP should be in subnet")
}

func TestIPAllocationExhaustion(t *testing.T) {
	// Use very small subnet to test exhaustion
	conf := &network.Config{
		IPAM: config.IPAMConfig{
			Type:    "tobogganing-ipam",
			Subnet:  "10.200.2.0/30", // Only 4 IPs: network, gateway, 1 available, broadcast
			Gateway: "10.200.2.1",
		},
		ManagerURL: "https://test-manager.example.com",
		APIKey:     "test-key",
		ClusterID:  "test-cluster",
	}

	mgr, err := network.NewManager(conf)
	require.NoError(t, err)
	defer mgr.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Allocate the only available IP
	ip1, err := mgr.AllocateIP(ctx, "container1")
	require.NoError(t, err)
	require.NotNil(t, ip1)

	// Try to allocate another IP - should fail locally
	// Note: In real implementation, this would fall back to manager
	_, err = mgr.AllocateIP(ctx, "container2")
	// For this test, we expect it to fail since we don't have a mock manager
	// In production, it would fall back to the manager service
	assert.Error(t, err, "Should fail when local pool is exhausted and no manager available")

	// Release the IP and verify it becomes available again
	err = mgr.ReleaseIP(ctx, "container1", ip1)
	require.NoError(t, err)

	// Should be able to allocate again
	ip2, err := mgr.AllocateIP(ctx, "container2")
	require.NoError(t, err)
	assert.True(t, ip1.Equal(ip2), "Should get the same IP back after release")
}

func TestIPv6Support(t *testing.T) {
	conf := &network.Config{
		IPAM: config.IPAMConfig{
			Type:    "tobogganing-ipam",
			Subnet:  "2001:db8::/126", // 4 IPv6 addresses
			Gateway: "2001:db8::1",
		},
		ManagerURL: "https://test-manager.example.com",
		APIKey:     "test-key",
		ClusterID:  "test-cluster",
	}

	mgr, err := network.NewManager(conf)
	require.NoError(t, err)
	defer mgr.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Allocate IPv6 address
	ip, err := mgr.AllocateIP(ctx, "container1")
	require.NoError(t, err)
	require.NotNil(t, ip)

	// Verify it's IPv6
	assert.NotNil(t, ip.To16(), "Should be IPv6 address")
	assert.Nil(t, ip.To4(), "Should not be IPv4 address")

	// Verify it's in correct subnet
	_, subnet, err := net.ParseCIDR("2001:db8::/126")
	require.NoError(t, err)
	assert.True(t, subnet.Contains(ip), "IPv6 address should be in subnet")

	// Verify it's not the gateway
	gateway := net.ParseIP("2001:db8::1")
	assert.False(t, ip.Equal(gateway), "IP should not be gateway")
}

func TestGetPoolStats(t *testing.T) {
	conf := &network.Config{
		IPAM: config.IPAMConfig{
			Type:    "tobogganing-ipam",
			Subnet:  "10.200.3.0/28",
			Gateway: "10.200.3.1",
		},
		ManagerURL: "https://test-manager.example.com",
		APIKey:     "test-key",
		ClusterID:  "test-cluster",
	}

	mgr, err := network.NewManager(conf)
	require.NoError(t, err)
	defer mgr.Close()

	// Test initial stats
	stats := mgr.GetPoolStats()
	require.NotNil(t, stats)

	assert.Equal(t, "local-pool", stats["type"])
	assert.Equal(t, "10.200.3.0/28", stats["subnet"])
	assert.Equal(t, "10.200.3.1", stats["gateway"])
	assert.Equal(t, 13, stats["availableCount"]) // 16 - network - broadcast - gateway
	assert.Equal(t, 0, stats["usedCount"])
	assert.Equal(t, 0, stats["allocatedCount"])

	// Allocate some IPs
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err = mgr.AllocateIP(ctx, "container1")
	require.NoError(t, err)
	_, err = mgr.AllocateIP(ctx, "container2")
	require.NoError(t, err)

	// Check updated stats
	stats = mgr.GetPoolStats()
	assert.Equal(t, 11, stats["availableCount"]) // 2 less available
	assert.Equal(t, 2, stats["usedCount"])       // 2 more used
	assert.Equal(t, 2, stats["allocatedCount"])  // 2 allocated
}

func TestManagerOnlyMode(t *testing.T) {
	// Config without local subnet - should use manager-only mode
	conf := &network.Config{
		IPAM: config.IPAMConfig{
			Type: "tobogganing-ipam",
			// No subnet specified
		},
		ManagerURL: "https://test-manager.example.com",
		APIKey:     "test-key",
		ClusterID:  "test-cluster",
	}

	mgr, err := network.NewManager(conf)
	require.NoError(t, err)
	defer mgr.Close()

	// Check stats show manager-only mode
	stats := mgr.GetPoolStats()
	require.NotNil(t, stats)
	assert.Equal(t, "manager-only", stats["type"])
	assert.Equal(t, 0, stats["allocatedCount"])

	// IP allocation would fail in this test since we don't have a real manager
	// but the manager should be properly configured for manager-only mode
}

func TestConcurrentAllocation(t *testing.T) {
	conf := &network.Config{
		IPAM: config.IPAMConfig{
			Type:    "tobogganing-ipam",
			Subnet:  "10.200.4.0/24", // Large subnet for concurrent testing
			Gateway: "10.200.4.1",
		},
		ManagerURL: "https://test-manager.example.com",
		APIKey:     "test-key",
		ClusterID:  "test-cluster",
	}

	mgr, err := network.NewManager(conf)
	require.NoError(t, err)
	defer mgr.Close()

	// Test concurrent allocations
	const numGoroutines = 10
	results := make(chan error, numGoroutines)
	allocatedIPs := make(chan net.IP, numGoroutines)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Start concurrent allocations
	for i := 0; i < numGoroutines; i++ {
		go func(id int) {
			containerID := "container" + string(rune('0'+id))
			ip, err := mgr.AllocateIP(ctx, containerID)
			results <- err
			if err == nil {
				allocatedIPs <- ip
			}
		}(i)
	}

	// Collect results
	var errors []error
	var ips []net.IP
	
	for i := 0; i < numGoroutines; i++ {
		if err := <-results; err != nil {
			errors = append(errors, err)
		}
	}
	
	close(allocatedIPs)
	for ip := range allocatedIPs {
		ips = append(ips, ip)
	}

	// Verify no errors occurred
	assert.Empty(t, errors, "No allocation errors should occur")
	
	// Verify all IPs are unique
	ipMap := make(map[string]bool)
	for _, ip := range ips {
		ipStr := ip.String()
		assert.False(t, ipMap[ipStr], "IP %s should be unique", ipStr)
		ipMap[ipStr] = true
	}
	
	assert.Equal(t, numGoroutines, len(ips), "Should have allocated unique IPs for all goroutines")
}