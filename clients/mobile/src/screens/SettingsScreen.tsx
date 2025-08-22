/**
 * Settings Screen - Application settings and preferences
 * Provides same functionality as Go client tray settings
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  Alert,
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Icon from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '../providers/ThemeProvider';
import { useConfig } from '../providers/ConfigProvider';

interface AppSettings {
  darkMode: boolean;
  autoConnect: boolean;
  notifications: boolean;
  autoUpdate: boolean;
  startOnBoot: boolean;
  killSwitch: boolean;
  logLevel: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  connectionTimeout: number;
  reconnectAttempts: number;
}

const DEFAULT_SETTINGS: AppSettings = {
  darkMode: false,
  autoConnect: true,
  notifications: true,
  autoUpdate: true,
  startOnBoot: false,
  killSwitch: false,
  logLevel: 'INFO',
  connectionTimeout: 30,
  reconnectAttempts: 3,
};

const SettingsScreen: React.FC = () => {
  const { colors, isDarkMode, toggleTheme } = useTheme();
  const { config } = useConfig();
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const savedSettings = await AsyncStorage.getItem('app_settings');
      if (savedSettings) {
        setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(savedSettings) });
      }
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  };

  const saveSettings = async (newSettings: AppSettings) => {
    try {
      await AsyncStorage.setItem('app_settings', JSON.stringify(newSettings));
      setSettings(newSettings);
    } catch (error) {
      console.error('Failed to save settings:', error);
      Alert.alert('Error', 'Failed to save settings');
    }
  };

  const updateSetting = <K extends keyof AppSettings>(
    key: K,
    value: AppSettings[K]
  ) => {
    const newSettings = { ...settings, [key]: value };
    saveSettings(newSettings);
  };

  const handleClearCache = () => {
    Alert.alert(
      'Clear Cache',
      'This will clear all cached data including statistics and temporary files. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: async () => {
            try {
              // Clear specific cache items but preserve config
              await AsyncStorage.removeItem('vpn_statistics');
              await AsyncStorage.removeItem('app_cache');
              Alert.alert('Success', 'Cache cleared successfully');
            } catch (error) {
              Alert.alert('Error', 'Failed to clear cache');
            }
          },
        },
      ]
    );
  };

  const handleResetSettings = () => {
    Alert.alert(
      'Reset Settings',
      'This will reset all application settings to default values. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          style: 'destructive',
          onPress: () => {
            saveSettings(DEFAULT_SETTINGS);
            Alert.alert('Success', 'Settings reset to default');
          },
        },
      ]
    );
  };

  const handleViewLogs = () => {
    // In a real implementation, this would show logs
    Alert.alert('Application Logs', 'Log entries from the VPN client');
  };

  const handleOpenSupport = () => {
    Linking.openURL('https://github.com/penguintechinc/tobogganing/issues');
  };

  const handleOpenDocumentation = () => {
    Linking.openURL('https://tobogganing.com/docs');
  };

  const styles = createStyles(colors);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Appearance Settings */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Appearance</Text>
          
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Text style={styles.settingLabel}>Dark Mode</Text>
              <Text style={styles.settingDescription}>
                Use dark theme for the application
              </Text>
            </View>
            <Switch
              value={isDarkMode}
              onValueChange={toggleTheme}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={isDarkMode ? colors.surface : colors.textSecondary}
            />
          </View>
        </View>

        {/* Connection Settings */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Connection</Text>
          
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Text style={styles.settingLabel}>Auto Connect</Text>
              <Text style={styles.settingDescription}>
                Automatically connect when app starts
              </Text>
            </View>
            <Switch
              value={settings.autoConnect}
              onValueChange={(value) => updateSetting('autoConnect', value)}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={settings.autoConnect ? colors.surface : colors.textSecondary}
            />
          </View>

          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Text style={styles.settingLabel}>Auto Update Configuration</Text>
              <Text style={styles.settingDescription}>
                Automatically pull configuration updates from manager
              </Text>
            </View>
            <Switch
              value={settings.autoUpdate}
              onValueChange={(value) => updateSetting('autoUpdate', value)}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={settings.autoUpdate ? colors.surface : colors.textSecondary}
            />
          </View>

          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Text style={styles.settingLabel}>Kill Switch</Text>
              <Text style={styles.settingDescription}>
                Block internet access when VPN is disconnected
              </Text>
            </View>
            <Switch
              value={settings.killSwitch}
              onValueChange={(value) => updateSetting('killSwitch', value)}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={settings.killSwitch ? colors.surface : colors.textSecondary}
            />
          </View>

          <TouchableOpacity style={styles.actionRow}>
            <Text style={styles.settingLabel}>Connection Timeout</Text>
            <Text style={styles.settingValue}>{settings.connectionTimeout}s</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.actionRow}>
            <Text style={styles.settingLabel}>Reconnect Attempts</Text>
            <Text style={styles.settingValue}>{settings.reconnectAttempts}</Text>
          </TouchableOpacity>
        </View>

        {/* Notification Settings */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Notifications</Text>
          
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Text style={styles.settingLabel}>Enable Notifications</Text>
              <Text style={styles.settingDescription}>
                Show connection status and update notifications
              </Text>
            </View>
            <Switch
              value={settings.notifications}
              onValueChange={(value) => updateSetting('notifications', value)}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={settings.notifications ? colors.surface : colors.textSecondary}
            />
          </View>
        </View>

        {/* Advanced Settings */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Advanced</Text>
          
          <TouchableOpacity style={styles.actionRow}>
            <Text style={styles.settingLabel}>Log Level</Text>
            <Text style={styles.settingValue}>{settings.logLevel}</Text>
          </TouchableOpacity>

          <TouchableOpacity 
            style={styles.actionRow}
            onPress={handleViewLogs}
          >
            <Icon name="description" size={24} color={colors.primary} />
            <Text style={styles.actionText}>View Logs</Text>
            <Icon name="chevron-right" size={24} color={colors.textSecondary} />
          </TouchableOpacity>

          <TouchableOpacity 
            style={styles.actionRow}
            onPress={handleClearCache}
          >
            <Icon name="clear-all" size={24} color={colors.primary} />
            <Text style={styles.actionText}>Clear Cache</Text>
            <Icon name="chevron-right" size={24} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>

        {/* Data & Storage */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Data & Storage</Text>
          
          <View style={styles.infoRow}>
            <Text style={styles.settingLabel}>Configuration Version</Text>
            <Text style={styles.settingValue}>{config.version || 'Unknown'}</Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.settingLabel}>Last Configuration Update</Text>
            <Text style={styles.settingValue}>
              {config.lastUpdated 
                ? new Date(config.lastUpdated).toLocaleDateString()
                : 'Never'
              }
            </Text>
          </View>

          <View style={styles.infoRow}>
            <Text style={styles.settingLabel}>Manager URL</Text>
            <Text style={styles.settingValue} numberOfLines={1} ellipsizeMode="middle">
              {config.managerURL || 'Not configured'}
            </Text>
          </View>
        </View>

        {/* Support & Information */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Support & Information</Text>
          
          <TouchableOpacity 
            style={styles.actionRow}
            onPress={handleOpenDocumentation}
          >
            <Icon name="help" size={24} color={colors.primary} />
            <Text style={styles.actionText}>Documentation</Text>
            <Icon name="open-in-new" size={20} color={colors.textSecondary} />
          </TouchableOpacity>

          <TouchableOpacity 
            style={styles.actionRow}
            onPress={handleOpenSupport}
          >
            <Icon name="support" size={24} color={colors.primary} />
            <Text style={styles.actionText}>Support & Bug Reports</Text>
            <Icon name="open-in-new" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>

        {/* Danger Zone */}
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: colors.error }]}>Danger Zone</Text>
          
          <TouchableOpacity 
            style={[styles.actionRow, styles.dangerRow]}
            onPress={handleResetSettings}
          >
            <Icon name="restore" size={24} color={colors.error} />
            <Text style={[styles.actionText, { color: colors.error }]}>
              Reset All Settings
            </Text>
            <Icon name="chevron-right" size={24} color={colors.error} />
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};

const createStyles = (colors: any) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollView: {
    flex: 1,
    padding: 16,
  },
  section: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    marginBottom: 16,
    overflow: 'hidden',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.text,
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 12,
    backgroundColor: colors.background,
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  settingInfo: {
    flex: 1,
    marginRight: 16,
  },
  settingLabel: {
    fontSize: 16,
    fontWeight: '500',
    color: colors.text,
    marginBottom: 4,
  },
  settingDescription: {
    fontSize: 14,
    color: colors.textSecondary,
    lineHeight: 20,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  actionText: {
    fontSize: 16,
    color: colors.text,
    marginLeft: 16,
    flex: 1,
  },
  settingValue: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.textSecondary,
    textAlign: 'right',
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  dangerRow: {
    backgroundColor: `${colors.error}15`,
  },
});

export default SettingsScreen;