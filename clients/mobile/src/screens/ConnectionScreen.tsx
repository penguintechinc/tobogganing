/**
 * Connection Screen - Main VPN connection interface
 * Provides same functionality as Go client tray connection controls
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Icon from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '../providers/ThemeProvider';
import { useVPN } from '../providers/VPNProvider';
import { useConfig } from '../providers/ConfigProvider';
import { formatBytes, formatDuration } from '../utils/formatters';

const ConnectionScreen: React.FC = () => {
  const { colors } = useTheme();
  const { status, connect, disconnect, reconnect, refreshStatus, isVPNAvailable } = useVPN();
  const { config, pullConfigFromManager, isUpdating } = useConfig();
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    // Initial status check
    refreshStatus();
  }, []);

  const handleConnectionToggle = async () => {
    if (status.connecting) {
      return; // Prevent action while connecting
    }

    if (status.connected) {
      Alert.alert(
        'Disconnect VPN',
        'Are you sure you want to disconnect from the VPN?',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Disconnect', style: 'destructive', onPress: disconnect },
        ]
      );
    } else {
      if (!config.wireguardConfig) {
        Alert.alert(
          'No Configuration',
          'Please configure the VPN connection first.',
          [
            { text: 'OK' },
            { text: 'Configure', onPress: () => {/* Navigate to config screen */} },
          ]
        );
        return;
      }
      await connect();
    }
  };

  const handleReconnect = async () => {
    Alert.alert(
      'Reconnect VPN',
      'This will disconnect and reconnect the VPN connection.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Reconnect', onPress: reconnect },
      ]
    );
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await refreshStatus();
    setRefreshing(false);
  };

  const handleManualConfigPull = async () => {
    if (!config.managerURL || !config.clientID) {
      Alert.alert(
        'Configuration Required',
        'Please configure Manager URL and Client ID first.',
        [
          { text: 'OK' },
          { text: 'Configure', onPress: () => {/* Navigate to config screen */} },
        ]
      );
      return;
    }

    await pullConfigFromManager();
  };

  const getConnectionStatusColor = () => {
    if (status.connecting) return colors.warning;
    if (status.connected) return colors.success;
    if (status.error) return colors.error;
    return colors.textSecondary;
  };

  const getConnectionStatusText = () => {
    if (status.connecting) return 'Connecting...';
    if (status.connected) return 'Connected';
    if (status.error) return 'Error';
    return 'Disconnected';
  };

  const getConnectionIcon = () => {
    if (status.connecting) return 'sync';
    if (status.connected) return 'vpn-lock';
    if (status.error) return 'error';
    return 'vpn-key';
  };

  const styles = createStyles(colors);

  if (!isVPNAvailable()) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.unavailableContainer}>
          <Icon name="warning" size={64} color={colors.warning} />
          <Text style={styles.unavailableTitle}>VPN Unavailable</Text>
          <Text style={styles.unavailableText}>
            WireGuard VPN is not available on this device. Please check if WireGuard is installed and properly configured.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
      >
        {/* Connection Status Card */}
        <View style={styles.statusCard}>
          <View style={styles.statusHeader}>
            <Icon
              name={getConnectionIcon()}
              size={48}
              color={getConnectionStatusColor()}
            />
            <View style={styles.statusInfo}>
              <Text style={[styles.statusText, { color: getConnectionStatusColor() }]}>
                {getConnectionStatusText()}
              </Text>
              {status.connected && status.connectedSince && (
                <Text style={styles.connectedSince}>
                  Connected for {formatDuration(Date.now() - status.connectedSince.getTime())}
                </Text>
              )}
              {status.error && (
                <Text style={styles.errorText}>{status.error}</Text>
              )}
            </View>
          </View>

          {/* Server Information */}
          {(status.connected || config.serverName) && (
            <View style={styles.serverInfo}>
              <Text style={styles.serverName}>
                {status.connected ? status.serverName : config.serverName}
              </Text>
              {status.serverIP && (
                <Text style={styles.serverIP}>Server: {status.serverIP}</Text>
              )}
              {status.localIP && (
                <Text style={styles.localIP}>Local IP: {status.localIP}</Text>
              )}
            </View>
          )}

          {/* Connection Button */}
          <TouchableOpacity
            style={[
              styles.connectionButton,
              {
                backgroundColor: status.connected
                  ? colors.error
                  : colors.primary,
              },
            ]}
            onPress={handleConnectionToggle}
            disabled={status.connecting}
          >
            {status.connecting ? (
              <ActivityIndicator size="small" color="white" />
            ) : (
              <Text style={styles.connectionButtonText}>
                {status.connected ? 'Disconnect' : 'Connect'}
              </Text>
            )}
          </TouchableOpacity>
        </View>

        {/* Statistics Card */}
        {status.connected && (
          <View style={styles.statsCard}>
            <Text style={styles.cardTitle}>Connection Statistics</Text>
            
            <View style={styles.statsGrid}>
              <View style={styles.statItem}>
                <Icon name="cloud-upload" size={24} color={colors.primary} />
                <Text style={styles.statLabel}>Sent</Text>
                <Text style={styles.statValue}>{formatBytes(status.bytesSent)}</Text>
              </View>
              
              <View style={styles.statItem}>
                <Icon name="cloud-download" size={24} color={colors.primary} />
                <Text style={styles.statLabel}>Received</Text>
                <Text style={styles.statValue}>{formatBytes(status.bytesReceived)}</Text>
              </View>
              
              <View style={styles.statItem}>
                <Icon name="handshake" size={24} color={colors.primary} />
                <Text style={styles.statLabel}>Last Handshake</Text>
                <Text style={styles.statValue}>
                  {status.lastHandshake
                    ? formatDuration(Date.now() - status.lastHandshake.getTime()) + ' ago'
                    : 'Never'
                  }
                </Text>
              </View>
              
              <View style={styles.statItem}>
                <Icon name="fingerprint" size={24} color={colors.primary} />
                <Text style={styles.statLabel}>Public Key</Text>
                <Text style={styles.statValue} numberOfLines={1} ellipsizeMode="middle">
                  {status.publicKey || 'N/A'}
                </Text>
              </View>
            </View>
          </View>
        )}

        {/* Quick Actions Card */}
        <View style={styles.actionsCard}>
          <Text style={styles.cardTitle}>Quick Actions</Text>
          
          <TouchableOpacity
            style={styles.actionButton}
            onPress={handleReconnect}
            disabled={status.connecting || !status.connected}
          >
            <Icon name="refresh" size={24} color={colors.primary} />
            <Text style={styles.actionButtonText}>Reconnect</Text>
          </TouchableOpacity>
          
          <TouchableOpacity
            style={styles.actionButton}
            onPress={handleManualConfigPull}
            disabled={isUpdating}
          >
            <Icon name="sync" size={24} color={colors.primary} />
            <Text style={styles.actionButtonText}>
              {isUpdating ? 'Updating...' : 'Update Configuration'}
            </Text>
            {isUpdating && (
              <ActivityIndicator size="small" color={colors.primary} style={styles.actionSpinner} />
            )}
          </TouchableOpacity>
          
          <TouchableOpacity
            style={styles.actionButton}
            onPress={refreshStatus}
          >
            <Icon name="info" size={24} color={colors.primary} />
            <Text style={styles.actionButtonText}>Refresh Status</Text>
          </TouchableOpacity>
        </View>

        {/* Configuration Status Card */}
        <View style={styles.configCard}>
          <Text style={styles.cardTitle}>Configuration Status</Text>
          
          <View style={styles.configItem}>
            <Text style={styles.configLabel}>Last Updated:</Text>
            <Text style={styles.configValue}>
              {config.lastUpdated
                ? new Date(config.lastUpdated).toLocaleString()
                : 'Never'
              }
            </Text>
          </View>
          
          <View style={styles.configItem}>
            <Text style={styles.configLabel}>Next Update:</Text>
            <Text style={styles.configValue}>
              {config.nextScheduledUpdate
                ? new Date(config.nextScheduledUpdate).toLocaleString()
                : 'Not scheduled'
              }
            </Text>
          </View>
          
          <View style={styles.configItem}>
            <Text style={styles.configLabel}>Version:</Text>
            <Text style={styles.configValue}>{config.version || 'Unknown'}</Text>
          </View>
          
          <View style={styles.configItem}>
            <Text style={styles.configLabel}>Manager URL:</Text>
            <Text style={styles.configValue} numberOfLines={1} ellipsizeMode="middle">
              {config.managerURL || 'Not configured'}
            </Text>
          </View>
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
  unavailableContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  unavailableTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: colors.text,
    marginTop: 16,
    marginBottom: 8,
    textAlign: 'center',
  },
  unavailableText: {
    fontSize: 16,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 24,
  },
  statusCard: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  statusHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  statusInfo: {
    marginLeft: 16,
    flex: 1,
  },
  statusText: {
    fontSize: 24,
    fontWeight: 'bold',
  },
  connectedSince: {
    fontSize: 14,
    color: colors.textSecondary,
    marginTop: 4,
  },
  errorText: {
    fontSize: 14,
    color: colors.error,
    marginTop: 4,
  },
  serverInfo: {
    marginBottom: 20,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  serverName: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
    marginBottom: 4,
  },
  serverIP: {
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: 2,
  },
  localIP: {
    fontSize: 14,
    color: colors.textSecondary,
  },
  connectionButton: {
    borderRadius: 8,
    paddingVertical: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  connectionButtonText: {
    color: 'white',
    fontSize: 18,
    fontWeight: '600',
  },
  statsCard: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  actionsCard: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  configCard: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
    marginBottom: 16,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  statItem: {
    alignItems: 'center',
    width: '48%',
    marginBottom: 16,
    padding: 12,
    backgroundColor: colors.background,
    borderRadius: 8,
  },
  statLabel: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 4,
    textAlign: 'center',
  },
  statValue: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
    marginTop: 2,
    textAlign: 'center',
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    marginBottom: 8,
    backgroundColor: colors.background,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
  },
  actionButtonText: {
    marginLeft: 12,
    fontSize: 16,
    color: colors.text,
    flex: 1,
  },
  actionSpinner: {
    marginLeft: 8,
  },
  configItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  configLabel: {
    fontSize: 14,
    color: colors.textSecondary,
    flex: 1,
  },
  configValue: {
    fontSize: 14,
    color: colors.text,
    fontWeight: '500',
    flex: 2,
    textAlign: 'right',
  },
});

export default ConnectionScreen;