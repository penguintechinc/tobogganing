package tests

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/tobogganing/k8s-cni/pkg/config"
)

func TestParseNetworkConfig(t *testing.T) {
	tests := []struct {
		name        string
		configJSON  string
		expectError bool
		validate    func(*testing.T, *config.NetworkConfig)
	}{
		{
			name: "valid basic config",
			configJSON: `{
				"cniVersion": "1.0.0",
				"name": "tobogganing",
				"type": "tobogganing",
				"tobogganing": {
					"managerURL": "https://manager.example.com",
					"clusterID": "test-cluster"
				},
				"ipam": {
					"type": "tobogganing-ipam",
					"subnet": "10.200.0.0/16"
				}
			}`,
			expectError: false,
			validate: func(t *testing.T, conf *config.NetworkConfig) {
				assert.Equal(t, "1.0.0", conf.CNIVersion)
				assert.Equal(t, "tobogganing", conf.Name)
				assert.Equal(t, "tobogganing", conf.Type)
				assert.Equal(t, "https://manager.example.com", conf.Tobogganing.ManagerURL)
				assert.Equal(t, "test-cluster", conf.Tobogganing.ClusterID)
				assert.Equal(t, "tobogganing-ipam", conf.IPAM.Type)
				assert.Equal(t, "10.200.0.0/16", conf.IPAM.Subnet)
			},
		},
		{
			name: "config with wireguard settings",
			configJSON: `{
				"cniVersion": "1.0.0",
				"name": "tobogganing",
				"type": "tobogganing",
				"tobogganing": {
					"managerURL": "https://manager.example.com",
					"clusterID": "test-cluster",
					"wireguard": {
						"interfacePrefix": "test",
						"mtu": 1500,
						"listenPort": 51820
					}
				},
				"ipam": {
					"type": "tobogganing-ipam"
				}
			}`,
			expectError: false,
			validate: func(t *testing.T, conf *config.NetworkConfig) {
				assert.Equal(t, "test", conf.Tobogganing.WireGuard.InterfacePrefix)
				assert.Equal(t, 1500, conf.Tobogganing.WireGuard.MTU)
				assert.Equal(t, 51820, conf.Tobogganing.WireGuard.ListenPort)
			},
		},
		{
			name: "missing required fields",
			configJSON: `{
				"cniVersion": "1.0.0",
				"name": "tobogganing",
				"type": "tobogganing"
			}`,
			expectError: true,
		},
		{
			name: "invalid subnet",
			configJSON: `{
				"cniVersion": "1.0.0",
				"name": "tobogganing",
				"type": "tobogganing",
				"tobogganing": {
					"managerURL": "https://manager.example.com",
					"clusterID": "test-cluster"
				},
				"ipam": {
					"type": "tobogganing-ipam",
					"subnet": "invalid-subnet"
				}
			}`,
			expectError: true,
		},
		{
			name: "invalid wireguard port",
			configJSON: `{
				"cniVersion": "1.0.0",
				"name": "tobogganing",
				"type": "tobogganing",
				"tobogganing": {
					"managerURL": "https://manager.example.com",
					"clusterID": "test-cluster",
					"wireguard": {
						"listenPort": 999999
					}
				},
				"ipam": {
					"type": "tobogganing-ipam"
				}
			}`,
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			conf, err := config.ParseNetworkConfig([]byte(tt.configJSON))
			
			if tt.expectError {
				assert.Error(t, err)
				return
			}
			
			require.NoError(t, err)
			require.NotNil(t, conf)
			
			if tt.validate != nil {
				tt.validate(t, conf)
			}
		})
	}
}

func TestNetworkConfigDefaults(t *testing.T) {
	configJSON := `{
		"cniVersion": "1.0.0",
		"name": "tobogganing",
		"type": "tobogganing",
		"tobogganing": {
			"managerURL": "https://manager.example.com",
			"clusterID": "test-cluster"
		},
		"ipam": {
			"type": "tobogganing-ipam"
		}
	}`

	conf, err := config.ParseNetworkConfig([]byte(configJSON))
	require.NoError(t, err)

	// Check that defaults are applied
	assert.Equal(t, "tob", conf.Tobogganing.WireGuard.InterfacePrefix)
	assert.Equal(t, 1420, conf.Tobogganing.WireGuard.MTU)
	assert.Equal(t, 25, conf.Tobogganing.WireGuard.PersistentKeepalive)
	assert.Equal(t, "info", conf.Tobogganing.Logging.Level)
	assert.Equal(t, "json", conf.Tobogganing.Logging.Format)
	assert.Equal(t, 26, conf.IPAM.BlockSize)
	assert.Equal(t, 4, conf.Tobogganing.Performance.WorkerCount)
}

func TestNetworkConfigClone(t *testing.T) {
	configJSON := `{
		"cniVersion": "1.0.0",
		"name": "tobogganing",
		"type": "tobogganing",
		"tobogganing": {
			"managerURL": "https://manager.example.com",
			"clusterID": "test-cluster"
		},
		"ipam": {
			"type": "tobogganing-ipam"
		}
	}`

	original, err := config.ParseNetworkConfig([]byte(configJSON))
	require.NoError(t, err)

	clone := original.Clone()
	require.NotNil(t, clone)

	// Verify clone is independent
	clone.Name = "modified"
	assert.Equal(t, "tobogganing", original.Name)
	assert.Equal(t, "modified", clone.Name)
}

