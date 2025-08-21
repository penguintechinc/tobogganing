# 📱 SASEWaddle Mobile Development Guide

## 🎯 Overview

SASEWaddle includes a React Native mobile application for Android and iOS (planned) that provides secure VPN access with an intuitive mobile interface. This guide covers setup, development, building, and deployment of the mobile client.

## 📋 Table of Contents

- [🚀 Quick Setup](#-quick-setup)
- [🔧 Development Environment](#-development-environment)
- [📱 Mobile App Architecture](#-mobile-app-architecture)
- [🏗️ Building & Deployment](#️-building--deployment)
- [🧪 Testing](#-testing)
- [📊 Features](#-features)
- [🔧 Troubleshooting](#-troubleshooting)

---

## 🚀 Quick Setup

### One-Command Setup

```bash
# Install Android Studio, SDK, and build mobile app
./scripts/setup-android-studio.sh

# Deploy mobile app to device/emulator
./scripts/deploy-mobile.sh
```

### Manual Setup

```bash
# 1. Install Node.js dependencies
cd clients/mobile
npm install

# 2. Set up Android development environment
./scripts/setup-android-studio.sh

# 3. Build and test
npm run android
```

---

## 🔧 Development Environment

### Prerequisites

- **Node.js 18+**: JavaScript runtime
- **Android Studio**: For Android development
- **Android SDK API 34**: Target Android platform
- **Java 17**: Required for Android builds
- **Chrome/Chromium**: For screenshot generation

### Automated Setup

The setup script handles all prerequisites:

```bash
# Complete Android development setup
./scripts/setup-android-studio.sh

# Available options:
./scripts/setup-android-studio.sh --help
./scripts/setup-android-studio.sh --verify          # Verify installation
./scripts/setup-android-studio.sh --build-app       # Build app only
./scripts/setup-android-studio.sh --start-emulator  # Start emulator
./scripts/setup-android-studio.sh --create-avd      # Create virtual device
```

### Manual Environment Setup

If you prefer manual setup:

```bash
# Install Android Studio
# Download from: https://developer.android.com/studio

# Set environment variables
export ANDROID_HOME=/opt/android-sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

# Install React Native CLI
npm install -g @react-native-community/cli

# Install mobile dependencies
cd clients/mobile
npm install
```

### Verify Environment

```bash
# Check React Native environment
npx react-native doctor

# Expected output:
# ✓ Node.js - Required to execute JavaScript code
# ✓ npm - Required to install NPM dependencies
# ✓ Android Studio - Required for building and installing your app on Android
# ✓ Android SDK - Required for building and installing your app on Android
# ✓ ANDROID_HOME - Environment variable that points to your Android SDK installation
```

---

## 📱 Mobile App Architecture

### Technology Stack

- **Framework**: React Native 0.72.6
- **Language**: TypeScript
- **Navigation**: React Navigation v6
- **State Management**: React Context + Hooks
- **Storage**: React Native AsyncStorage + Keychain
- **Networking**: Axios
- **UI Components**: Custom components with React Native
- **Platform**: Android (iOS planned for v1.1+)

### Project Structure

```
clients/mobile/
├── android/                     # Android-specific code
│   ├── app/
│   │   ├── build.gradle         # Android build configuration
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       ├── java/com/sasewaddle/mobile/
│   │       └── res/             # Android resources
│   ├── build.gradle             # Root build configuration
│   ├── gradlew                  # Gradle wrapper
│   └── settings.gradle          # Gradle settings
├── ios/                         # iOS-specific code (planned)
├── src/                         # React Native source code
│   ├── App.tsx                  # Main app component
│   ├── config/
│   │   └── build.ts             # Build configuration
│   ├── constants/
│   │   └── Colors.ts            # App color scheme
│   ├── providers/               # React Context providers
│   │   ├── ConfigProvider.tsx   # Configuration management
│   │   ├── ThemeProvider.tsx    # Theme management
│   │   └── VPNProvider.tsx      # VPN state management
│   ├── screens/                 # App screens
│   │   ├── AboutScreen.tsx      # About/info screen
│   │   ├── ConfigurationScreen.tsx # VPN configuration
│   │   ├── ConnectionScreen.tsx # Main connection screen
│   │   ├── SettingsScreen.tsx   # App settings
│   │   └── StatisticsScreen.tsx # Connection statistics
│   ├── types/                   # TypeScript type definitions
│   ├── utils/                   # Utility functions
│   │   └── formatters.ts        # Data formatting utilities
│   └── assets/                  # Images, fonts, etc.
├── package.json                 # Node.js dependencies
├── metro.config.js              # Metro bundler configuration
├── babel.config.js              # Babel configuration
├── tsconfig.json                # TypeScript configuration
└── app.json                     # React Native app configuration
```

### Key Components

#### 🔌 VPN Connection Management
- **VPNProvider**: Manages VPN connection state
- **ConnectionScreen**: Main interface for connection control
- **WireGuard Integration**: Native WireGuard client integration

#### ⚙️ Configuration Management
- **ConfigProvider**: Handles app configuration and server settings
- **ConfigurationScreen**: User interface for VPN configuration
- **Secure Storage**: Encrypted storage for sensitive data

#### 📊 Monitoring & Statistics
- **StatisticsScreen**: Real-time connection statistics
- **Performance Metrics**: Data usage, connection quality
- **Health Monitoring**: Connection status and diagnostics

#### 🔒 Security Features
- **Certificate Management**: X.509 certificate handling
- **Biometric Authentication**: Fingerprint/face unlock
- **Secure Keychain**: Encrypted credential storage

---

## 🏗️ Building & Deployment

### Quick Build & Deploy

```bash
# Build and deploy in one command
./scripts/deploy-mobile.sh

# Output:
# ✅ APK built successfully!
# 📱 APK ready for installation
# To install: adb install -r path/to/app-debug.apk
```

### Manual Build Process

```bash
# Navigate to mobile project
cd clients/mobile

# Install dependencies
npm install

# Build Android APK
cd android
./gradlew assembleDebug

# APK location: android/app/build/outputs/apk/debug/app-debug.apk
```

### Build Configurations

#### Development Build
```bash
# Build for development
BUILD_TYPE=development ./scripts/deploy-mobile.sh

# Features:
# - Debug mode enabled
# - Development API endpoints
# - Debugging tools available
```

#### Staging Build
```bash
# Build for staging
BUILD_TYPE=staging ./scripts/deploy-mobile.sh

# Features:
# - Staging API endpoints
# - Performance optimizations
# - Limited debugging
```

#### Production Build
```bash
# Build for production
BUILD_TYPE=production npm run build:android

# Features:
# - Production API endpoints
# - Full optimizations
# - No debugging tools
# - Code obfuscation
```

### Installation & Deployment

#### Install to Connected Device
```bash
# Install APK to connected Android device
adb install -r clients/mobile/android/app/build/outputs/apk/debug/app-debug.apk

# Check connected devices
adb devices

# View app logs
adb logcat | grep SASEWaddle
```

#### Install to Emulator
```bash
# Start Android emulator
./scripts/setup-android-studio.sh --start-emulator

# Wait for emulator to start
adb wait-for-device

# Install app
./scripts/deploy-mobile.sh
```

### Automated CI/CD

The GitHub Actions workflow automatically builds mobile apps:

```yaml
# .github/workflows/mobile.yml
- name: Build Android APK
  run: |
    cd clients/mobile/android
    ./gradlew assembleDebug
    
- name: Upload APK Artifact
  uses: actions/upload-artifact@v3
  with:
    name: android-apk
    path: clients/mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 🧪 Testing

### Unit Testing

```bash
# Run unit tests
cd clients/mobile
npm test

# Run with coverage
npm run test:coverage

# Watch mode for development
npm run test:watch
```

### Integration Testing

```bash
# Test React Native environment
npx react-native doctor

# Test Android build
./scripts/deploy-mobile.sh

# Test emulator deployment
./scripts/setup-android-studio.sh --start-emulator
adb wait-for-device
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

### Manual Testing Checklist

- [ ] **Connection Flow**
  - [ ] Initial app setup with API key
  - [ ] VPN connection establishment
  - [ ] Connection status updates
  - [ ] Disconnect functionality

- [ ] **Configuration**
  - [ ] Server configuration
  - [ ] Auto-connect settings
  - [ ] Biometric authentication
  - [ ] Theme switching

- [ ] **Statistics & Monitoring**
  - [ ] Real-time data usage
  - [ ] Connection quality metrics
  - [ ] Historical statistics
  - [ ] Export functionality

- [ ] **Security**
  - [ ] Certificate validation
  - [ ] Secure credential storage
  - [ ] Biometric unlock
  - [ ] Auto-lock functionality

---

## 📊 Features

### Core Functionality

#### 🔌 VPN Connection
- **WireGuard Integration**: Native WireGuard protocol support
- **Auto-Connect**: Automatic connection on app launch
- **Quick Connect**: One-tap connection establishment
- **Connection Profiles**: Multiple server configurations
- **Offline Support**: Graceful handling of network changes

#### ⚙️ Configuration Management
- **Server Settings**: Manager URL and authentication
- **Connection Preferences**: Auto-connect, timeout settings
- **Security Options**: Biometric authentication, auto-lock
- **Network Settings**: DNS, proxy configuration
- **Backup/Restore**: Configuration backup and restore

#### 📊 Monitoring & Statistics
- **Real-time Metrics**: Data usage, connection speed
- **Historical Data**: Usage patterns over time
- **Performance Monitoring**: Latency, packet loss
- **Data Export**: Export statistics for analysis
- **Alerts**: Connection status notifications

#### 🔒 Security Features
- **Dual Authentication**: Certificate + JWT tokens
- **Biometric Security**: Fingerprint/face unlock
- **Secure Storage**: Encrypted credential storage
- **Certificate Management**: Automatic certificate updates
- **Security Alerts**: Threat detection notifications

### User Interface

#### 🎨 Modern Design
- **Material Design**: Android-native UI patterns
- **Dark/Light Themes**: Automatic theme switching
- **Responsive Layout**: Optimized for all screen sizes
- **Smooth Animations**: Fluid transitions and interactions
- **Accessibility**: Screen reader and accessibility support

#### 📱 Navigation
- **Bottom Tabs**: Main navigation structure
- **Stack Navigation**: Hierarchical screen flow
- **Drawer Navigation**: Settings and advanced options
- **Deep Linking**: URL-based navigation support
- **Back Button**: Native Android back button support

### Advanced Features

#### 🛡️ Enterprise Security
- **MDM Integration**: Mobile Device Management support
- **Compliance Reporting**: Security compliance status
- **Remote Configuration**: Centralized configuration management
- **Audit Logging**: Detailed security event logging
- **Zero-Touch Deployment**: Automated configuration

#### 📈 Analytics & Insights
- **Usage Analytics**: App usage patterns
- **Performance Metrics**: App performance monitoring
- **Crash Reporting**: Automatic crash reporting
- **User Feedback**: In-app feedback collection
- **A/B Testing**: Feature testing framework

---

## 🔧 Troubleshooting

### Common Issues

#### Build Failures

**Gradle Build Errors**
```bash
# Clear Gradle cache
cd clients/mobile/android
./gradlew clean

# Clear React Native cache
cd clients/mobile
npx react-native clean

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

**Metro Bundler Issues**
```bash
# Reset Metro cache
npx react-native clean
npx react-native start --reset-cache

# Clear watchman
watchman watch-del-all
```

**Android SDK Issues**
```bash
# Verify Android environment
./scripts/setup-android-studio.sh --verify

# Reinstall Android SDK components
./scripts/setup-android-studio.sh --create-avd
```

#### Runtime Issues

**VPN Connection Failures**
```bash
# Check device logs
adb logcat | grep SASEWaddle

# Verify network connectivity
adb shell ping manager.example.com

# Check certificate validity
adb shell cat /data/data/com.sasewaddle.mobile/files/cert.pem
```

**Performance Issues**
```bash
# Enable performance monitoring
adb shell setprop debug.choreographer.skipwarning 1

# Monitor memory usage
adb shell dumpsys meminfo com.sasewaddle.mobile

# Check CPU usage
adb shell top | grep sasewaddle
```

### Debug Tools

#### React Native Debugger
```bash
# Enable debugging
npx react-native run-android --variant=debug

# Open Chrome DevTools
# Navigate to: chrome://inspect
```

#### Android Studio Debugging
```bash
# Open project in Android Studio
~/open-sasewaddle-mobile.sh

# Use Android Studio debugger
# Set breakpoints in Java/Kotlin code
# Use Logcat for runtime logging
```

#### Native Logging
```bash
# View React Native logs
npx react-native log-android

# View native Android logs
adb logcat *:E | grep SASEWaddle

# Export logs for analysis
adb logcat -d > sasewaddle-logs.txt
```

### Performance Optimization

#### Build Optimization
```bash
# Enable Proguard for release builds
# Edit android/app/build.gradle:
# minifyEnabled true

# Optimize bundle size
npx react-native bundle --dev false --platform android

# Generate APK with optimizations
cd android && ./gradlew assembleRelease
```

#### Runtime Optimization
```bash
# Enable Hermes engine
# Edit android/app/build.gradle:
# enableHermes: true

# Optimize images
# Use WebP format for images
# Implement lazy loading
```

### Getting Help

- **Documentation**: [/docs/MOBILE_DEVELOPMENT.md](MOBILE_DEVELOPMENT.md)
- **Build Scripts**: [/scripts/setup-android-studio.sh](../scripts/setup-android-studio.sh)
- **Issue Tracker**: [GitHub Issues](https://github.com/your-org/sasewaddle/issues)
- **React Native Docs**: [https://reactnative.dev/docs/getting-started](https://reactnative.dev/docs/getting-started)
- **Android Developer Docs**: [https://developer.android.com/](https://developer.android.com/)

This comprehensive mobile development guide provides everything needed to develop, build, test, and deploy the SASEWaddle mobile application across different environments and use cases.