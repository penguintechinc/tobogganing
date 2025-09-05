# Makefile for Tobogganing Kubernetes CNI Plugin
#
# This Makefile provides targets for building, testing, and deploying
# the high-performance Tobogganing CNI plugin for Kubernetes.

# Build variables
BINARY_NAME := tobogganing-cni
PACKAGE := github.com/tobogganing/k8s-cni
BUILD_DIR := build
DIST_DIR := dist

# Version information
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
GIT_COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo "unknown")
BUILD_DATE := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")

# Go build flags
GO_BUILD_FLAGS := -ldflags "-s -w -X main.BuildVersion=$(VERSION) -X main.GitCommit=$(GIT_COMMIT)"
CGO_ENABLED := 0
GOOS := linux

# Docker configuration
DOCKER_REGISTRY ?= tobogganing
DOCKER_IMAGE := $(DOCKER_REGISTRY)/cni
DOCKER_TAG ?= $(VERSION)

# Test configuration
TEST_TIMEOUT := 10m
TEST_PACKAGES := ./pkg/... ./tests/...

# Linting configuration
GOLANGCI_LINT_VERSION := v1.55.2

# Architecture targets
ARCHITECTURES := amd64 arm64

.PHONY: all build test clean lint fmt vet check docker install uninstall help

##@ General

all: clean lint test build ## Build everything after cleaning, linting, and testing

help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

fmt: ## Format Go code
	@echo "Formatting Go code..."
	@gofmt -s -w .
	@goimports -w .

vet: ## Run Go vet
	@echo "Running go vet..."
	@go vet ./...

lint: ## Run golangci-lint
	@echo "Running golangci-lint..."
	@command -v golangci-lint >/dev/null 2>&1 || { \
		echo "Installing golangci-lint $(GOLANGCI_LINT_VERSION)..."; \
		curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $$(go env GOPATH)/bin $(GOLANGCI_LINT_VERSION); \
	}
	@golangci-lint run --timeout 5m

check: fmt vet lint ## Run all code quality checks

##@ Build

build: build-linux ## Build for Linux (default target platform)

