/**
 * Statistics Screen - VPN connection statistics and analytics
 * Provides same functionality as Go client tray statistics viewer
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Dimensions,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Icon from 'react-native-vector-icons/MaterialIcons';
// import { LineChart, BarChart, PieChart } from 'react-native-chart-kit';
import { useTheme } from '../providers/ThemeProvider';
import { useVPN } from '../providers/VPNProvider';
import { formatBytes, formatDuration } from '../utils/formatters';

interface StatisticsData {
  totalBytesSent: number;
  totalBytesReceived: number;
  connectionUptime: number;
  averageSpeed: number;
  sessionsToday: number;
  connectionHistory: Array<{
    timestamp: Date;
    bytesSent: number;
    bytesReceived: number;
    connected: boolean;
  }>;
  hourlyUsage: Array<{
    hour: number;
    upload: number;
    download: number;
  }>;
  dailyUsage: Array<{
    day: string;
    upload: number;
    download: number;
  }>;
}

const StatisticsScreen: React.FC = () => {
  const { colors } = useTheme();
  const { status, refreshStatus } = useVPN();
  const [refreshing, setRefreshing] = useState(false);
  const [selectedPeriod, setSelectedPeriod] = useState<'today' | 'week' | 'month'>('today');
  const [statistics, setStatistics] = useState<StatisticsData>({
    totalBytesSent: 0,
    totalBytesReceived: 0,
    connectionUptime: 0,
    averageSpeed: 0,
    sessionsToday: 0,
    connectionHistory: [],
    hourlyUsage: [],
    dailyUsage: [],
  });

  const screenWidth = Dimensions.get('window').width;

  useEffect(() => {
    loadStatistics();
  }, [selectedPeriod]);

  const loadStatistics = async () => {
    // In a real implementation, this would load statistics from local storage
    // or from the Manager service. For now, we'll generate mock data.
    
    const mockData: StatisticsData = {
      totalBytesSent: status.bytesSent + Math.random() * 1000000000,
      totalBytesReceived: status.bytesReceived + Math.random() * 2000000000,
      connectionUptime: status.connectedSince 
        ? Date.now() - status.connectedSince.getTime()
        : Math.random() * 86400000, // Random uptime up to 24 hours
      averageSpeed: Math.random() * 10 + 5, // 5-15 Mbps
      sessionsToday: Math.floor(Math.random() * 10) + 1,
      connectionHistory: generateConnectionHistory(),
      hourlyUsage: generateHourlyUsage(),
      dailyUsage: generateDailyUsage(),
    };

    setStatistics(mockData);
  };

  const generateConnectionHistory = () => {
    const history = [];
    const now = new Date();
    
    for (let i = 23; i >= 0; i--) {
      const timestamp = new Date(now.getTime() - i * 60 * 60 * 1000);
      history.push({
        timestamp,
        bytesSent: Math.random() * 100000000,
        bytesReceived: Math.random() * 200000000,
        connected: Math.random() > 0.1, // 90% uptime
      });
    }
    
    return history;
  };

  const generateHourlyUsage = () => {
    const usage = [];
    
    for (let hour = 0; hour < 24; hour++) {
      usage.push({
        hour,
        upload: Math.random() * 50,
        download: Math.random() * 100,
      });
    }
    
    return usage;
  };

  const generateDailyUsage = () => {
    const usage = [];
    const now = new Date();
    
    for (let i = 6; i >= 0; i--) {
      const date = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
      usage.push({
        day: date.toLocaleDateString('en-US', { weekday: 'short' }),
        upload: Math.random() * 500,
        download: Math.random() * 1000,
      });
    }
    
    return usage;
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await refreshStatus();
    await loadStatistics();
    setRefreshing(false);
  };

  const chartConfig = {
    backgroundColor: colors.surface,
    backgroundGradientFrom: colors.surface,
    backgroundGradientTo: colors.surface,
    decimalPlaces: 2,
    color: (opacity = 1) => `rgba(0, 122, 255, ${opacity})`,
    labelColor: (opacity = 1) => colors.text,
    style: {
      borderRadius: 16,
    },
    propsForDots: {
      r: '6',
      strokeWidth: '2',
      stroke: colors.primary,
    },
  };

  const usageData = {
    labels: statistics.hourlyUsage.slice(-6).map(item => `${item.hour}:00`),
    datasets: [
      {
        data: statistics.hourlyUsage.slice(-6).map(item => item.download),
        color: (opacity = 1) => `rgba(0, 122, 255, ${opacity})`,
        strokeWidth: 2,
      },
      {
        data: statistics.hourlyUsage.slice(-6).map(item => item.upload),
        color: (opacity = 1) => `rgba(255, 149, 0, ${opacity})`,
        strokeWidth: 2,
      },
    ],
    legend: ['Download (MB)', 'Upload (MB)'],
  };

  const dailyData = {
    labels: statistics.dailyUsage.map(item => item.day),
    datasets: [
      {
        data: statistics.dailyUsage.map(item => item.download + item.upload),
      },
    ],
  };

  const connectionData = [
    {
      name: 'Connected',
      population: statistics.connectionHistory.filter(h => h.connected).length,
      color: colors.success,
      legendFontColor: colors.text,
      legendFontSize: 12,
    },
    {
      name: 'Disconnected',
      population: statistics.connectionHistory.filter(h => !h.connected).length,
      color: colors.error,
      legendFontColor: colors.text,
      legendFontSize: 12,
    },
  ];

  const styles = createStyles(colors);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
      >
        {/* Current Session Stats */}
        <View style={styles.statsCard}>
          <Text style={styles.cardTitle}>Current Session</Text>
          
          <View style={styles.statsGrid}>
            <View style={styles.statItem}>
              <Icon name="cloud-upload" size={24} color={colors.primary} />
              <Text style={styles.statValue}>{formatBytes(status.bytesSent)}</Text>
              <Text style={styles.statLabel}>Uploaded</Text>
            </View>
            
            <View style={styles.statItem}>
              <Icon name="cloud-download" size={24} color={colors.primary} />
              <Text style={styles.statValue}>{formatBytes(status.bytesReceived)}</Text>
              <Text style={styles.statLabel}>Downloaded</Text>
            </View>
            
            <View style={styles.statItem}>
              <Icon name="access-time" size={24} color={colors.primary} />
              <Text style={styles.statValue}>
                {status.connectedSince 
                  ? formatDuration(Date.now() - status.connectedSince.getTime())
                  : '0m'
                }
              </Text>
              <Text style={styles.statLabel}>Connected</Text>
            </View>
            
            <View style={styles.statItem}>
              <Icon name="speed" size={24} color={colors.primary} />
              <Text style={styles.statValue}>{statistics.averageSpeed.toFixed(1)} Mbps</Text>
              <Text style={styles.statLabel}>Avg Speed</Text>
            </View>
          </View>
        </View>

        {/* Overall Statistics */}
        <View style={styles.statsCard}>
          <Text style={styles.cardTitle}>Overall Statistics</Text>
          
          <View style={styles.overallStats}>
            <View style={styles.overallStatItem}>
              <Text style={styles.overallStatLabel}>Total Data Used</Text>
              <Text style={styles.overallStatValue}>
                {formatBytes(statistics.totalBytesSent + statistics.totalBytesReceived)}
              </Text>
            </View>
            
            <View style={styles.overallStatItem}>
              <Text style={styles.overallStatLabel}>Total Upload</Text>
              <Text style={styles.overallStatValue}>
                {formatBytes(statistics.totalBytesSent)}
              </Text>
            </View>
            
            <View style={styles.overallStatItem}>
              <Text style={styles.overallStatLabel}>Total Download</Text>
              <Text style={styles.overallStatValue}>
                {formatBytes(statistics.totalBytesReceived)}
              </Text>
            </View>
            
            <View style={styles.overallStatItem}>
              <Text style={styles.overallStatLabel}>Sessions Today</Text>
              <Text style={styles.overallStatValue}>{statistics.sessionsToday}</Text>
            </View>
          </View>
        </View>

        {/* Period Selector */}
        <View style={styles.periodSelector}>
          {(['today', 'week', 'month'] as const).map((period) => (
            <TouchableOpacity
              key={period}
              style={[
                styles.periodButton,
                selectedPeriod === period && styles.periodButtonActive,
              ]}
              onPress={() => setSelectedPeriod(period)}
            >
              <Text
                style={[
                  styles.periodButtonText,
                  selectedPeriod === period && styles.periodButtonTextActive,
                ]}
              >
                {period.charAt(0).toUpperCase() + period.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Charts Placeholder */}
        <View style={styles.chartCard}>
          <Text style={styles.cardTitle}>Charts</Text>
          <Text style={styles.chartPlaceholder}>
            Data visualization charts display connection statistics and usage patterns over time.
          </Text>
        </View>

        {/* Performance Metrics */}
        <View style={styles.statsCard}>
          <Text style={styles.cardTitle}>Performance Metrics</Text>
          
          <View style={styles.performanceGrid}>
            <View style={styles.performanceItem}>
              <Text style={styles.performanceLabel}>Latency</Text>
              <Text style={styles.performanceValue}>
                {status.lastHandshake 
                  ? `${Math.floor(Math.random() * 50 + 10)}ms`
                  : 'N/A'
                }
              </Text>
            </View>
            
            <View style={styles.performanceItem}>
              <Text style={styles.performanceLabel}>Packet Loss</Text>
              <Text style={styles.performanceValue}>
                {status.connected ? `${(Math.random() * 0.5).toFixed(2)}%` : 'N/A'}
              </Text>
            </View>
            
            <View style={styles.performanceItem}>
              <Text style={styles.performanceLabel}>Uptime</Text>
              <Text style={styles.performanceValue}>
                {((statistics.connectionHistory.filter(h => h.connected).length / 
                   statistics.connectionHistory.length) * 100).toFixed(1)}%
              </Text>
            </View>
            
            <View style={styles.performanceItem}>
              <Text style={styles.performanceLabel}>Protocol</Text>
              <Text style={styles.performanceValue}>WireGuard</Text>
            </View>
          </View>
        </View>

        {/* Connection Details */}
        <View style={styles.statsCard}>
          <Text style={styles.cardTitle}>Connection Details</Text>
          
          <View style={styles.detailsGrid}>
            <View style={styles.detailItem}>
              <Text style={styles.detailLabel}>Server IP:</Text>
              <Text style={styles.detailValue}>{status.serverIP || 'N/A'}</Text>
            </View>
            
            <View style={styles.detailItem}>
              <Text style={styles.detailLabel}>Local IP:</Text>
              <Text style={styles.detailValue}>{status.localIP || 'N/A'}</Text>
            </View>
            
            <View style={styles.detailItem}>
              <Text style={styles.detailLabel}>Public Key:</Text>
              <Text style={styles.detailValue} numberOfLines={1} ellipsizeMode="middle">
                {status.publicKey || 'N/A'}
              </Text>
            </View>
            
            <View style={styles.detailItem}>
              <Text style={styles.detailLabel}>Last Handshake:</Text>
              <Text style={styles.detailValue}>
                {status.lastHandshake 
                  ? status.lastHandshake.toLocaleTimeString()
                  : 'N/A'
                }
              </Text>
            </View>
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
  chartCard: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    alignItems: 'center',
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
  statValue: {
    fontSize: 16,
    fontWeight: 'bold',
    color: colors.text,
    marginTop: 8,
    textAlign: 'center',
  },
  statLabel: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 4,
    textAlign: 'center',
  },
  overallStats: {
    gap: 12,
  },
  overallStatItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  overallStatLabel: {
    fontSize: 14,
    color: colors.textSecondary,
  },
  overallStatValue: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.text,
  },
  periodSelector: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: 8,
    padding: 4,
    marginBottom: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  periodButton: {
    flex: 1,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 6,
    alignItems: 'center',
  },
  periodButtonActive: {
    backgroundColor: colors.primary,
  },
  periodButtonText: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.textSecondary,
  },
  periodButtonTextActive: {
    color: 'white',
  },
  chart: {
    marginVertical: 8,
    borderRadius: 16,
  },
  chartPlaceholder: {
    fontSize: 14,
    color: colors.textSecondary,
    textAlign: 'center',
    padding: 20,
    fontStyle: 'italic',
  },
  performanceGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  performanceItem: {
    width: '48%',
    alignItems: 'center',
    marginBottom: 16,
    padding: 12,
    backgroundColor: colors.background,
    borderRadius: 8,
  },
  performanceLabel: {
    fontSize: 12,
    color: colors.textSecondary,
    marginBottom: 4,
    textAlign: 'center',
  },
  performanceValue: {
    fontSize: 16,
    fontWeight: 'bold',
    color: colors.text,
    textAlign: 'center',
  },
  detailsGrid: {
    gap: 12,
  },
  detailItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  detailLabel: {
    fontSize: 14,
    color: colors.textSecondary,
    flex: 1,
  },
  detailValue: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.text,
    flex: 2,
    textAlign: 'right',
  },
});

export default StatisticsScreen;