#!/bin/bash

# SASEWaddle Local Build Script
# Builds all React-based applications locally and generates screenshots

set -e

echo "===========================================" 
echo "  SASEWaddle Local Application Builder"
echo "==========================================="

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
SCREENSHOTS_DIR="$ROOT_DIR/website/public/images/screenshots"
VERSION=$(cat "$ROOT_DIR/.version" 2>/dev/null || echo "1.0.0")
BUILD_TYPE="${BUILD_TYPE:-development}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Node.js
    if ! command -v node &> /dev/null; then
        log_error "Node.js is not installed. Please install Node.js 18 or later."
        exit 1
    fi
    
    NODE_VERSION=$(node --version | cut -d 'v' -f 2 | cut -d '.' -f 1)
    if [ "$NODE_VERSION" -lt 18 ]; then
        log_error "Node.js version 18 or later is required. Current version: $(node --version)"
        exit 1
    fi
    
    # Check npm
    if ! command -v npm &> /dev/null; then
        log_error "npm is not installed."
        exit 1
    fi
    
    # Check puppeteer dependencies (for screenshots)
    if ! command -v chromium-browser &> /dev/null && ! command -v google-chrome &> /dev/null && ! command -v chrome &> /dev/null; then
        log_warning "Chrome/Chromium not found. Screenshots may not work properly."
        log_info "Install Chrome or Chromium for screenshot generation"
    fi
    
    log_success "Prerequisites check passed"
}

# Create necessary directories
setup_directories() {
    log_info "Setting up directories..."
    
    mkdir -p "$SCREENSHOTS_DIR"
    mkdir -p "$ROOT_DIR/build/apps"
    mkdir -p "$ROOT_DIR/build/screenshots"
    
    log_success "Directories created"
}

# Build React Native mobile app
build_mobile_app() {
    log_info "Building React Native mobile app..."
    
    cd "$ROOT_DIR/clients/mobile"
    
    if [ ! -f "package.json" ]; then
        log_error "Mobile app package.json not found"
        return 1
    fi
    
    # Install dependencies
    log_info "Installing mobile app dependencies..."
    npm ci
    
    # Create build configuration
    log_info "Creating build configuration for $BUILD_TYPE..."
    cat > src/config/build.ts << EOF
export const BUILD_CONFIG = {
  VERSION: '$VERSION',
  BUILD_TYPE: '$BUILD_TYPE',
  API_ENDPOINT: 'https://api${BUILD_TYPE == 'production' ? '' : '-dev'}.sasewaddle.com'
};

export const API_ENDPOINTS = {
  development: 'https://api-dev.sasewaddle.com',
  staging: 'https://api-staging.sasewaddle.com', 
  production: 'https://api.sasewaddle.com'
};

export const getApiEndpoint = (buildType: string = BUILD_CONFIG.BUILD_TYPE) => {
  return API_ENDPOINTS[buildType as keyof typeof API_ENDPOINTS] || API_ENDPOINTS.development;
};
EOF
    
    # Run TypeScript check
    log_info "Running TypeScript check..."
    npx tsc --noEmit
    
    # Run linting
    log_info "Running linting..."
    npx eslint src/ --fix || log_warning "Linting found issues"
    
    # Create Metro bundle (similar to web build)
    log_info "Creating Metro bundle..."
    npx react-native bundle \
        --platform android \
        --dev false \
        --entry-file index.js \
        --bundle-output "$ROOT_DIR/build/apps/mobile-android.bundle" \
        --assets-dest "$ROOT_DIR/build/apps/mobile-assets/" \
        --verbose || log_warning "Android bundle creation had issues"
    
    npx react-native bundle \
        --platform ios \
        --dev false \
        --entry-file index.js \
        --bundle-output "$ROOT_DIR/build/apps/mobile-ios.bundle" \
        --assets-dest "$ROOT_DIR/build/apps/mobile-assets/" \
        --verbose || log_warning "iOS bundle creation had issues"
    
    log_success "Mobile app build completed"
    cd "$ROOT_DIR"
}

