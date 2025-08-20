# SASEWaddle Build Scripts

This directory contains utility scripts for building and managing SASEWaddle applications locally.

## Available Scripts

### `build-apps.sh`

Comprehensive local build script for all SASEWaddle React-based applications.

**Features:**
- ✅ Builds React Native mobile app bundles (Android & iOS)
- ✅ Builds Next.js website with static export
- ✅ Generates application screenshots automatically
- ✅ Creates build reports and artifact summaries
- ✅ Supports multiple build types (development, staging, production)

**Prerequisites:**
- Node.js 18 or later
- npm
- Chrome/Chromium (for screenshots)

**Usage:**

```bash
# Full build (mobile + website + screenshots)
./scripts/build-apps.sh

# Build specific components
./scripts/build-apps.sh --mobile-only
./scripts/build-apps.sh --website-only  
./scripts/build-apps.sh --screenshots-only

# Set build type
BUILD_TYPE=production ./scripts/build-apps.sh

# Get help
./scripts/build-apps.sh --help
```

**Output:**
- Build artifacts: `./build/`
- Screenshots: `./website/public/images/screenshots/`
- Build report: `./build/BUILD_REPORT.md`

**Environment Variables:**
- `BUILD_TYPE`: `development`, `staging`, or `production` (default: `development`)

## Build Artifacts

The build process generates the following artifacts:

### Mobile App Bundles
- `build/apps/mobile-android.bundle` - Android Metro bundle
- `build/apps/mobile-ios.bundle` - iOS Metro bundle
- `build/apps/mobile-assets/` - Shared mobile assets

### Website Build
- `build/apps/website-static/` - Next.js static files
- `build/apps/website-export/` - Exported static site

### Screenshots
- `website/public/images/screenshots/homepage-desktop.png`
- `website/public/images/screenshots/homepage-tablet.png` 
- `website/public/images/screenshots/homepage-mobile.png`
- `website/public/images/screenshots/features-desktop.png`
- `website/public/images/screenshots/architecture-desktop.png`
- `website/public/images/screenshots/use-cases-desktop.png`
- `website/public/images/screenshots/mobile-connection-screen.png`
- `website/public/images/screenshots/mobile-settings-screen.png`
- `website/public/images/screenshots/mobile-configuration-screen.png`

### Build Report
- `build/BUILD_REPORT.md` - Comprehensive build summary with file sizes and artifact locations

## Integration with CI/CD

These scripts complement the GitHub Actions workflows:

- **GitHub Actions** - Automated builds on PRs and releases
- **Local Scripts** - Development builds and screenshot generation  
- **Manual Workflows** - On-demand builds with custom parameters

## Troubleshooting

### Common Issues

**Node.js Version**
```bash
# Check Node.js version
node --version  # Should be 18+

# Install/update Node.js using nvm
nvm install 18
nvm use 18
```

**Chrome/Chromium Missing**
```bash
# Ubuntu/Debian
sudo apt-get install chromium-browser

# macOS
brew install chromium

# Or set custom Chrome path
export CHROME_BIN=/path/to/chrome
```

**Permission Errors**
```bash
# Make script executable
chmod +x scripts/build-apps.sh

# Fix npm permissions
sudo chown -R $(whoami) ~/.npm
```

**Build Failures**
```bash
# Clear npm caches
npm cache clean --force

# Remove node_modules and reinstall
rm -rf clients/mobile/node_modules website/node_modules
./scripts/build-apps.sh
```

### Getting Help

1. Run `./scripts/build-apps.sh --help` for usage information
2. Check the build report at `build/BUILD_REPORT.md` for detailed output
3. Review logs in the console output for specific error messages
4. Ensure all prerequisites are installed and up to date

## Contributing

When adding new build features:

1. Update the build script with appropriate error handling
2. Add documentation to this README
3. Test with all build types (development, staging, production) 
4. Ensure generated artifacts are properly structured
5. Update the build report generation to include new artifacts