/**
 * Configuration Provider - Manages configuration updates and scheduling
 * Provides same functionality as Go client config manager
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import BackgroundTimer from 'react-native-background-timer';
import Toast from 'react-native-toast-message';
import axios from 'axios';

export interface ConfigurationData {
  managerURL: string;
  clientID: string;
  apiKey: string;
  serverName: string;
  serverIP: string;
  publicKey: string;
  wireguardConfig: string;
  version: number;
  lastUpdated: Date | null;
  nextScheduledUpdate: Date | null;
}

export interface ConfigProviderType {
  config: ConfigurationData;
  isUpdating: boolean;
  updateConfig: (newConfig: Partial<ConfigurationData>) => Promise<void>;
  pullConfigFromManager: () => Promise<void>;
  getLastConfigUpdate: () => Date | null;
  getNextScheduledUpdate: () => Date | null;
  scheduleNextUpdate: () => void;
  importConfigFromFile: (configString: string) => Promise<void>;
  importConfigFromQR: (qrData: string) => Promise<void>;
  exportConfig: () => Promise<string>;
}

const ConfigContext = createContext<ConfigProviderType | undefined>(undefined);

const DEFAULT_CONFIG: ConfigurationData = {
  managerURL: '',
  clientID: '',
  apiKey: '',
  serverName: 'SASEWaddle Server',
  serverIP: '',
  publicKey: '',
  wireguardConfig: '',
  version: 0,
  lastUpdated: null,
  nextScheduledUpdate: null,
};

export const ConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<ConfigurationData>(DEFAULT_CONFIG);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateTimer, setUpdateTimer] = useState<number | null>(null);

  useEffect(() => {
    loadConfiguration();
    startUpdateScheduler();

    return () => {
      if (updateTimer) {
        BackgroundTimer.clearInterval(updateTimer);
      }
    };
  }, []);

  const loadConfiguration = async () => {
    try {
      const savedConfig = await AsyncStorage.getItem('sasewaddle_config');
      if (savedConfig) {
        const parsedConfig = JSON.parse(savedConfig);
        setConfig({
          ...DEFAULT_CONFIG,
          ...parsedConfig,
          lastUpdated: parsedConfig.lastUpdated ? new Date(parsedConfig.lastUpdated) : null,
          nextScheduledUpdate: parsedConfig.nextScheduledUpdate ? new Date(parsedConfig.nextScheduledUpdate) : null,
        });
      }
    } catch (error) {
      console.error('Failed to load configuration:', error);
      Toast.show({
        type: 'error',
        text1: 'Configuration Error',
        text2: 'Failed to load saved configuration',
      });
    }
  };

  const saveConfiguration = async (newConfig: ConfigurationData) => {
    try {
      await AsyncStorage.setItem('sasewaddle_config', JSON.stringify(newConfig));
      await AsyncStorage.setItem('wireguard_config', newConfig.wireguardConfig);
      await AsyncStorage.setItem('vpn_config', JSON.stringify({
        serverName: newConfig.serverName,
        serverIP: newConfig.serverIP,
        publicKey: newConfig.publicKey,
      }));
    } catch (error) {
      console.error('Failed to save configuration:', error);
      throw new Error('Failed to save configuration');
    }
  };

  const updateConfig = useCallback(async (newConfig: Partial<ConfigurationData>) => {
    try {
      const updatedConfig = {
        ...config,
        ...newConfig,
      };
      
      await saveConfiguration(updatedConfig);
      setConfig(updatedConfig);
      
      Toast.show({
        type: 'success',
        text1: 'Configuration Updated',
        text2: 'Configuration has been saved successfully',
      });
    } catch (error) {
      console.error('Failed to update configuration:', error);
      Toast.show({
        type: 'error',
        text1: 'Update Failed',
        text2: 'Failed to update configuration',
      });
    }
  }, [config]);

  const pullConfigFromManager = useCallback(async () => {
    if (isUpdating) {
      Toast.show({
        type: 'warning',
        text1: 'Update In Progress',
        text2: 'Configuration update already in progress',
      });
      return;
    }

    if (!config.managerURL || !config.clientID) {
      Toast.show({
        type: 'error',
        text1: 'Configuration Missing',
        text2: 'Manager URL and Client ID are required',
      });
      return;
    }

    setIsUpdating(true);

    try {
      const configURL = `${config.managerURL}/api/v1/clients/${config.clientID}/config`;
      
      const headers: { [key: string]: string } = {
        'User-Agent': 'SASEWaddle-Mobile/1.0.0',
        'X-Client-ID': config.clientID,
        'X-Client-Version': '1.0.0',
      };

      if (config.apiKey) {
        headers['Authorization'] = `Bearer ${config.apiKey}`;
      }

      const response = await axios.get(configURL, {
        headers,
        timeout: 30000, // 30 seconds
      });

      if (response.data.success) {
        const newConfig = {
          ...config,
          wireguardConfig: response.data.config,
          version: response.data.version || config.version + 1,
          lastUpdated: new Date(),
        };

        // Parse WireGuard config to extract server details
        const parsedDetails = parseWireGuardConfig(response.data.config);
        if (parsedDetails) {
          newConfig.serverIP = parsedDetails.serverIP;
          newConfig.publicKey = parsedDetails.publicKey;
        }

        await saveConfiguration(newConfig);
        setConfig(newConfig);
        scheduleNextUpdate();

        Toast.show({
          type: 'success',
          text1: 'Configuration Updated',
          text2: `Updated to version ${newConfig.version}`,
        });
      } else {
        throw new Error(response.data.message || 'Server returned error');
      }
    } catch (error) {
      console.error('Failed to pull configuration:', error);
      let errorMessage = 'Unknown error occurred';
      
      if (axios.isAxiosError(error)) {
        if (error.response) {
          errorMessage = `Server error: ${error.response.status}`;
        } else if (error.request) {
          errorMessage = 'Network error - check connection';
        } else {
          errorMessage = error.message;
        }
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }

      Toast.show({
        type: 'error',
        text1: 'Configuration Update Failed',
        text2: errorMessage,
      });

      // Schedule retry with shorter interval (5-10 minutes)
      scheduleRetryUpdate();
    } finally {
      setIsUpdating(false);
    }
  }, [config, isUpdating]);

  const scheduleNextUpdate = useCallback(() => {
    // Random interval between 45-60 minutes (same as Go client)
    const minMinutes = 45;
    const maxMinutes = 60;
    const randomMinutes = minMinutes + Math.floor(Math.random() * (maxMinutes - minMinutes + 1));
    const nextUpdateTime = new Date(Date.now() + randomMinutes * 60 * 1000);
    
    const updatedConfig = {
      ...config,
      nextScheduledUpdate: nextUpdateTime,
    };
    
    setConfig(updatedConfig);
    saveConfiguration(updatedConfig).catch(console.error);
    
    console.log(`Next configuration update scheduled for: ${nextUpdateTime.toLocaleString()}`);
  }, [config]);

  const scheduleRetryUpdate = useCallback(() => {
    // Shorter random interval for retries: 5-10 minutes
    const minMinutes = 5;
    const maxMinutes = 10;
    const randomMinutes = minMinutes + Math.floor(Math.random() * (maxMinutes - minMinutes + 1));
    const nextUpdateTime = new Date(Date.now() + randomMinutes * 60 * 1000);
    
    const updatedConfig = {
      ...config,
      nextScheduledUpdate: nextUpdateTime,
    };
    
    setConfig(updatedConfig);
    saveConfiguration(updatedConfig).catch(console.error);
    
    console.log(`Configuration update retry scheduled for: ${nextUpdateTime.toLocaleString()}`);
  }, [config]);

  const startUpdateScheduler = useCallback(() => {
    // Check every minute if it's time for an update
    const timer = BackgroundTimer.setInterval(() => {
      if (config.nextScheduledUpdate && new Date() >= config.nextScheduledUpdate && !isUpdating) {
        console.log('Triggering scheduled configuration update');
        pullConfigFromManager();
      }
    }, 60000); // 1 minute

    setUpdateTimer(timer);
  }, [config.nextScheduledUpdate, isUpdating, pullConfigFromManager]);

  const parseWireGuardConfig = (configString: string) => {
    try {
      const lines = configString.split('\n');
      let serverIP = '';
      let publicKey = '';

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine.startsWith('Endpoint =')) {
          const endpoint = trimmedLine.split('=')[1].trim();
          serverIP = endpoint.split(':')[0];
        } else if (trimmedLine.startsWith('PublicKey =')) {
          publicKey = trimmedLine.split('=')[1].trim();
        }
      }

      return { serverIP, publicKey };
    } catch (error) {
      console.error('Failed to parse WireGuard config:', error);
      return null;
    }
  };

  const importConfigFromFile = useCallback(async (configString: string) => {
    try {
      // Try to parse as JSON first (SASEWaddle config format)
      let importedConfig: Partial<ConfigurationData>;
      
      try {
        const jsonConfig = JSON.parse(configString);
        importedConfig = {
          managerURL: jsonConfig.managerURL,
          clientID: jsonConfig.clientID,
          apiKey: jsonConfig.apiKey,
          serverName: jsonConfig.serverName || 'SASEWaddle Server',
          wireguardConfig: jsonConfig.wireguardConfig || '',
        };
      } catch {
        // If not JSON, treat as WireGuard config
        const parsedDetails = parseWireGuardConfig(configString);
        importedConfig = {
          wireguardConfig: configString,
          serverIP: parsedDetails?.serverIP || '',
          publicKey: parsedDetails?.publicKey || '',
        };
      }

      await updateConfig(importedConfig);
      
      Toast.show({
        type: 'success',
        text1: 'Configuration Imported',
        text2: 'Configuration has been imported successfully',
      });
    } catch (error) {
      console.error('Failed to import configuration:', error);
      Toast.show({
        type: 'error',
        text1: 'Import Failed',
        text2: 'Failed to import configuration file',
      });
    }
  }, [updateConfig]);

  const importConfigFromQR = useCallback(async (qrData: string) => {
    try {
      await importConfigFromFile(qrData);
    } catch (error) {
      console.error('Failed to import QR configuration:', error);
      Toast.show({
        type: 'error',
        text1: 'QR Import Failed',
        text2: 'Failed to import configuration from QR code',
      });
    }
  }, [importConfigFromFile]);

  const exportConfig = useCallback(async (): Promise<string> => {
    try {
      const exportData = {
        managerURL: config.managerURL,
        clientID: config.clientID,
        apiKey: config.apiKey,
        serverName: config.serverName,
        wireguardConfig: config.wireguardConfig,
        version: config.version,
        exportedAt: new Date().toISOString(),
      };

      return JSON.stringify(exportData, null, 2);
    } catch (error) {
      console.error('Failed to export configuration:', error);
      throw new Error('Failed to export configuration');
    }
  }, [config]);

  const getLastConfigUpdate = useCallback(() => {
    return config.lastUpdated;
  }, [config.lastUpdated]);

  const getNextScheduledUpdate = useCallback(() => {
    return config.nextScheduledUpdate;
  }, [config.nextScheduledUpdate]);

  const value: ConfigProviderType = {
    config,
    isUpdating,
    updateConfig,
    pullConfigFromManager,
    getLastConfigUpdate,
    getNextScheduledUpdate,
    scheduleNextUpdate,
    importConfigFromFile,
    importConfigFromQR,
    exportConfig,
  };

  return (
    <ConfigContext.Provider value={value}>
      {children}
    </ConfigContext.Provider>
  );
};

export const useConfig = (): ConfigProviderType => {
  const context = useContext(ConfigContext);
  if (context === undefined) {
    throw new Error('useConfig must be used within a ConfigProvider');
  }
  return context;
};