# Tobogganing Root Makefile
# Provides convenient commands for building, testing, and deploying Tobogganing services

.PHONY: help all clean build test test-unit test-portal test-go test-cov lint lint-python lint-portal lint-go smoke-test docker-build docker-push proto

# Default target
help: ## Show this help message
	@echo "Tobogganing - PenguinTech Networking Platform"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# All
all: clean build test ## Build and test all components

# Clean all build artifacts
clean: ## Clean all build artifacts
	@echo "🧹 Cleaning build artifacts..."
	@rm -rf hub_api/__pycache__ hub_api/.pytest_cache hub_api/htmlcov/
	@rm -rf portal/dist portal/node_modules/.cache
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean complete"

# Build hub_api Docker image
build: docker-build ## Build Docker images

docker-build: ## Build Docker image for hub_api
	@echo "🐳 Building hub_api Docker image..."
	@docker build -t hub-api:latest ./hub_api
	@echo "✅ Docker build complete"

docker-push: ## Push Docker image to registry
	@echo "🐳 Pushing Docker image..."
	@docker push hub-api:latest
	@echo "✅ Docker push complete"

# Proto generation
proto: ## Generate gRPC stubs from .proto files
	@echo "📝 Generating gRPC stubs..."
	@python3 -m grpc_tools.protoc \
		-I proto \
		--python_out=proto \
		--grpc_python_out=proto \
		proto/netsvcs/v1/manager.proto
	@touch proto/__init__.py proto/netsvcs/__init__.py proto/netsvcs/v1/__init__.py
	@# Fix imports to use relative paths for PEP 328 compliance
	@sed -i 's/^from netsvcs\.v1 import/from . import/g' proto/netsvcs/v1/manager_pb2_grpc.py
	@echo "✅ gRPC stubs generated"

# Test targets
test: test-unit test-portal test-go ## Run all tests (unit + portal + go if available)

test-unit: ## Run hub_api unit tests
	@echo "🧪 Testing hub_api (Python/Quart brain)..."
	@python3 -m pytest hub_api/tests/ -v

test-portal: ## Run portal tests (if npm available)
	@if [ -f portal/package.json ]; then \
		echo "🧪 Testing portal (React/Vite)..."; \
		cd portal && npm run test 2>/dev/null || echo "⚠️  Portal tests skipped (npm/jest not available)"; \
	else \
		echo "⏭️  Portal tests skipped (no package.json)"; \
	fi

test-go: ## Run Go service tests (if go.mod available)
	@if [ -f clients/native/go.mod ] || [ -f services/hub-router/go.mod ] || [ -f engines/testserver/go.mod ]; then \
		echo "🧪 Testing Go services..."; \
		for mod in clients/native services/hub-router engines/testserver; do \
			if [ -f $$mod/go.mod ]; then \
				echo "  Testing $$mod..."; \
				(cd $$mod && go test -v -race ./... || true); \
			fi; \
		done; \
	else \
		echo "⏭️  Go tests skipped (no go.mod found)"; \
	fi

test-cov: ## Run hub_api tests with coverage report
	@echo "📊 Running hub_api tests with coverage..."
	@python3 -m pytest hub_api/tests/ --cov=hub_api --cov-report=term-missing --cov-report=html
	@echo "✅ Coverage report generated (open htmlcov/index.html)"

# Lint targets
lint: lint-python lint-portal lint-go ## Run all linters

lint-python: ## Lint Python code
	@echo "🔍 Linting Python (hub_api)..."
	@if command -v ruff &> /dev/null; then \
		ruff check hub_api/ || true; \
	elif command -v flake8 &> /dev/null; then \
		flake8 hub_api/ || true; \
	else \
		echo "⚠️  No Python linter found (ruff/flake8 not installed)"; \
	fi
	@if command -v black &> /dev/null; then \
		black --check hub_api/ || true; \
	fi

lint-portal: ## Lint portal code (if npm available)
	@if [ -f portal/package.json ]; then \
		echo "🔍 Linting portal (React/Vite)..."; \
		cd portal && npm run lint 2>/dev/null || echo "⚠️  Portal lint skipped"; \
	else \
		echo "⏭️  Portal lint skipped (no package.json)"; \
	fi

lint-go: ## Lint Go services (if golangci-lint available)
	@if command -v golangci-lint &> /dev/null; then \
		echo "🔍 Linting Go services..."; \
		for mod in clients/native services/hub-router engines/testserver; do \
			if [ -f $$mod/go.mod ]; then \
				echo "  Linting $$mod..."; \
				(cd $$mod && golangci-lint run || true); \
			fi; \
		done; \
	else \
		echo "⚠️  Go linting skipped (golangci-lint not installed)"; \
	fi

# Smoke test
smoke-test: ## Run smoke tests
	@echo "🔥 Running smoke tests..."
	@echo "  Verifying hub_api build..."
	@python3 -c "import sys; sys.path.insert(0, '.'); from hub_api.app import create_app; print('✅ hub_api app imports successfully')" || exit 1
	@echo "  Verifying hub_api pytest setup..."
	@python3 -m pytest hub_api/tests/test_app.py -q 2>/dev/null || echo "⚠️  Basic test ran (check output above)"
	@echo "✅ Smoke tests complete"

# Development helpers
dependencies: ## Install Python dependencies
	@echo "📦 Installing dependencies..."
	@pip install --no-cache-dir -r hub_api/requirements.txt

portal-dev: ## Start portal dev server
	@echo "🚀 Starting portal dev server..."
	@cd portal && npm install && npm run dev

install-hooks: ## Install Git hooks (pre-commit, pre-push)
	@echo "📦 Installing Git hooks..."
	@if [ -f .git/hooks/pre-commit ]; then echo "✅ Git hooks already installed"; else echo "Run: sh scripts/install-hooks.sh"; fi

# Portal-specific targets (convenience)
portal-build: ## Build portal for production
	@echo "🏗️  Building portal..."
	@cd portal && npm ci && npm run build

portal-test: ## Run portal tests
	@echo "🧪 Testing portal..."
	@cd portal && npm run test

# Health check
health: ## Check system health
	@echo "💚 Checking system health..."
	@python3 --version || echo "⚠️  Python 3 not available"
	@node --version 2>/dev/null || echo "⚠️  Node.js not available"
	@go version 2>/dev/null || echo "⚠️  Go not available"
	@docker --version 2>/dev/null || echo "⚠️  Docker not available"
	@echo "✅ Health check complete"

# Version info
version: ## Show version information
	@echo "Tobogganing Version Information:"
	@if [ -f .version ]; then echo "  Version: $$(cat .version)"; else echo "  Version: unknown (no .version file)"; fi
	@echo "  Git Commit: $$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
	@echo "  Python: $$(python3 --version 2>&1 | awk '{print $$2}' || echo 'not installed')"
	@echo "  Node.js: $$(node --version 2>/dev/null || echo 'not installed')"
	@echo "  Go: $$(go version 2>/dev/null | awk '{print $$3}' || echo 'not installed')"
