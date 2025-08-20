/**
 * About Screen - Application information and credits
 * Provides same functionality as Go client tray about dialog
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Linking,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Icon from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '../providers/ThemeProvider';
import { useConfig } from '../providers/ConfigProvider';

const APP_VERSION = '1.0.0';
const BUILD_NUMBER = '1';

const AboutScreen: React.FC = () => {
  const { colors } = useTheme();
  const { config } = useConfig();

  const handleOpenWebsite = () => {
    Linking.openURL('https://sasewaddle.com');
  };

  const handleOpenGitHub = () => {
    Linking.openURL('https://github.com/SASEWaddle/SASEWaddle');
  };

  const handleOpenLicense = () => {
    Linking.openURL('https://github.com/SASEWaddle/SASEWaddle/blob/main/LICENSE');
  };

  const handleOpenPrivacyPolicy = () => {
    Linking.openURL('https://sasewaddle.com/privacy');
  };

  const handleOpenTerms = () => {
    Linking.openURL('https://sasewaddle.com/terms');
  };

  const handleSendFeedback = () => {
    const subject = `SASEWaddle Mobile App Feedback (v${APP_VERSION})`;
    const body = `Please share your feedback about the SASEWaddle mobile app:\n\n`;
    Linking.openURL(`mailto:feedback@sasewaddle.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
  };

  const styles = createStyles(colors);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* App Header */}
        <View style={styles.header}>
          <View style={styles.logoContainer}>
            <View style={styles.logoIcon}>
              <Icon name="vpn-key" size={64} color={colors.primary} />
            </View>
          </View>
          
          <Text style={styles.appName}>SASEWaddle</Text>
          <Text style={styles.appTagline}>Open Source SASE Solution</Text>
          <Text style={styles.appVersion}>Version {APP_VERSION} (Build {BUILD_NUMBER})</Text>
        </View>

        {/* Quick Info */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>About</Text>
          <Text style={styles.description}>
            SASEWaddle is an Open Source Secure Access Service Edge (SASE) solution implementing 
            Zero Trust Network Architecture (ZTNA) principles. This mobile client provides secure 
            VPN connectivity with the same functionality as our desktop clients.
          </Text>
        </View>

        {/* Features */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Key Features</Text>
          
          <View style={styles.featureItem}>
            <Icon name="security" size={24} color={colors.primary} />
            <Text style={styles.featureText}>WireGuard VPN Protocol</Text>
          </View>
          
          <View style={styles.featureItem}>
            <Icon name="sync" size={24} color={colors.primary} />
            <Text style={styles.featureText}>Automatic Configuration Updates</Text>
          </View>
          
          <View style={styles.featureItem}>
            <Icon name="analytics" size={24} color={colors.primary} />
            <Text style={styles.featureText}>Real-time Statistics</Text>
          </View>
          
          <View style={styles.featureItem}>
            <Icon name="admin-panel-settings" size={24} color={colors.primary} />
            <Text style={styles.featureText}>Centralized Management</Text>
          </View>
          
          <View style={styles.featureItem}>
            <Icon name="shield" size={24} color={colors.primary} />
            <Text style={styles.featureText}>Zero Trust Security</Text>
          </View>
        </View>

        {/* Current Configuration */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Current Configuration</Text>
          
          <View style={styles.configRow}>
            <Text style={styles.configLabel}>Manager URL:</Text>
            <Text style={styles.configValue} numberOfLines={1} ellipsizeMode="middle">
              {config.managerURL || 'Not configured'}
            </Text>
          </View>
          
          <View style={styles.configRow}>
            <Text style={styles.configLabel}>Client ID:</Text>
            <Text style={styles.configValue} numberOfLines={1} ellipsizeMode="middle">
              {config.clientID || 'Not configured'}
            </Text>
          </View>
          
          <View style={styles.configRow}>
            <Text style={styles.configLabel}>Server:</Text>
            <Text style={styles.configValue}>
              {config.serverName || 'Not configured'}
            </Text>
          </View>
          
          <View style={styles.configRow}>
            <Text style={styles.configLabel}>Configuration Version:</Text>
            <Text style={styles.configValue}>
              {config.version || 'Unknown'}
            </Text>
          </View>
        </View>

        {/* Links */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Links</Text>
          
          <TouchableOpacity style={styles.linkRow} onPress={handleOpenWebsite}>
            <Icon name="public" size={24} color={colors.primary} />
            <Text style={styles.linkText}>Official Website</Text>
            <Icon name="open-in-new" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.linkRow} onPress={handleOpenGitHub}>
            <Icon name="code" size={24} color={colors.primary} />
            <Text style={styles.linkText}>Source Code (GitHub)</Text>
            <Icon name="open-in-new" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.linkRow} onPress={handleOpenLicense}>
            <Icon name="gavel" size={24} color={colors.primary} />
            <Text style={styles.linkText}>Open Source License</Text>
            <Icon name="open-in-new" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.linkRow} onPress={handleSendFeedback}>
            <Icon name="feedback" size={24} color={colors.primary} />
            <Text style={styles.linkText}>Send Feedback</Text>
            <Icon name="mail" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>

        {/* Legal */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Legal</Text>
          
          <TouchableOpacity style={styles.linkRow} onPress={handleOpenPrivacyPolicy}>
            <Icon name="privacy-tip" size={24} color={colors.primary} />
            <Text style={styles.linkText}>Privacy Policy</Text>
            <Icon name="open-in-new" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.linkRow} onPress={handleOpenTerms}>
            <Icon name="description" size={24} color={colors.primary} />
            <Text style={styles.linkText}>Terms of Service</Text>
            <Icon name="open-in-new" size={20} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>

        {/* Technical Information */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Technical Information</Text>
          
          <View style={styles.techRow}>
            <Text style={styles.techLabel}>Platform:</Text>
            <Text style={styles.techValue}>React Native</Text>
          </View>
          
          <View style={styles.techRow}>
            <Text style={styles.techLabel}>VPN Protocol:</Text>
            <Text style={styles.techValue}>WireGuard</Text>
          </View>
          
          <View style={styles.techRow}>
            <Text style={styles.techLabel}>Architecture:</Text>
            <Text style={styles.techValue}>Zero Trust Network Access (ZTNA)</Text>
          </View>
          
          <View style={styles.techRow}>
            <Text style={styles.techLabel}>Security Framework:</Text>
            <Text style={styles.techValue}>Secure Access Service Edge (SASE)</Text>
          </View>
        </View>

        {/* Credits */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Credits</Text>
          <Text style={styles.creditsText}>
            SASEWaddle is built with open source technologies including WireGuard, 
            React Native, and many other amazing projects. Special thanks to the 
            WireGuard team for creating such an excellent VPN protocol.
          </Text>
        </View>

        {/* Copyright */}
        <View style={styles.footer}>
          <Text style={styles.copyright}>
            © 2024 SASEWaddle Contributors
          </Text>
          <Text style={styles.copyrightSub}>
            Licensed under Open Source License
          </Text>
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
  header: {
    alignItems: 'center',
    paddingVertical: 32,
    marginBottom: 16,
  },
  logoContainer: {
    marginBottom: 16,
  },
  logoIcon: {
    width: 80,
    height: 80,
    borderRadius: 20,
    backgroundColor: colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  appName: {
    fontSize: 28,
    fontWeight: 'bold',
    color: colors.text,
    marginBottom: 8,
  },
  appTagline: {
    fontSize: 16,
    color: colors.textSecondary,
    marginBottom: 8,
    textAlign: 'center',
  },
  appVersion: {
    fontSize: 14,
    color: colors.textSecondary,
    fontFamily: 'monospace',
  },
  section: {
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
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
    marginBottom: 16,
  },
  description: {
    fontSize: 16,
    lineHeight: 24,
    color: colors.text,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  featureText: {
    fontSize: 16,
    color: colors.text,
    marginLeft: 16,
  },
  configRow: {
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
    fontWeight: '500',
    color: colors.text,
    flex: 2,
    textAlign: 'right',
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  linkText: {
    fontSize: 16,
    color: colors.text,
    marginLeft: 16,
    flex: 1,
  },
  techRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  techLabel: {
    fontSize: 14,
    color: colors.textSecondary,
    flex: 1,
  },
  techValue: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.text,
    flex: 2,
    textAlign: 'right',
  },
  creditsText: {
    fontSize: 14,
    lineHeight: 20,
    color: colors.textSecondary,
  },
  footer: {
    alignItems: 'center',
    paddingVertical: 32,
    marginTop: 16,
  },
  copyright: {
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: 4,
  },
  copyrightSub: {
    fontSize: 12,
    color: colors.textSecondary,
  },
});

export default AboutScreen;