func TestNetworkConfigToJSON(t *testing.T) {
	configJSON := `{
		"cniVersion": "1.0.0",
		"name": "tobogganing",
		"type": "tobogganing",
		"tobogganing": {
			"managerURL": "https://manager.example.com",
			"clusterID": "test-cluster"
		},
		"ipam": {
			"type": "tobogganing-ipam"
		}
	}`

	conf, err := config.ParseNetworkConfig([]byte(configJSON))
	require.NoError(t, err)

	jsonStr, err := conf.ToJSON()
	require.NoError(t, err)
	assert.NotEmpty(t, jsonStr)

	// Verify it's valid JSON
	var check map[string]interface{}
	err = json.Unmarshal([]byte(jsonStr), &check)
	assert.NoError(t, err)
}

func TestIPAMValidation(t *testing.T) {
	tests := []struct {
		name        string
		ipam        config.IPAMConfig
		expectError bool
	}{
		{
			name: "valid IPv4 subnet",
			ipam: config.IPAMConfig{
				Type:    "tobogganing-ipam",
				Subnet:  "10.200.0.0/16",
				Gateway: "10.200.0.1",
			},
			expectError: false,
		},
		{
			name: "valid IPv6 subnet",
			ipam: config.IPAMConfig{
				Type:    "tobogganing-ipam",
				Subnet:  "2001:db8::/64",
				Gateway: "2001:db8::1",
			},
			expectError: false,
		},
		{
			name: "invalid subnet format",
			ipam: config.IPAMConfig{
				Type:   "tobogganing-ipam",
				Subnet: "10.200.0.0/33",
			},
			expectError: true,
		},
		{
			name: "invalid gateway IP",
			ipam: config.IPAMConfig{
				Type:    "tobogganing-ipam",
				Subnet:  "10.200.0.0/16",
				Gateway: "invalid-ip",
			},
			expectError: true,
		},
		{
			name: "valid routes",
			ipam: config.IPAMConfig{
				Type:   "tobogganing-ipam",
				Subnet: "10.200.0.0/16",
				Routes: []config.IPAMRoute{
					{
						Dst: "0.0.0.0/0",
						GW:  "10.200.0.1",
					},
				},
			},
			expectError: false,
		},
		{
			name: "invalid route destination",
			ipam: config.IPAMConfig{
				Type:   "tobogganing-ipam",
				Subnet: "10.200.0.0/16",
				Routes: []config.IPAMRoute{
					{
						Dst: "invalid-route",
					},
				},
			},
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			configJSON := `{
				"cniVersion": "1.0.0",
				"name": "tobogganing",
				"type": "tobogganing",
				"tobogganing": {
					"managerURL": "https://manager.example.com",
					"clusterID": "test-cluster"
				},
				"ipam": {}
			}`

			var confMap map[string]interface{}
			err := json.Unmarshal([]byte(configJSON), &confMap)
			require.NoError(t, err)

			// Replace IPAM config
			ipamMap, err := structToMap(tt.ipam)
			require.NoError(t, err)
			confMap["ipam"] = ipamMap

			modifiedJSON, err := json.Marshal(confMap)
			require.NoError(t, err)

			_, err = config.ParseNetworkConfig(modifiedJSON)
			if tt.expectError {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

func TestWireGuardValidation(t *testing.T) {
	tests := []struct {
		name        string
		wireguard   config.WireGuardConfig
		expectError bool
	}{
		{
			name: "valid config",
			wireguard: config.WireGuardConfig{
				InterfacePrefix: "test",
				ListenPort:      51820,
				MTU:             1420,
				AllowedIPs:      []string{"10.200.0.0/16"},
			},
			expectError: false,
		},
		{
			name: "invalid listen port - too low",
			wireguard: config.WireGuardConfig{
				ListenPort: 1000,
			},
			expectError: true,
		},
		{
			name: "invalid listen port - too high",
			wireguard: config.WireGuardConfig{
				ListenPort: 70000,
			},
			expectError: true,
		},
		{
			name: "invalid MTU - too low",
			wireguard: config.WireGuardConfig{
				MTU: 60,
			},
			expectError: true,
		},
		{
			name: "invalid MTU - too high",
			wireguard: config.WireGuardConfig{
				MTU: 10000,
			},
			expectError: true,
		},
		{
			name: "invalid allowed IP",
			wireguard: config.WireGuardConfig{
				AllowedIPs: []string{"invalid-ip"},
			},
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			configJSON := `{
				"cniVersion": "1.0.0",
				"name": "tobogganing",
				"type": "tobogganing",
				"tobogganing": {
					"managerURL": "https://manager.example.com",
					"clusterID": "test-cluster",
					"wireguard": {}
				},
				"ipam": {
					"type": "tobogganing-ipam"
				}
			}`

			var confMap map[string]interface{}
			err := json.Unmarshal([]byte(configJSON), &confMap)
			require.NoError(t, err)

			// Replace WireGuard config
			wgMap, err := structToMap(tt.wireguard)
			require.NoError(t, err)
			
			tobogganing := confMap["tobogganing"].(map[string]interface{})
			tobogganing["wireguard"] = wgMap

			modifiedJSON, err := json.Marshal(confMap)
			require.NoError(t, err)

			_, err = config.ParseNetworkConfig(modifiedJSON)
			if tt.expectError {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

// Helper function to convert struct to map for JSON manipulation
func structToMap(obj interface{}) (map[string]interface{}, error) {
	data, err := json.Marshal(obj)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	err = json.Unmarshal(data, &result)
	if err != nil {
		return nil, err
	}

	return result, nil
}