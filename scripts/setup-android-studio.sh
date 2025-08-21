#!/bin/bash

# Android Studio Setup Script for SASEWaddle Development
# This script installs Android Studio, Android SDK, and configures the environment for React Native development

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
ANDROID_STUDIO_VERSION="2024.1.2.12"
ANDROID_SDK_TOOLS_VERSION="11076708"
INSTALL_DIR="/opt"
ANDROID_HOME="/opt/android-sdk"
JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"

echo "=============================================="
echo "  Android Studio Setup for SASEWaddle"
echo "=============================================="
echo

log_info "This script will install:"
echo "  • Android Studio ${ANDROID_STUDIO_VERSION}"
echo "  • Android SDK command line tools"
echo "  • Android SDK components for React Native"
echo "  • Set up environment variables"
echo

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    log_error "Please don't run this script as root. It will use sudo when needed."
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check for required commands
    local missing_deps=()
    
    if ! command_exists "wget"; then
        missing_deps+=("wget")
    fi
    
    if ! command_exists "unzip"; then
        missing_deps+=("unzip")
    fi
    
    if ! command_exists "java"; then
        missing_deps+=("openjdk-17-jdk")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        log_info "Installing missing dependencies: ${missing_deps[*]}"
        sudo apt-get update -qq
        sudo apt-get install -y "${missing_deps[@]}"
    fi
    
    # Verify Java installation
    if ! java -version 2>&1 | grep -q "openjdk.*17"; then
        log_warning "Java 17 not found. Installing OpenJDK 17..."
        sudo apt-get install -y openjdk-17-jdk
    fi
    
    log_success "Prerequisites check completed"
}

# Download Android Studio
download_android_studio() {
    local studio_url="https://redirector.gvt1.com/edgedl/android/studio/ide-zips/${ANDROID_STUDIO_VERSION}/android-studio-${ANDROID_STUDIO_VERSION}-linux.tar.gz"
    local studio_file="/tmp/android-studio-${ANDROID_STUDIO_VERSION}-linux.tar.gz"
    
    if [ -f "$studio_file" ]; then
        log_info "Android Studio archive already exists, skipping download"
        return 0
    fi
    
    log_info "Downloading Android Studio ${ANDROID_STUDIO_VERSION}..."
    log_info "This may take a few minutes (file size: ~1.2GB)"
    
    if wget -q --show-progress --progress=bar:force:noscroll "$studio_url" -O "$studio_file"; then
        log_success "Android Studio downloaded successfully"
    else
        log_error "Failed to download Android Studio"
        return 1
    fi
}

# Install Android Studio
install_android_studio() {
    local studio_file="/tmp/android-studio-${ANDROID_STUDIO_VERSION}-linux.tar.gz"
    
    if [ -d "$INSTALL_DIR/android-studio" ]; then
        log_warning "Android Studio already installed, skipping extraction"
        return 0
    fi
    
    log_info "Installing Android Studio to $INSTALL_DIR..."
    
    sudo mkdir -p "$INSTALL_DIR"
    sudo tar -xzf "$studio_file" -C "$INSTALL_DIR"
    sudo chown -R $USER:$USER "$INSTALL_DIR/android-studio"
    
    log_success "Android Studio installed successfully"
}

