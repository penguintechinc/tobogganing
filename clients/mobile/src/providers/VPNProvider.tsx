/**
 * VPN Provider - Manages WireGuard VPN connection state and operations
 * Provides same functionality as Go client tray VPN manager
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { Platform, NativeModules, NativeEventEmitter, AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Toast from 'react-native-toast-message';

export interface VPNStatus {
  connected: boolean;
  connecting: boolean;
  serverName: string;
  connectedSince: Date | null;
  localIP: string;
  serverIP: string;
  publicKey: string;
  bytesSent: number;
  bytesReceived: number;
  lastHandshake: Date | null;
  error: string | null;
}

export interface VPNProviderType {
  status: VPNStatus;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  reconnect: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  isVPNAvailable: () => boolean;
}

const VPNContext = createContext<VPNProviderType | undefined>(undefined);

// Mock WireGuard module for development
const WireGuardModule = Platform.select({
  ios: NativeModules.WireGuardKit || {
    startTunnel: async () => Promise.resolve(),
    stopTunnel: async () => Promise.resolve(),
    getTunnelStatus: async () => Promise.resolve({
      status: 'disconnected',
      statistics: { bytesSent: 0, bytesReceived: 0 }
    }),
    isWireGuardAvailable: () => true,
  },
  android: NativeModules.WireGuardAndroid || {
    startTunnel: async () => Promise.resolve(),
    stopTunnel: async () => Promise.resolve(),
    getTunnelStatus: async () => Promise.resolve({
      status: 'disconnected',
      statistics: { bytesSent: 0, bytesReceived: 0 }
    }),
    isWireGuardAvailable: () => true,
  },
  default: {
    startTunnel: async () => Promise.resolve(),
    stopTunnel: async () => Promise.resolve(),
    getTunnelStatus: async () => Promise.resolve({
      status: 'disconnected',
      statistics: { bytesSent: 0, bytesReceived: 0 }
    }),
    isWireGuardAvailable: () => false,
  },
});

export const VPNProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<VPNStatus>({
    connected: false,
    connecting: false,
    serverName: '',
    connectedSince: null,
    localIP: '',
    serverIP: '',
    publicKey: '',
    bytesSent: 0,
    bytesReceived: 0,
    lastHandshake: null,
    error: null,
  });

  const [statusCheckInterval, setStatusCheckInterval] = useState<NodeJS.Timeout | null>(null);

  // Initialize VPN status monitoring
  useEffect(() => {
    initializeVPN();
    setupStatusMonitoring();
    setupAppStateHandling();

    return () => {
      if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
      }
    };
  }, []);

  const initializeVPN = async () => {
    try {
      // Load saved server configuration
      const savedConfig = await AsyncStorage.getItem('vpn_config');
      if (savedConfig) {
        const config = JSON.parse(savedConfig);
        setStatus(prev => ({
          ...prev,
          serverName: config.serverName || 'SASEWaddle Server',
          serverIP: config.serverIP || '',
          publicKey: config.publicKey || '',
        }));
      }

      // Check initial VPN status
      await refreshStatus();
    } catch (error) {
      console.error('Failed to initialize VPN:', error);
      setStatus(prev => ({
        ...prev,
        error: 'Failed to initialize VPN',
      }));
    }
  };

  const setupStatusMonitoring = () => {
    // Check status every 5 seconds when connected
    const interval = setInterval(async () => {
      if (status.connected || status.connecting) {
        await refreshStatus();
      }
    }, 5000);

    setStatusCheckInterval(interval);
  };

  const setupAppStateHandling = () => {
    const handleAppStateChange = (nextAppState: string) => {
      if (nextAppState === 'active') {
        // Refresh status when app becomes active
        refreshStatus();
      }
    };

    const subscription = AppState.addEventListener('change', handleAppStateChange);
    return () => subscription?.remove();
  };

  const refreshStatus = useCallback(async () => {
    try {
      const tunnelStatus = await WireGuardModule.getTunnelStatus();
      const isConnected = tunnelStatus.status === 'connected';
      
      setStatus(prev => ({
        ...prev,
        connected: isConnected,
        connecting: tunnelStatus.status === 'connecting',
        bytesSent: tunnelStatus.statistics?.bytesSent || prev.bytesSent,
        bytesReceived: tunnelStatus.statistics?.bytesReceived || prev.bytesReceived,
        lastHandshake: tunnelStatus.statistics?.lastHandshake 
          ? new Date(tunnelStatus.statistics.lastHandshake) 
          : prev.lastHandshake,
        localIP: tunnelStatus.localIP || prev.localIP,
        error: null,
      }));

    } catch (error) {
      console.error('Failed to refresh VPN status:', error);
      setStatus(prev => ({
        ...prev,
        error: 'Failed to get VPN status',
        connecting: false,
      }));
    }
  }, []);

  const connect = useCallback(async () => {
    try {
      setStatus(prev => ({
        ...prev,
        connecting: true,
        error: null,
      }));

      // Get WireGuard configuration
      const configString = await AsyncStorage.getItem('wireguard_config');
      if (!configString) {
        throw new Error('No WireGuard configuration found. Please configure the VPN first.');
      }

      // Start the tunnel
      await WireGuardModule.startTunnel(configString);
      
      // Wait a moment for connection to establish
      setTimeout(async () => {
        await refreshStatus();
        
        setStatus(prev => ({
          ...prev,
          connectedSince: new Date(),
          connecting: false,
        }));

        Toast.show({
          type: 'success',
          text1: 'VPN Connected',
          text2: `Connected to ${status.serverName}`,
        });
      }, 2000);

    } catch (error) {
      console.error('VPN connection failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      
      setStatus(prev => ({
        ...prev,
        connecting: false,
        connected: false,
        error: errorMessage,
      }));

      Toast.show({
        type: 'error',
        text1: 'Connection Failed',
        text2: errorMessage,
      });
    }
  }, [status.serverName]);

  const disconnect = useCallback(async () => {
    try {
      setStatus(prev => ({
        ...prev,
        connecting: true,
        error: null,
      }));

      await WireGuardModule.stopTunnel();
      
      setStatus(prev => ({
        ...prev,
        connected: false,
        connecting: false,
        connectedSince: null,
        localIP: '',
        bytesSent: 0,
        bytesReceived: 0,
        lastHandshake: null,
        error: null,
      }));

      Toast.show({
        type: 'info',
        text1: 'VPN Disconnected',
        text2: 'VPN connection has been terminated',
      });

    } catch (error) {
      console.error('VPN disconnection failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      
      setStatus(prev => ({
        ...prev,
        connecting: false,
        error: errorMessage,
      }));

      Toast.show({
        type: 'error',
        text1: 'Disconnection Failed',
        text2: errorMessage,
      });
    }
  }, []);

  const reconnect = useCallback(async () => {
    if (status.connected) {
      await disconnect();
      // Wait a moment before reconnecting
      setTimeout(async () => {
        await connect();
      }, 1000);
    } else {
      await connect();
    }
  }, [status.connected, connect, disconnect]);

  const isVPNAvailable = useCallback(() => {
    return WireGuardModule.isWireGuardAvailable();
  }, []);

  const value: VPNProviderType = {
    status,
    connect,
    disconnect,
    reconnect,
    refreshStatus,
    isVPNAvailable,
  };

  return (
    <VPNContext.Provider value={value}>
      {children}
    </VPNContext.Provider>
  );
};

export const useVPN = (): VPNProviderType => {
  const context = useContext(VPNContext);
  if (context === undefined) {
    throw new Error('useVPN must be used within a VPNProvider');
  }
  return context;
};