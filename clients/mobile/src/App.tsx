/**
 * SASEWaddle Mobile Client
 * React Native app for WireGuard VPN management with same functionality as Go client tray
 */

import React, { useEffect, useState } from 'react';
import {
  StatusBar,
  StyleSheet,
  useColorScheme,
} from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import Toast from 'react-native-toast-message';
import Icon from 'react-native-vector-icons/MaterialIcons';

import { VPNProvider } from './providers/VPNProvider';
import { ConfigProvider } from './providers/ConfigProvider';
import { ThemeProvider } from './providers/ThemeProvider';
import { Colors } from './constants/Colors';

// Screens
import ConnectionScreen from './screens/ConnectionScreen';
import StatisticsScreen from './screens/StatisticsScreen';
import ConfigurationScreen from './screens/ConfigurationScreen';
import SettingsScreen from './screens/SettingsScreen';
import AboutScreen from './screens/AboutScreen';

const Tab = createBottomTabNavigator();

function App(): JSX.Element {
  const isDarkMode = useColorScheme() === 'dark';
  
  const backgroundStyle = {
    backgroundColor: isDarkMode ? Colors.darker : Colors.lighter,
  };

  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <VPNProvider>
          <ConfigProvider>
            <NavigationContainer>
              <StatusBar
                barStyle={isDarkMode ? 'light-content' : 'dark-content'}
                backgroundColor={backgroundStyle.backgroundColor}
              />
              
              <Tab.Navigator
                initialRouteName="Connection"
                screenOptions={({ route }) => ({
                  tabBarIcon: ({ focused, color, size }) => {
                    let iconName: string;

                    switch (route.name) {
                      case 'Connection':
                        iconName = 'vpn-key';
                        break;
                      case 'Statistics':
                        iconName = 'analytics';
                        break;
                      case 'Configuration':
                        iconName = 'settings';
                        break;
                      case 'Settings':
                        iconName = 'tune';
                        break;
                      case 'About':
                        iconName = 'info';
                        break;
                      default:
                        iconName = 'help';
                    }

                    return <Icon name={iconName} size={size} color={color} />;
                  },
                  tabBarActiveTintColor: '#007AFF',
                  tabBarInactiveTintColor: 'gray',
                  tabBarStyle: {
                    backgroundColor: isDarkMode ? Colors.dark : Colors.light,
                    borderTopColor: isDarkMode ? Colors.border : Colors.lightBorder,
                  },
                  headerStyle: {
                    backgroundColor: isDarkMode ? Colors.dark : Colors.light,
                  },
                  headerTintColor: isDarkMode ? Colors.light : Colors.dark,
                })}
              >
                <Tab.Screen 
                  name="Connection" 
                  component={ConnectionScreen}
                  options={{ title: 'VPN Connection' }}
                />
                <Tab.Screen 
                  name="Statistics" 
                  component={StatisticsScreen}
                  options={{ title: 'Statistics' }}
                />
                <Tab.Screen 
                  name="Configuration" 
                  component={ConfigurationScreen}
                  options={{ title: 'Configuration' }}
                />
                <Tab.Screen 
                  name="Settings" 
                  component={SettingsScreen}
                  options={{ title: 'Settings' }}
                />
                <Tab.Screen 
                  name="About" 
                  component={AboutScreen}
                  options={{ title: 'About' }}
                />
              </Tab.Navigator>
            </NavigationContainer>
            
            <Toast />
          </ConfigProvider>
        </VPNProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  // Add any global styles here
});

export default App;