# Download and install Android SDK command line tools
install_android_sdk() {
    local sdk_tools_url="https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_SDK_TOOLS_VERSION}_latest.zip"
    local sdk_tools_file="/tmp/commandlinetools-linux-latest.zip"
    
    log_info "Setting up Android SDK..."
    
    # Create SDK directory
    sudo mkdir -p "$ANDROID_HOME"
    sudo chown -R $USER:$USER "$ANDROID_HOME"
    
    # Download command line tools if not exists
    if [ ! -f "$sdk_tools_file" ]; then
        log_info "Downloading Android SDK command line tools..."
        wget -q --show-progress --progress=bar:force:noscroll "$sdk_tools_url" -O "$sdk_tools_file"
    fi
    
    # Extract command line tools
    if [ ! -d "$ANDROID_HOME/cmdline-tools" ]; then
        log_info "Extracting Android SDK command line tools..."
        unzip -q "$sdk_tools_file" -d "$ANDROID_HOME"
        
        # Move to proper directory structure
        mkdir -p "$ANDROID_HOME/cmdline-tools/latest"
        mv "$ANDROID_HOME/cmdline-tools"/* "$ANDROID_HOME/cmdline-tools/latest/" 2>/dev/null || true
        
        # Remove empty directories that might have been created
        find "$ANDROID_HOME/cmdline-tools" -maxdepth 1 -type d -empty -delete 2>/dev/null || true
    fi
    
    log_success "Android SDK command line tools installed"
}

# Install Android SDK components
install_sdk_components() {
    log_info "Installing Android SDK components for React Native development..."
    
    # Set up environment for this session
    export ANDROID_HOME="$ANDROID_HOME"
    export ANDROID_SDK_ROOT="$ANDROID_HOME"
    export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools"
    export JAVA_HOME="$JAVA_HOME"
    
    local sdkmanager="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
    
    if [ ! -f "$sdkmanager" ]; then
        log_error "SDK manager not found at $sdkmanager"
        return 1
    fi
    
    # Accept licenses
    log_info "Accepting Android SDK licenses..."
    yes | "$sdkmanager" --licenses > /dev/null 2>&1 || true
    
    # Install essential components for React Native
    log_info "Installing Android SDK platforms and tools..."
    
    local packages=(
        "platform-tools"
        "platforms;android-34"
        "platforms;android-33"
        "platforms;android-32"
        "build-tools;34.0.0"
        "build-tools;33.0.2"
        "system-images;android-34;google_apis;x86_64"
        "system-images;android-33;google_apis;x86_64"
        "emulator"
        "extras;android;m2repository"
        "extras;google;m2repository"
        "extras;google;google_play_services"
    )
    
    for package in "${packages[@]}"; do
        log_info "Installing $package..."
        "$sdkmanager" "$package" || log_warning "Failed to install $package"
    done
    
    log_success "Android SDK components installed"
}

# Set up environment variables permanently
setup_environment() {
    log_info "Setting up environment variables..."
    
    local profile_file="$HOME/.bashrc"
    local env_vars="
# Android development environment
export ANDROID_HOME=$ANDROID_HOME
export ANDROID_SDK_ROOT=\$ANDROID_HOME
export PATH=\$PATH:\$ANDROID_HOME/cmdline-tools/latest/bin:\$ANDROID_HOME/platform-tools:\$ANDROID_HOME/emulator
export JAVA_HOME=$JAVA_HOME
"
    
    # Check if Android environment is already set up
    if ! grep -q "ANDROID_HOME" "$profile_file" 2>/dev/null; then
        echo "$env_vars" >> "$profile_file"
        log_success "Environment variables added to $profile_file"
    else
        log_info "Android environment variables already configured"
    fi
    
    # Set up for current session
    export ANDROID_HOME="$ANDROID_HOME"
    export ANDROID_SDK_ROOT="$ANDROID_HOME"
    export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator"
    export JAVA_HOME="$JAVA_HOME"
}

# Create Android Virtual Device (AVD)
create_avd() {
    log_info "Creating Android Virtual Device for testing..."
    
    local avdmanager="$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager"
    local avd_name="SASEWaddle_Test_Device"
    local compact_avd="SASEWaddle_Compact"
    
    # Check if AVD already exists
    if "$avdmanager" list avd 2>/dev/null | grep -q "$avd_name"; then
        log_info "AVD '$avd_name' already exists"
        return 0
    fi
    
    # Try to create primary AVD
    log_info "Creating primary AVD '$avd_name'..."
    if echo "no" | "$avdmanager" create avd \
        -n "$avd_name" \
        -k "system-images;android-34;google_apis;x86_64" \
        -d "pixel_7" \
        --force 2>/dev/null; then
        log_success "Android Virtual Device '$avd_name' created successfully"
        return 0
    fi
    
    # If primary creation fails, try compact version
    log_warning "Primary AVD creation failed, trying compact version..."
    if echo "no" | "$avdmanager" create avd \
        -n "$compact_avd" \
        -k "system-images;android-34;google_apis;x86_64" \
        -d "pixel_3a" \
        -c 512M \
        --force 2>/dev/null; then
        log_success "Compact Android Virtual Device '$compact_avd' created successfully"
    else
        log_warning "AVD creation failed - you can create one manually in Android Studio"
    fi
}

# Build and deploy SASEWaddle mobile app
build_and_deploy_app() {
    log_info "Building and deploying SASEWaddle mobile app..."
    
    local mobile_dir="/workspaces/SASEWaddle/clients/mobile"
    
    # Check if mobile project exists
    if [ ! -d "$mobile_dir" ]; then
        log_warning "SASEWaddle mobile project not found at $mobile_dir"
        return 0
    fi
    
    cd "$mobile_dir" || return 1
    
    # Check if dependencies are installed
    if [ ! -d "node_modules" ]; then
        log_info "Installing React Native dependencies..."
        npm install --silent || log_warning "Failed to install dependencies"
    fi
    
    # Build the Android APK
    log_info "Building Android APK..."
    cd android || return 1
    
    if ./gradlew assembleDebug --no-daemon --quiet; then
        local apk_path="$mobile_dir/android/app/build/outputs/apk/debug/app-debug.apk"
        
        if [ -f "$apk_path" ]; then
            log_success "✅ APK built successfully: $(basename "$apk_path")"
            log_info "APK Size: $(du -h "$apk_path" | cut -f1)"
            
            # Check if emulator is running
            local device_count=$(adb devices | grep -c "emulator\|device")
            
            if [ "$device_count" -gt 1 ]; then
                log_info "Installing app to connected device/emulator..."
                if adb install -r "$apk_path" 2>/dev/null; then
                    log_success "✅ App installed successfully!"
                    log_info "Launch the app on your device to test SASEWaddle mobile"
                else
                    log_warning "⚠️  App installation failed - no device connected"
                fi
            else
                log_info "📱 APK ready for installation (no device connected)"
                log_info "To install: adb install -r \"$apk_path\""
            fi
        else
            log_warning "APK file not found after build"
        fi
    else
        log_warning "Android build failed - check React Native configuration"
    fi
    
    cd "$OLDPWD" || true
}

# Start Android emulator (optional)
start_emulator() {
    local avd_name="${1:-SASEWaddle_Test_Device}"
    local compact_avd="SASEWaddle_Compact"
    
    log_info "Starting Android emulator..."
    
    # Check if emulator is already running
    if adb devices | grep -q "emulator"; then
        log_info "Emulator is already running"
        return 0
    fi
    
    # Try to start primary AVD
    if $ANDROID_HOME/cmdline-tools/latest/bin/avdmanager list avd 2>/dev/null | grep -q "$avd_name"; then
        log_info "Starting emulator with AVD: $avd_name"
        nohup $ANDROID_HOME/emulator/emulator -avd "$avd_name" -no-audio -gpu swiftshader_indirect -memory 2048 > /tmp/emulator.log 2>&1 &
    elif $ANDROID_HOME/cmdline-tools/latest/bin/avdmanager list avd 2>/dev/null | grep -q "$compact_avd"; then
        log_info "Starting emulator with compact AVD: $compact_avd"
        nohup $ANDROID_HOME/emulator/emulator -avd "$compact_avd" -no-audio -gpu swiftshader_indirect -memory 1024 > /tmp/emulator.log 2>&1 &
    else
        log_warning "No AVD found - create one with: avdmanager create avd"
        return 1
    fi
    
    log_info "Emulator starting in background (check with: adb devices)"
    log_info "Emulator log: tail -f /tmp/emulator.log"
}

# Create desktop shortcuts and scripts
create_shortcuts() {
    log_info "Creating desktop shortcuts and launch scripts..."
    
    # Create Android Studio launcher script
    cat > "$HOME/launch-android-studio.sh" << EOF
#!/bin/bash
export ANDROID_HOME=$ANDROID_HOME
export ANDROID_SDK_ROOT=\$ANDROID_HOME
export PATH=\$PATH:\$ANDROID_HOME/cmdline-tools/latest/bin:\$ANDROID_HOME/platform-tools:\$ANDROID_HOME/emulator
export JAVA_HOME=$JAVA_HOME

cd /workspaces/SASEWaddle/clients/mobile
$INSTALL_DIR/android-studio/bin/studio.sh "\$@"
EOF
    
    chmod +x "$HOME/launch-android-studio.sh"
    
    # Create React Native project opener script
    cat > "$HOME/open-sasewaddle-mobile.sh" << EOF
#!/bin/bash
export ANDROID_HOME=$ANDROID_HOME
export ANDROID_SDK_ROOT=\$ANDROID_HOME
export PATH=\$PATH:\$ANDROID_HOME/cmdline-tools/latest/bin:\$ANDROID_HOME/platform-tools:\$ANDROID_HOME/emulator
export JAVA_HOME=$JAVA_HOME

cd /workspaces/SASEWaddle/clients/mobile
echo "Opening SASEWaddle Mobile project in Android Studio..."
$INSTALL_DIR/android-studio/bin/studio.sh android/
EOF
    
    chmod +x "$HOME/open-sasewaddle-mobile.sh"
    
    log_success "Launch scripts created:"
    echo "  • ~/launch-android-studio.sh - Launch Android Studio"
    echo "  • ~/open-sasewaddle-mobile.sh - Open SASEWaddle mobile project"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    
    local issues=()
    
    # Check Android Studio
    if [ ! -f "$INSTALL_DIR/android-studio/bin/studio.sh" ]; then
        issues+=("Android Studio executable not found")
    fi
    
    # Check Android SDK
    if [ ! -d "$ANDROID_HOME" ]; then
        issues+=("Android SDK directory not found")
    fi
    
    # Check SDK manager
    if [ ! -f "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" ]; then
        issues+=("Android SDK manager not found")
    fi
    
    # Check platform tools
    if [ ! -f "$ANDROID_HOME/platform-tools/adb" ]; then
        issues+=("Android platform tools not found")
    fi
    
    if [ ${#issues[@]} -eq 0 ]; then
        log_success "Installation verification passed!"
        
        # Additional verification tests
        log_info "Running additional verification tests..."
        
        # Test Android Studio launch
        if timeout 5s "$INSTALL_DIR/android-studio/bin/studio.sh" --help >/dev/null 2>&1; then
            log_success "✅ Android Studio executable works"
        else
            log_warning "⚠️  Android Studio requires GUI environment"
        fi
        
        # Test ADB
        if "$ANDROID_HOME/platform-tools/adb" version >/dev/null 2>&1; then
            log_success "✅ ADB is working"
        else
            log_warning "⚠️  ADB has issues"
        fi
        
        # Check React Native compatibility if project exists
        if [ -d "/workspaces/SASEWaddle/clients/mobile" ]; then
            log_info "Testing React Native environment..."
            cd /workspaces/SASEWaddle/clients/mobile 2>/dev/null || true
            if command -v npx >/dev/null 2>&1; then
                if timeout 10s npx react-native doctor 2>/dev/null | grep -q "Android Studio"; then
                    log_success "✅ React Native recognizes Android Studio"
                else
                    log_warning "⚠️  React Native environment needs setup"
                fi
            fi
        fi
    else
        log_warning "Installation issues found:"
        for issue in "${issues[@]}"; do
            echo "  • $issue"
        done
    fi
}

# Print installation summary
print_summary() {
    echo
    echo "=============================================="
    echo "  Android Studio Installation Complete!"
    echo "=============================================="
    echo
    log_success "Installation Summary:"
    echo "  • Android Studio: $INSTALL_DIR/android-studio/"
    echo "  • Android SDK: $ANDROID_HOME"
    echo "  • Java Home: $JAVA_HOME"
    echo
    log_info "Next Steps:"
    echo "  1. Reload your shell: source ~/.bashrc"
    echo "  2. Launch Android Studio: ~/launch-android-studio.sh"
    echo "  3. Open SASEWaddle project: ~/open-sasewaddle-mobile.sh"
    echo "  4. Start Android emulator to test the app"
    echo
    log_info "Useful Commands:"
    echo "  • List AVDs: avdmanager list avd"
    echo "  • Start emulator: ./scripts/setup-android-studio.sh --start-emulator"
    echo "  • ADB devices: adb devices"
    echo "  • Build and deploy app: ./scripts/setup-android-studio.sh --build-app"
    echo "  • Build React Native: cd clients/mobile && npx react-native run-android"
    echo "  • React Native doctor: npx react-native doctor"
    echo "  • Build Android APK: cd clients/mobile/android && ./gradlew assembleDebug --no-daemon"
    echo "  • Install APK: adb install -r path/to/app-debug.apk"
    echo
    log_info "Environment Variables Set:"
    echo "  • ANDROID_HOME=$ANDROID_HOME"
    echo "  • ANDROID_SDK_ROOT=$ANDROID_HOME"
    echo "  • JAVA_HOME=$JAVA_HOME"
    echo
    log_info "Troubleshooting:"
    echo "  • If React Native build fails with namespace issues, update node modules"
    echo "  • For Gradle daemon crashes, use --no-daemon flag"
    echo "  • Verify environment: npx react-native doctor"
    echo "  • Check ADB connection: adb devices"
    echo
}

# Cleanup function
cleanup() {
    log_info "Cleaning up temporary files..."
    rm -f /tmp/android-studio-*.tar.gz
    rm -f /tmp/commandlinetools-linux-latest.zip
    log_success "Cleanup completed"
}

# Main installation function
main() {
    log_info "Starting Android Studio installation..."
    echo
    
    check_prerequisites
    download_android_studio
    install_android_studio
    install_android_sdk
    install_sdk_components
    setup_environment
    create_avd
    create_shortcuts
    verify_installation
    build_and_deploy_app
    cleanup
    print_summary
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Android Studio Setup Script for SASEWaddle"
        echo
        echo "Usage: $0 [OPTIONS]"
        echo
        echo "Options:"
        echo "  --help, -h          Show this help message"
        echo "  --verify            Only verify existing installation"
        echo "  --cleanup           Only cleanup temporary files"
        echo "  --build-app         Only build and deploy SASEWaddle app"
        echo "  --start-emulator    Start Android emulator"
        echo "  --create-avd        Create Android Virtual Device only"
        echo
        echo "This script will install Android Studio, Android SDK, set up"
        echo "the development environment, and deploy the SASEWaddle mobile app."
        echo
        exit 0
        ;;
    --verify)
        setup_environment
        verify_installation
        ;;
    --cleanup)
        cleanup
        ;;
    --build-app)
        setup_environment
        build_and_deploy_app
        ;;
    --start-emulator)
        setup_environment
        start_emulator "${2:-SASEWaddle_Test_Device}"
        ;;
    --create-avd)
        setup_environment
        create_avd
        ;;
    *)
        main
        ;;
esac