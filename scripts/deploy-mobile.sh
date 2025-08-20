#!/bin/bash

# SASEWaddle Mobile App Deployment Script
# Quick deployment script for building and installing the mobile app

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
MOBILE_DIR="$ROOT_DIR/clients/mobile"
ANDROID_DIR="$MOBILE_DIR/android"
APK_PATH="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"

echo "========================================"
echo "  SASEWaddle Mobile App Deployment"
echo "========================================"
echo

# Check if mobile project exists
if [ ! -d "$MOBILE_DIR" ]; then
    log_error "SASEWaddle mobile project not found at $MOBILE_DIR"
    exit 1
fi

# Set up Android environment
export ANDROID_HOME=/opt/android-sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator

log_info "Environment configured for Android development"

# Build the app
log_info "Building SASEWaddle mobile app..."
cd "$ANDROID_DIR" || exit 1

if ./gradlew assembleDebug --no-daemon --quiet; then
    if [ -f "$APK_PATH" ]; then
        log_success "✅ APK built successfully!"
        log_info "APK Location: $APK_PATH"
        log_info "APK Size: $(du -h "$APK_PATH" | cut -f1)"
    else
        log_error "APK file not found after build"
        exit 1
    fi
else
    log_error "Build failed"
    exit 1
fi

# Check for connected devices
log_info "Checking for connected Android devices..."
device_count=$(adb devices 2>/dev/null | grep -E "device$|emulator" | wc -l)

if [ "$device_count" -eq 0 ]; then
    log_warning "No Android devices or emulators connected"
    echo
    log_info "To install manually:"
    echo "  1. Connect an Android device or start an emulator"
    echo "  2. Run: adb install -r \"$APK_PATH\""
    echo
    log_info "To start an emulator:"
    echo "  • $SCRIPT_DIR/setup-android-studio.sh --start-emulator"
    echo
else
    log_success "Found $device_count connected device(s)"
    adb devices 2>/dev/null | grep -E "device$|emulator" | while read -r line; do
        device=$(echo "$line" | awk '{print $1}')
        echo "  • $device"
    done
    echo
    
    # Install to connected devices
    log_info "Installing app to connected devices..."
    
    if adb install -r "$APK_PATH" 2>/dev/null; then
        log_success "✅ App installed successfully!"
        echo
        log_success "🚀 SASEWaddle mobile app deployment complete!"
        log_info "Launch the app on your device to test the SASE functionality"
    else
        log_warning "⚠️  App installation failed"
        log_info "Try manually: adb install -r \"$APK_PATH\""
    fi
fi

echo
log_info "Deployment Summary:"
echo "  • APK: $(basename "$APK_PATH")"
echo "  • Size: $(du -h "$APK_PATH" | cut -f1)"
echo "  • Location: $APK_PATH"
echo "  • Package: com.sasewaddle.mobile"
echo