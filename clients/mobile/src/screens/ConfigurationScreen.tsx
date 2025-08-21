/**
 * Configuration Screen - VPN configuration management interface
 * Provides same functionality as Go client tray configuration
 */

import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Alert,
  Switch,
  Modal,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Icon from 'react-native-vector-icons/MaterialIcons';
// import DocumentPicker from 'react-native-document-picker';
// import QRCodeScanner from 'react-native-qrcode-scanner';
// import Share from 'react-native-share';
import { useTheme } from '../providers/ThemeProvider';
import { useConfig } from '../providers/ConfigProvider';

const ConfigurationScreen: React.FC = () => {
  const { colors } = useTheme();
  const { config, updateConfig, pullConfigFromManager, isUpdating, importConfigFromFile, importConfigFromQR, exportConfig } = useConfig();
  
  const [isEditing, setIsEditing] = useState(false);
  const [editedConfig, setEditedConfig] = useState(config);
  const [showQRScanner, setShowQRScanner] = useState(false);
  const [autoUpdate, setAutoUpdate] = useState(true);

  React.useEffect(() => {
    setEditedConfig(config);
  }, [config]);

  const handleSaveConfig = async () => {
    try {
      await updateConfig(editedConfig);
      setIsEditing(false);
    } catch (error) {
      Alert.alert('Error', 'Failed to save configuration');
    }
  };

  const handleCancelEdit = () => {
    setEditedConfig(config);
    setIsEditing(false);
  };

  const handleImportFile = async () => {
    try {
      // For production, this would integrate with platform-specific file picker
      // await importConfigFromFile(configData);
      Alert.alert('Import File', 'Select configuration file to import');
    } catch (error) {
      Alert.alert('Import Error', 'Failed to import configuration file');
    }
  };

  const handleImportQR = () => {
    setShowQRScanner(true);
  };

  const handleQRScan = async (data: string) => {
    setShowQRScanner(false);
    try {
      await importConfigFromQR(data);
    } catch (error) {
      Alert.alert('QR Import Error', 'Failed to import configuration from QR code');
    }
  };

  const handleExportConfig = async () => {
    try {
      const configData = await exportConfig();
      // For production, this would use platform sharing capabilities
      Alert.alert('Export Configuration', 'Configuration exported successfully');
    } catch (error) {
      Alert.alert('Export Error', 'Failed to export configuration');
    }
  };

  const handleTestConnection = async () => {
    if (!config.managerURL || !config.clientID) {
      Alert.alert(
        'Configuration Required',
        'Please configure Manager URL and Client ID first.'
      );
      return;
    }

    Alert.alert(
      'Test Connection',
      'This will attempt to pull configuration from the Manager server.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Test', onPress: pullConfigFromManager },
      ]
    );
  };

  const styles = createStyles(colors);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Manager Configuration Card */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Manager Configuration</Text>
            <TouchableOpacity
              style={styles.editButton}
              onPress={() => setIsEditing(!isEditing)}
            >
              <Icon 
                name={isEditing ? 'cancel' : 'edit'} 
                size={24} 
                color={colors.primary} 
              />
            </TouchableOpacity>
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Manager URL</Text>
            <TextInput
              style={styles.textInput}
              value={isEditing ? editedConfig.managerURL : config.managerURL}
              onChangeText={(text) => setEditedConfig({ ...editedConfig, managerURL: text })}
              placeholder="https://manager.example.com"
              placeholderTextColor={colors.textSecondary}
              editable={isEditing}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Client ID</Text>
            <TextInput
              style={styles.textInput}
              value={isEditing ? editedConfig.clientID : config.clientID}
              onChangeText={(text) => setEditedConfig({ ...editedConfig, clientID: text })}
              placeholder="client-uuid-here"
              placeholderTextColor={colors.textSecondary}
              editable={isEditing}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>API Key</Text>
            <TextInput
              style={styles.textInput}
              value={isEditing ? editedConfig.apiKey : config.apiKey}
              onChangeText={(text) => setEditedConfig({ ...editedConfig, apiKey: text })}
              placeholder="api-key-here"
              placeholderTextColor={colors.textSecondary}
              editable={isEditing}
              secureTextEntry={!isEditing}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Server Name</Text>
            <TextInput
              style={styles.textInput}
              value={isEditing ? editedConfig.serverName : config.serverName}
              onChangeText={(text) => setEditedConfig({ ...editedConfig, serverName: text })}
              placeholder="SASEWaddle Server"
              placeholderTextColor={colors.textSecondary}
              editable={isEditing}
            />
          </View>

          {isEditing && (
            <View style={styles.editActions}>
              <TouchableOpacity
                style={[styles.actionButton, styles.cancelButton]}
                onPress={handleCancelEdit}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, styles.saveButton]}
                onPress={handleSaveConfig}
              >
                <Text style={styles.saveButtonText}>Save</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Connection Settings Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Connection Settings</Text>
          
          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Text style={styles.settingLabel}>Auto Update Configuration</Text>
              <Text style={styles.settingDescription}>
                Automatically pull configuration updates every 45-60 minutes
              </Text>
            </View>
            <Switch
              value={autoUpdate}
              onValueChange={setAutoUpdate}
              trackColor={{ false: colors.border, true: colors.primary }}
              thumbColor={autoUpdate ? colors.surface : colors.textSecondary}
            />
          </View>

          <TouchableOpacity
            style={styles.actionRow}
            onPress={handleTestConnection}
            disabled={isUpdating}
          >
            <Icon name="wifi-tethering" size={24} color={colors.primary} />
            <Text style={styles.actionText}>Test Connection</Text>
            {isUpdating && (
              <ActivityIndicator size="small" color={colors.primary} />
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionRow}
            onPress={pullConfigFromManager}
            disabled={isUpdating}
          >
            <Icon name="sync" size={24} color={colors.primary} />
            <Text style={styles.actionText}>
              {isUpdating ? 'Updating...' : 'Pull Configuration Now'}
            </Text>
            {isUpdating && (
              <ActivityIndicator size="small" color={colors.primary} />
            )}
          </TouchableOpacity>
        </View>

        {/* Import/Export Card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Import / Export</Text>
          
          <TouchableOpacity
            style={styles.actionRow}
            onPress={handleImportFile}
          >
            <Icon name="file-upload" size={24} color={colors.primary} />
            <Text style={styles.actionText}>Import from File</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionRow}
            onPress={handleImportQR}
          >
            <Icon name="qr-code-scanner" size={24} color={colors.primary} />
            <Text style={styles.actionText}>Import from QR Code</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionRow}
            onPress={handleExportConfig}
          >
            <Icon name="file-download" size={24} color={colors.primary} />
            <Text style={styles.actionText}>Export Configuration</Text>
          </TouchableOpacity>
        </View>

        {/* Current Configuration Status */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Configuration Status</Text>
          
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Version:</Text>
            <Text style={styles.statusValue}>{config.version || 'Unknown'}</Text>
          </View>
          
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Last Updated:</Text>
            <Text style={styles.statusValue}>
              {config.lastUpdated 
                ? new Date(config.lastUpdated).toLocaleString()
                : 'Never'
              }
            </Text>
          </View>
          
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Next Update:</Text>
            <Text style={styles.statusValue}>
              {config.nextScheduledUpdate 
                ? new Date(config.nextScheduledUpdate).toLocaleString()
                : 'Not scheduled'
              }
            </Text>
          </View>
          
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>WireGuard Config:</Text>
            <Text style={styles.statusValue}>
              {config.wireguardConfig ? 'Present' : 'Not configured'}
            </Text>
          </View>
        </View>
      </ScrollView>

      {/* QR Code Scanner Modal */}
      <Modal
        visible={showQRScanner}
        animationType="slide"
        onRequestClose={() => setShowQRScanner(false)}
      >
        <View style={styles.qrContainer}>
          <TouchableOpacity
            style={styles.qrCloseButton}
            onPress={() => setShowQRScanner(false)}
          >
            <Icon name="close" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.qrInstructions}>
            QR Code Scanner
          </Text>
          <Text style={styles.qrInstructions}>
            Point your camera at the QR code to import configuration
          </Text>
        </View>
      </Modal>
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
  card: {
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
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
  },
  editButton: {
    padding: 4,
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.text,
    marginBottom: 8,
  },
  textInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 16,
    color: colors.text,
    backgroundColor: colors.background,
  },
  editActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: 16,
    gap: 12,
  },
  actionButton: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    minWidth: 80,
    alignItems: 'center',
  },
  cancelButton: {
    backgroundColor: colors.border,
  },
  saveButton: {
    backgroundColor: colors.primary,
  },
  cancelButtonText: {
    color: colors.text,
    fontWeight: '500',
  },
  saveButtonText: {
    color: 'white',
    fontWeight: '500',
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
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
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
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
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  statusLabel: {
    fontSize: 14,
    color: colors.textSecondary,
    flex: 1,
  },
  statusValue: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.text,
    flex: 2,
    textAlign: 'right',
  },
  qrContainer: {
    flex: 1,
    backgroundColor: 'black',
  },
  qrCloseButton: {
    position: 'absolute',
    top: 50,
    right: 20,
    zIndex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    borderRadius: 20,
    padding: 10,
  },
  qrCamera: {
    height: '70%',
  },
  qrMarker: {
    borderColor: colors.primary,
    borderWidth: 2,
  },
  qrInstructions: {
    color: 'white',
    textAlign: 'center',
    padding: 20,
    fontSize: 16,
  },
});

export default ConfigurationScreen;