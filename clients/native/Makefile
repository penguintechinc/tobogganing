# SASEWaddle Native Client Makefile
# Supports cross-compilation for Mac Universal, Windows, and Linux

APP_NAME := sasewaddle-client
VERSION := 1.0.0
BUILD_TIME := $(shell date -u '+%Y-%m-%d_%H:%M:%S')
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo 'unknown')

# Go build flags
LDFLAGS := -ldflags="-X main.version=${VERSION} -X main.buildTime=${BUILD_TIME} -X main.gitCommit=${GIT_COMMIT} -w -s"

# Output directory
BUILD_DIR := build

# Default target
.PHONY: all
all: clean mac windows linux

# Clean build directory
.PHONY: clean
clean:
	rm -rf $(BUILD_DIR)
	mkdir -p $(BUILD_DIR)

# macOS Universal Binary (Intel + Apple Silicon)
.PHONY: mac
mac: mac-amd64 mac-arm64
	@echo "Creating macOS Universal binary..."
	lipo -create -output $(BUILD_DIR)/$(APP_NAME)-darwin-universal \
		$(BUILD_DIR)/$(APP_NAME)-darwin-amd64 \
		$(BUILD_DIR)/$(APP_NAME)-darwin-arm64
	rm $(BUILD_DIR)/$(APP_NAME)-darwin-amd64 $(BUILD_DIR)/$(APP_NAME)-darwin-arm64

.PHONY: mac-amd64
mac-amd64:
	@echo "Building for macOS Intel..."
	GOOS=darwin GOARCH=amd64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME)-darwin-amd64 ./cmd

.PHONY: mac-arm64
mac-arm64:
	@echo "Building for macOS Apple Silicon..."
	GOOS=darwin GOARCH=arm64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME)-darwin-arm64 ./cmd

# Windows x64
.PHONY: windows
windows:
	@echo "Building for Windows x64..."
	GOOS=windows GOARCH=amd64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME)-windows-amd64.exe ./cmd

# Linux builds
.PHONY: linux
linux: linux-amd64 linux-arm64

.PHONY: linux-amd64
linux-amd64:
	@echo "Building for Linux x64..."
	GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME)-linux-amd64 ./cmd

.PHONY: linux-arm64
linux-arm64:
	@echo "Building for Linux ARM64..."
	GOOS=linux GOARCH=arm64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME)-linux-arm64 ./cmd

# Build for current platform only
.PHONY: local
local:
	@echo "Building for current platform..."
	go build $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME) ./cmd

# Development build with race detection
.PHONY: dev
dev:
	@echo "Building development version..."
	go build -race $(LDFLAGS) -o $(BUILD_DIR)/$(APP_NAME)-dev ./cmd

# Run tests
.PHONY: test
test:
	go test -v -race ./...

# Run linter
.PHONY: lint
lint:
	golangci-lint run

# Install dependencies
.PHONY: deps
deps:
	go mod download
	go mod tidy

# Create release packages
.PHONY: package
package: all
	@echo "Creating release packages..."
	
	# macOS package
	mkdir -p $(BUILD_DIR)/packages/macos
	cp $(BUILD_DIR)/$(APP_NAME)-darwin-universal $(BUILD_DIR)/packages/macos/$(APP_NAME)
	chmod +x $(BUILD_DIR)/packages/macos/$(APP_NAME)
	tar -czf $(BUILD_DIR)/$(APP_NAME)-${VERSION}-darwin-universal.tar.gz -C $(BUILD_DIR)/packages/macos .
	
	# Windows package
	mkdir -p $(BUILD_DIR)/packages/windows
	cp $(BUILD_DIR)/$(APP_NAME)-windows-amd64.exe $(BUILD_DIR)/packages/windows/
	zip -r $(BUILD_DIR)/$(APP_NAME)-${VERSION}-windows-amd64.zip $(BUILD_DIR)/packages/windows/
	
	# Linux AMD64 package
	mkdir -p $(BUILD_DIR)/packages/linux-amd64
	cp $(BUILD_DIR)/$(APP_NAME)-linux-amd64 $(BUILD_DIR)/packages/linux-amd64/$(APP_NAME)
	chmod +x $(BUILD_DIR)/packages/linux-amd64/$(APP_NAME)
	tar -czf $(BUILD_DIR)/$(APP_NAME)-${VERSION}-linux-amd64.tar.gz -C $(BUILD_DIR)/packages/linux-amd64 .
	
	# Linux ARM64 package
	mkdir -p $(BUILD_DIR)/packages/linux-arm64
	cp $(BUILD_DIR)/$(APP_NAME)-linux-arm64 $(BUILD_DIR)/packages/linux-arm64/$(APP_NAME)
	chmod +x $(BUILD_DIR)/packages/linux-arm64/$(APP_NAME)
	tar -czf $(BUILD_DIR)/$(APP_NAME)-${VERSION}-linux-arm64.tar.gz -C $(BUILD_DIR)/packages/linux-arm64 .
	
	@echo "Release packages created in $(BUILD_DIR)/"

# Install locally (for development)
.PHONY: install
install: local
	cp $(BUILD_DIR)/$(APP_NAME) /usr/local/bin/
	@echo "Installed $(APP_NAME) to /usr/local/bin/"

# Uninstall
.PHONY: uninstall
uninstall:
	rm -f /usr/local/bin/$(APP_NAME)
	@echo "Uninstalled $(APP_NAME)"

# Show build info
.PHONY: info
info:
	@echo "App Name: $(APP_NAME)"
	@echo "Version: $(VERSION)"
	@echo "Build Time: $(BUILD_TIME)"
	@echo "Git Commit: $(GIT_COMMIT)"

# Help
.PHONY: help
help:
	@echo "SASEWaddle Native Client Build System"
	@echo ""
	@echo "Targets:"
	@echo "  all       - Build for all platforms (macOS Universal, Windows, Linux)"
	@echo "  mac       - Build macOS Universal binary"
	@echo "  windows   - Build Windows x64 binary"
	@echo "  linux     - Build Linux binaries (AMD64 + ARM64)"
	@echo "  local     - Build for current platform only"
	@echo "  dev       - Development build with race detection"
	@echo "  test      - Run tests"
	@echo "  lint      - Run linter"
	@echo "  deps      - Install dependencies"
	@echo "  package   - Create release packages"
	@echo "  install   - Install locally"
	@echo "  uninstall - Uninstall"
	@echo "  clean     - Clean build directory"
	@echo "  info      - Show build information"
	@echo "  help      - Show this help"