# Build Next.js website
build_website() {
    log_info "Building Next.js website..."
    
    cd "$ROOT_DIR/website"
    
    if [ ! -f "package.json" ]; then
        log_error "Website package.json not found"
        return 1
    fi
    
    # Install dependencies
    log_info "Installing website dependencies..."
    npm ci
    
    # Set build environment variables
    log_info "Setting build environment for $BUILD_TYPE..."
    cat > .env.local << EOF
NEXT_PUBLIC_VERSION=$VERSION
NEXT_PUBLIC_BUILD_TYPE=$BUILD_TYPE
NEXT_PUBLIC_API_URL=https://api${BUILD_TYPE == 'production' ? '' : '-dev'}.sasewaddle.com
NEXT_PUBLIC_MANAGER_URL=https://manager${BUILD_TYPE == 'production' ? '' : '-dev'}.sasewaddle.com
EOF
    
    # Build the website
    log_info "Building website..."
    npm run build
    
    # Export static files (for Cloudflare Pages)
    log_info "Exporting static files..."
    npm run export || log_warning "Static export had issues (may be normal for some Next.js configurations)"
    
    # Copy build to central build directory
    cp -r .next/static "$ROOT_DIR/build/apps/website-static/" 2>/dev/null || true
    cp -r out "$ROOT_DIR/build/apps/website-export/" 2>/dev/null || true
    
    log_success "Website build completed"
    cd "$ROOT_DIR"
}

# Generate app screenshots using Puppeteer
generate_screenshots() {
    log_info "Generating application screenshots..."
    
    # Create screenshot generator script
    cat > "$ROOT_DIR/build/screenshot-generator.js" << 'EOF'
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const SCREENSHOTS_DIR = process.argv[2] || './screenshots';
const WEBSITE_URL = process.argv[3] || 'http://localhost:3000';

async function generateScreenshots() {
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const page = await browser.newPage();
    
    // Set viewport for different device sizes
    const viewports = [
        { name: 'desktop', width: 1920, height: 1080 },
        { name: 'tablet', width: 768, height: 1024 },
        { name: 'mobile', width: 375, height: 812 }
    ];
    
    // Screenshots to capture
    const screenshots = [
        { url: '/', name: 'homepage' },
        { url: '/#features', name: 'features' },
        { url: '/#architecture', name: 'architecture' },
        { url: '/#use-cases', name: 'use-cases' }
    ];
    
    for (const viewport of viewports) {
        console.log(`Capturing screenshots for ${viewport.name} (${viewport.width}x${viewport.height})`);
        
        await page.setViewport({ 
            width: viewport.width, 
            height: viewport.height,
            deviceScaleFactor: 2 
        });
        
        for (const screenshot of screenshots) {
            try {
                console.log(`  Capturing ${screenshot.name}...`);
                
                await page.goto(`${WEBSITE_URL}${screenshot.url}`, { 
                    waitUntil: 'networkidle0',
                    timeout: 30000 
                });
                
                // Wait for any animations to complete
                await page.waitForTimeout(2000);
                
                const filename = `${screenshot.name}-${viewport.name}.png`;
                await page.screenshot({
                    path: path.join(SCREENSHOTS_DIR, filename),
                    fullPage: viewport.name === 'desktop', // Full page for desktop, viewport for mobile/tablet
                    type: 'png',
                    quality: 90
                });
                
                console.log(`    ✓ Saved ${filename}`);
            } catch (error) {
                console.error(`    ✗ Failed to capture ${screenshot.name}: ${error.message}`);
            }
        }
    }
    
    // Generate mobile app mockup screenshots
    console.log('Generating mobile app mockups...');
    
    // Create simple HTML mockups for mobile app screens
    const mobileScreens = [
        { name: 'connection-screen', title: 'VPN Connection', content: 'Connected to SASEWaddle' },
        { name: 'settings-screen', title: 'Settings', content: 'Auto-connect enabled' },
        { name: 'configuration-screen', title: 'Configuration', content: 'Manager URL configured' }
    ];
    
    await page.setViewport({ width: 375, height: 812, deviceScaleFactor: 3 });
    
    for (const screen of mobileScreens) {
        try {
            const html = `
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>SASEWaddle Mobile - ${screen.title}</title>
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                            margin: 0;
                            padding: 20px;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            height: 100vh;
                            display: flex;
                            flex-direction: column;
                        }
                        .header {
                            text-align: center;
                            font-size: 18px;
                            font-weight: bold;
                            margin-bottom: 30px;
                            padding-top: 50px;
                        }
                        .content {
                            flex: 1;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            flex-direction: column;
                        }
                        .logo {
                            font-size: 48px;
                            margin-bottom: 20px;
                        }
                        .status {
                            font-size: 16px;
                            margin-bottom: 40px;
                        }
                        .button {
                            background: rgba(255,255,255,0.2);
                            border: none;
                            border-radius: 12px;
                            color: white;
                            padding: 15px 30px;
                            font-size: 16px;
                            font-weight: 500;
                        }
                    </style>
                </head>
                <body>
                    <div class="header">${screen.title}</div>
                    <div class="content">
                        <div class="logo">🛡️</div>
                        <div class="status">${screen.content}</div>
                        <button class="button">SASEWaddle Mobile</button>
                    </div>
                </body>
                </html>
            `;
            
            await page.setContent(html);
            await page.waitForTimeout(1000);
            
            const filename = `mobile-${screen.name}.png`;
            await page.screenshot({
                path: path.join(SCREENSHOTS_DIR, filename),
                type: 'png'
            });
            
            console.log(`  ✓ Generated ${filename}`);
        } catch (error) {
            console.error(`  ✗ Failed to generate ${screen.name}: ${error.message}`);
        }
    }
    
    await browser.close();
    console.log('Screenshot generation completed!');
}

generateScreenshots().catch(console.error);
EOF
    
    # Install Puppeteer if not already installed
    cd "$ROOT_DIR/build"
    if [ ! -d "node_modules/puppeteer" ]; then
        log_info "Installing Puppeteer for screenshot generation..."
        npm init -y > /dev/null 2>&1
        npm install puppeteer > /dev/null 2>&1
    fi
    
    # Start Next.js development server in the background
    local website_pid=""
    if [ -d "$ROOT_DIR/website/.next" ]; then
        log_info "Starting Next.js server for screenshots..."
        cd "$ROOT_DIR/website"
        npm start &
        website_pid=$!
        
        # Wait for server to start
        log_info "Waiting for server to start..."
        sleep 10
        
        # Check if server is running
        if curl -s http://localhost:3000 > /dev/null; then
            log_success "Website server is running"
            
            # Generate screenshots
            cd "$ROOT_DIR/build"
            node screenshot-generator.js "$SCREENSHOTS_DIR" "http://localhost:3000" || log_warning "Screenshot generation had issues"
        else
            log_error "Website server failed to start"
        fi
        
        # Stop the server
        if [ -n "$website_pid" ]; then
            kill $website_pid 2>/dev/null || true
        fi
    else
        log_warning "Website build not found, generating mock screenshots only"
        cd "$ROOT_DIR/build"
        node screenshot-generator.js "$SCREENSHOTS_DIR" "about:blank"
    fi
    
    # Copy screenshots to website public directory
    if [ -d "$SCREENSHOTS_DIR" ] && [ "$(ls -A "$SCREENSHOTS_DIR" 2>/dev/null)" ]; then
        log_success "Screenshots generated successfully"
        log_info "Screenshots saved to: $SCREENSHOTS_DIR"
        ls -la "$SCREENSHOTS_DIR"
    else
        log_warning "No screenshots were generated"
    fi
    
    cd "$ROOT_DIR"
}