build-linux: ## Build Linux binary
	@echo "Building $(BINARY_NAME) for Linux..."
	@mkdir -p $(BUILD_DIR)
	@CGO_ENABLED=$(CGO_ENABLED) GOOS=linux GOARCH=amd64 go build $(GO_BUILD_FLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-linux-amd64 ./cmd/tobogganing-cni

build-all: ## Build for all supported architectures
	@echo "Building $(BINARY_NAME) for all architectures..."
	@mkdir -p $(BUILD_DIR)
	@for arch in $(ARCHITECTURES); do \
		echo "Building for linux/$$arch..."; \
		CGO_ENABLED=$(CGO_ENABLED) GOOS=linux GOARCH=$$arch go build $(GO_BUILD_FLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-linux-$$arch ./cmd/tobogganing-cni; \
	done

build-race: ## Build with race detection (for testing)
	@echo "Building $(BINARY_NAME) with race detection..."
	@mkdir -p $(BUILD_DIR)
	@CGO_ENABLED=1 go build -race $(GO_BUILD_FLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-race ./cmd/tobogganing-cni

##@ Testing

test: ## Run unit tests
	@echo "Running unit tests..."
	@go test -v -timeout $(TEST_TIMEOUT) -race -coverprofile=coverage.out $(TEST_PACKAGES)

test-short: ## Run short tests only
	@echo "Running short tests..."
	@go test -short -timeout 5m $(TEST_PACKAGES)

test-coverage: test ## Run tests and show coverage
	@echo "Generating coverage report..."
	@go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report generated: coverage.html"

benchmark: ## Run benchmarks
	@echo "Running benchmarks..."
	@go test -bench=. -benchmem $(TEST_PACKAGES)

##@ Docker

docker-build: build-all ## Build Docker image
	@echo "Building Docker image $(DOCKER_IMAGE):$(DOCKER_TAG)..."
	@docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
	@docker tag $(DOCKER_IMAGE):$(DOCKER_TAG) $(DOCKER_IMAGE):latest

docker-build-multi: ## Build multi-architecture Docker image
	@echo "Building multi-architecture Docker image..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

docker-push: docker-build ## Build and push Docker image
	@echo "Pushing Docker image..."
	@docker push $(DOCKER_IMAGE):$(DOCKER_TAG)
	@docker push $(DOCKER_IMAGE):latest

docker-push-multi: ## Build and push multi-architecture Docker image
	@echo "Building and pushing multi-architecture Docker image..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t $(DOCKER_IMAGE):$(DOCKER_TAG) --push .

##@ Kubernetes

k8s-deploy: docker-build ## Deploy to Kubernetes
	@echo "Deploying to Kubernetes..."
	@sed 's|image: tobogganing/cni:latest|image: $(DOCKER_IMAGE):$(DOCKER_TAG)|g' deploy/daemonset.yaml | kubectl apply -f -
	@kubectl apply -f deploy/network-policy.yaml

k8s-undeploy: ## Remove from Kubernetes
	@echo "Removing from Kubernetes..."
	@kubectl delete -f deploy/daemonset.yaml --ignore-not-found
	@kubectl delete -f deploy/network-policy.yaml --ignore-not-found

k8s-logs: ## Show CNI pod logs
	@echo "Showing CNI pod logs..."
	@kubectl logs -n kube-system -l app=tobogganing-cni -f

k8s-status: ## Check CNI pod status
	@echo "Checking CNI pod status..."
	@kubectl get pods -n kube-system -l app=tobogganing-cni
	@kubectl get daemonset -n kube-system tobogganing-cni

##@ Installation

install: build ## Install CNI binary to system
	@echo "Installing $(BINARY_NAME)..."
	@sudo mkdir -p /opt/cni/bin
	@sudo cp $(BUILD_DIR)/$(BINARY_NAME)-linux-amd64 /opt/cni/bin/$(BINARY_NAME)
	@sudo chmod +x /opt/cni/bin/$(BINARY_NAME)
	@echo "CNI binary installed to /opt/cni/bin/$(BINARY_NAME)"

install-config: ## Install example CNI configuration
	@echo "Installing CNI configuration..."
	@sudo mkdir -p /etc/cni/net.d
	@sudo cp examples/cni-config.json /etc/cni/net.d/10-tobogganing.conflist
	@echo "CNI configuration installed to /etc/cni/net.d/10-tobogganing.conflist"

uninstall: ## Remove CNI binary and configuration
	@echo "Removing $(BINARY_NAME)..."
	@sudo rm -f /opt/cni/bin/$(BINARY_NAME)
	@sudo rm -f /etc/cni/net.d/10-tobogganing.conflist
	@echo "CNI plugin uninstalled"

##@ Release

release: clean check test build-all ## Prepare release artifacts
	@echo "Preparing release $(VERSION)..."
	@mkdir -p $(DIST_DIR)
	@for arch in $(ARCHITECTURES); do \
		tar -czf $(DIST_DIR)/$(BINARY_NAME)-$(VERSION)-linux-$$arch.tar.gz -C $(BUILD_DIR) $(BINARY_NAME)-linux-$$arch; \
		sha256sum $(DIST_DIR)/$(BINARY_NAME)-$(VERSION)-linux-$$arch.tar.gz > $(DIST_DIR)/$(BINARY_NAME)-$(VERSION)-linux-$$arch.tar.gz.sha256; \
	done
	@echo "Release artifacts created in $(DIST_DIR)/"

##@ Cleanup

clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR)
	@rm -f coverage.out coverage.html

clean-docker: ## Clean Docker images
	@echo "Cleaning Docker images..."
	@docker rmi $(DOCKER_IMAGE):$(DOCKER_TAG) $(DOCKER_IMAGE):latest 2>/dev/null || true

clean-all: clean clean-docker ## Clean everything

##@ Development Tools

deps: ## Download and verify dependencies
	@echo "Downloading dependencies..."
	@go mod download
	@go mod verify

deps-update: ## Update dependencies
	@echo "Updating dependencies..."
	@go get -u ./...
	@go mod tidy

tools: ## Install development tools
	@echo "Installing development tools..."
	@go install golang.org/x/tools/cmd/goimports@latest
	@go install github.com/golangci/golangci-lint/cmd/golangci-lint@$(GOLANGCI_LINT_VERSION)

##@ Debugging

debug-build: ## Build with debug symbols
	@echo "Building $(BINARY_NAME) with debug symbols..."
	@mkdir -p $(BUILD_DIR)
	@CGO_ENABLED=1 go build -gcflags="all=-N -l" -o $(BUILD_DIR)/$(BINARY_NAME)-debug ./cmd/tobogganing-cni

debug-test: ## Run tests with debug output
	@echo "Running tests with debug output..."
	@TOBOGGANING_CNI_DEBUG=true go test -v $(TEST_PACKAGES)

##@ Documentation

docs: ## Generate documentation
	@echo "Generating documentation..."
	@go doc -all ./pkg/... > docs/API.md

godoc: ## Start local godoc server
	@echo "Starting godoc server on http://localhost:6060..."
	@godoc -http=:6060

##@ Security

security-scan: ## Run security vulnerability scan
	@echo "Running security scan..."
	@command -v gosec >/dev/null 2>&1 || go install github.com/securecodewarrior/gosec/v2/cmd/gosec@latest
	@gosec ./...

##@ Performance

profile-cpu: ## Run CPU profiling
	@echo "Running CPU profiling..."
	@go test -cpuprofile=cpu.prof -bench=. $(TEST_PACKAGES)
	@echo "CPU profile saved as cpu.prof"

profile-mem: ## Run memory profiling
	@echo "Running memory profiling..."
	@go test -memprofile=mem.prof -bench=. $(TEST_PACKAGES)
	@echo "Memory profile saved as mem.prof"

##@ CI/CD

ci: check test build ## Run CI pipeline
	@echo "CI pipeline completed successfully"

cd: release docker-push ## Run CD pipeline
	@echo "CD pipeline completed successfully"

# Include version information
$(BUILD_DIR)/version.txt: 
	@mkdir -p $(BUILD_DIR)
	@echo "Version: $(VERSION)" > $(BUILD_DIR)/version.txt
	@echo "Git Commit: $(GIT_COMMIT)" >> $(BUILD_DIR)/version.txt
	@echo "Build Date: $(BUILD_DATE)" >> $(BUILD_DIR)/version.txt

version: $(BUILD_DIR)/version.txt ## Show version information
	@cat $(BUILD_DIR)/version.txt

# Auto-detect if we're in a Git repository
.ONESHELL:
git-check:
	@if [ ! -d .git ]; then \
		echo "Warning: Not in a Git repository. Version information may be incomplete."; \
	fi

.DEFAULT_GOAL := help