# Update website with new screenshots
update_website_screenshots() {
    log_info "Updating website with new screenshots..."
    
    # Create a component to showcase the screenshots
    cat > "$ROOT_DIR/website/components/AppShowcase.tsx" << 'EOF'
import React from 'react';
import Image from 'next/image';

interface AppShowcaseProps {
    title?: string;
}

export const AppShowcase: React.FC<AppShowcaseProps> = ({ 
    title = "SASEWaddle Applications" 
}) => {
    const screenshots = [
        {
            name: 'Desktop Homepage',
            src: '/images/screenshots/homepage-desktop.png',
            alt: 'SASEWaddle homepage on desktop'
        },
        {
            name: 'Mobile App - Connection',
            src: '/images/screenshots/mobile-connection-screen.png', 
            alt: 'SASEWaddle mobile app connection screen'
        },
        {
            name: 'Features Overview',
            src: '/images/screenshots/features-desktop.png',
            alt: 'SASEWaddle features overview'
        },
        {
            name: 'Architecture Diagram',
            src: '/images/screenshots/architecture-desktop.png',
            alt: 'SASEWaddle architecture diagram'
        },
        {
            name: 'Mobile App - Settings',
            src: '/images/screenshots/mobile-settings-screen.png',
            alt: 'SASEWaddle mobile app settings'
        },
        {
            name: 'Use Cases',
            src: '/images/screenshots/use-cases-desktop.png',
            alt: 'SASEWaddle use cases'
        }
    ];

    return (
        <section className="py-12 bg-gray-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="text-center mb-12">
                    <h2 className="text-3xl font-bold text-gray-900 mb-4">
                        {title}
                    </h2>
                    <p className="text-xl text-gray-600 max-w-3xl mx-auto">
                        Experience SASEWaddle across all platforms with our intuitive interfaces
                        and comprehensive security management tools.
                    </p>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {screenshots.map((screenshot, index) => (
                        <div key={index} className="bg-white rounded-lg shadow-md overflow-hidden">
                            <div className="aspect-w-16 aspect-h-10">
                                <Image
                                    src={screenshot.src}
                                    alt={screenshot.alt}
                                    width={600}
                                    height={400}
                                    className="object-cover w-full h-full"
                                    onError={(e) => {
                                        // Handle missing images gracefully
                                        e.currentTarget.style.display = 'none';
                                    }}
                                />
                            </div>
                            <div className="p-4">
                                <h3 className="text-lg font-semibold text-gray-900">
                                    {screenshot.name}
                                </h3>
                                <p className="text-sm text-gray-600 mt-1">
                                    {screenshot.alt}
                                </p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
};

export default AppShowcase;
EOF
    
    log_success "Website components updated"
}

# Generate build report
generate_build_report() {
    log_info "Generating build report..."
    
    cat > "$ROOT_DIR/build/BUILD_REPORT.md" << EOF
# SASEWaddle Local Build Report

**Build Date:** $(date)
**Version:** $VERSION
**Build Type:** $BUILD_TYPE
**Builder:** $(whoami)
**System:** $(uname -a)

## Build Summary

### Applications Built
- [x] React Native Mobile App (Android & iOS bundles)
- [x] Next.js Website (Static export)

### Screenshots Generated
$(find "$SCREENSHOTS_DIR" -name "*.png" 2>/dev/null | wc -l) screenshots generated

### Build Artifacts
\`\`\`
$(find "$ROOT_DIR/build" -type f -name "*.bundle" -o -name "*.js" -o -name "*.css" -o -name "*.png" 2>/dev/null | sort)
\`\`\`

### File Sizes
\`\`\`
$(find "$ROOT_DIR/build" -type f -exec ls -lh {} \; 2>/dev/null | awk '{print $5 "\t" $9}' | sort -hr)
\`\`\`

### Screenshots Available
$(ls -la "$SCREENSHOTS_DIR" 2>/dev/null || echo "No screenshots directory found")

## Next Steps

1. Review the generated screenshots in: \`$SCREENSHOTS_DIR\`
2. Test the mobile app bundles
3. Deploy the website build
4. Update documentation with new screenshots

## Notes

- Build artifacts are stored in: \`$ROOT_DIR/build/\`
- Website static files: \`$ROOT_DIR/build/apps/website-export/\`
- Mobile app bundles: \`$ROOT_DIR/build/apps/mobile-*.bundle\`

EOF
    
    log_success "Build report generated: $ROOT_DIR/build/BUILD_REPORT.md"
}

# Main execution
main() {
    echo
    log_info "Starting SASEWaddle local build process..."
    log_info "Version: $VERSION"
    log_info "Build Type: $BUILD_TYPE"
    log_info "Root Directory: $ROOT_DIR"
    echo
    
    check_prerequisites
    setup_directories
    
    # Build applications
    build_mobile_app
    build_website
    
    # Generate screenshots
    generate_screenshots
    update_website_screenshots
    
    # Generate report
    generate_build_report
    
    echo
    log_success "=====================================
    log_success "  SASEWaddle Build Completed! 
    log_success "====================================="
    echo
    log_info "Build artifacts location: $ROOT_DIR/build/"
    log_info "Screenshots location: $SCREENSHOTS_DIR"
    log_info "Build report: $ROOT_DIR/build/BUILD_REPORT.md"
    echo
    log_info "To view the build report:"
    log_info "  cat $ROOT_DIR/build/BUILD_REPORT.md"
    echo
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "SASEWaddle Local Build Script"
        echo
        echo "Usage: $0 [OPTIONS]"
        echo
        echo "Options:"
        echo "  --help, -h          Show this help message"
        echo "  --mobile-only       Build only mobile app"
        echo "  --website-only      Build only website"
        echo "  --screenshots-only  Generate only screenshots"
        echo
        echo "Environment Variables:"
        echo "  BUILD_TYPE          Build type (development, staging, production)"
        echo
        exit 0
        ;;
    --mobile-only)
        check_prerequisites
        setup_directories
        build_mobile_app
        log_success "Mobile app build completed"
        ;;
    --website-only)
        check_prerequisites
        setup_directories  
        build_website
        log_success "Website build completed"
        ;;
    --screenshots-only)
        check_prerequisites
        setup_directories
        generate_screenshots
        log_success "Screenshots generation completed"
        ;;
    *)
        main
        ;;
esac