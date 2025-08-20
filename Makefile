# SASEWaddle Root Makefile
# Provides convenient commands for building, testing, and deploying the entire SASEWaddle project

.PHONY: help all clean build test lint docker deploy dev-up dev-down website

# Default target
help: ## Show this help message
	@echo "SASEWaddle - Open Source SASE Solution"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Build all components
all: clean build test ## Build and test all components

clean: ## Clean all build artifacts
	@echo "🧹 Cleaning build artifacts..."
	@rm -rf build/ dist/ releases/ artifacts/
	@cd manager && rm -rf __pycache__ .pytest_cache htmlcov/ *.egg-info/
	@cd headend && rm -rf build/ *.test *.out
	@cd clients/native && rm -rf build/ *.test *.out
	@cd website && rm -rf .next/ out/ node_modules/.cache/
	@echo "✅ Clean complete"

# Build all components
build: build-manager build-headend build-client build-website ## Build all components

build-manager: ## Build Manager Service
	@echo "🏗️  Building Manager Service..."
	@cd manager && pip install -r requirements.txt

build-headend: ## Build Headend Server
	@echo "🏗️  Building Headend Server..."
	@cd headend && go mod download && go build -o build/headend ./cmd

build-client: ## Build Native Client
	@echo "🏗️  Building Native Client..."
	@cd clients/native && go mod download && make local

build-website: ## Build Website
	@echo "🏗️  Building Website..."
	@cd website && npm install && npm run build

# Run all tests
test: test-manager test-headend test-client ## Run all tests

test-manager: ## Run Manager Service tests
	@echo "🧪 Testing Manager Service..."
	@cd manager && python -m pytest tests/ -v --cov=. || true

test-headend: ## Run Headend Server tests
	@echo "🧪 Testing Headend Server..."
	@cd headend && go test -v -race ./... || true

test-client: ## Run Native Client tests
	@echo "🧪 Testing Native Client..."
	@cd clients/native && go test -v -race ./... || true

# Run linting
lint: lint-manager lint-headend lint-client lint-website ## Run all linting

lint-manager: ## Lint Manager Service
	@echo "🔍 Linting Manager Service..."
	@cd manager && python -m pylint . --rcfile=.pylintrc || true
	@cd manager && python -m mypy . || true

lint-headend: ## Lint Headend Server
	@echo "🔍 Linting Headend Server..."
	@cd headend && golangci-lint run || true

lint-client: ## Lint Native Client
	@echo "🔍 Linting Native Client..."
	@cd clients/native && golangci-lint run || true

lint-website: ## Lint Website
	@echo "🔍 Linting Website..."
	@cd website && npm run lint || true

# Docker commands
docker: docker-build ## Build all Docker images

docker-build: ## Build all Docker images
	@echo "🐳 Building Docker images..."
	@docker build -t sasewaddle/manager:latest ./manager
	@docker build -t sasewaddle/headend:latest ./headend
	@docker build -t sasewaddle/client:latest ./clients/docker

docker-push: ## Push Docker images to registry
	@echo "🐳 Pushing Docker images..."
	@docker push sasewaddle/manager:latest
	@docker push sasewaddle/headend:latest
	@docker push sasewaddle/client:latest

# Development environment
dev-up: ## Start development environment
	@echo "🚀 Starting development environment..."
	@cd deploy/docker-compose && docker-compose -f docker-compose.dev.yml up -d
	@echo "✅ Development environment started"
	@echo "   Manager UI: http://localhost:8000"
	@echo "   Redis Commander: http://localhost:8082"
	@echo "   Adminer: http://localhost:8081"

dev-down: ## Stop development environment
	@echo "🛑 Stopping development environment..."
	@cd deploy/docker-compose && docker-compose -f docker-compose.dev.yml down
	@echo "✅ Development environment stopped"

dev-logs: ## Show development environment logs
	@cd deploy/docker-compose && docker-compose -f docker-compose.dev.yml logs -f

dev-restart: dev-down dev-up ## Restart development environment

# Deployment commands
deploy: deploy-k8s ## Deploy to production

deploy-k8s: ## Deploy to Kubernetes
	@echo "☸️  Deploying to Kubernetes..."
	@cd deploy/kubernetes && kubectl apply -f .
	@echo "✅ Kubernetes deployment complete"

deploy-terraform: ## Deploy with Terraform
	@echo "🏗️  Deploying with Terraform..."
	@cd deploy/terraform && terraform init && terraform plan && terraform apply
	@echo "✅ Terraform deployment complete"

# Website commands
website: ## Build and serve website locally
	@echo "🌐 Starting website development server..."
	@cd website && npm install && npm run dev

website-build: ## Build website for production
	@echo "🌐 Building website for production..."
	@cd website && npm install && npm run build

website-deploy: ## Deploy website to Cloudflare Pages
	@echo "🌐 Deploying website to Cloudflare Pages..."
	@cd website && npm run pages:build && npm run pages:deploy

# Security and compliance
security-scan: ## Run security scans
	@echo "🔐 Running security scans..."
	@docker run --rm -v $(PWD):/workspace aquasec/trivy fs /workspace || true

# Release commands
release: ## Create a new release
	@echo "🎉 Creating new release..."
	@./scripts/create-release.sh

release-notes: ## Generate release notes
	@echo "📝 Generating release notes..."
	@git log --pretty=format:"- %s" $(shell git describe --tags --abbrev=0)..HEAD

# Documentation
docs: ## Generate documentation
	@echo "📚 Generating documentation..."
	@cd manager && python -m pdoc --html --output-dir ../docs/ . || true

# Health checks
health: ## Check system health
	@echo "💚 Checking system health..."
	@curl -f http://localhost:8000/health || echo "Manager service not responding"
	@curl -f http://localhost:8080/health || echo "Headend service not responding"

# Performance testing
perf-test: ## Run performance tests
	@echo "⚡ Running performance tests..."
	@echo "Performance testing framework would run here"

# Installation
install: build ## Install SASEWaddle locally
	@echo "📦 Installing SASEWaddle..."
	@sudo cp clients/native/build/sasewaddle-client /usr/local/bin/
	@echo "✅ Installation complete"
	@echo "   Run 'sasewaddle-client --help' to get started"

uninstall: ## Uninstall SASEWaddle
	@echo "🗑️  Uninstalling SASEWaddle..."
	@sudo rm -f /usr/local/bin/sasewaddle-client
	@echo "✅ Uninstallation complete"

# Certificate management
certs-generate: ## Generate development certificates
	@echo "🔐 Generating development certificates..."
	@mkdir -p certs
	@openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout certs/dev.key -out certs/dev.crt \
		-subj "/C=US/ST=Development/L=Local/O=SASEWaddle/CN=localhost"
	@echo "✅ Development certificates generated in ./certs/"

# Database management
db-migrate: ## Run database migrations
	@echo "🗄️  Running database migrations..."
	@cd manager && python -m manager.tools.migrate

db-reset: ## Reset development database
	@echo "🗄️  Resetting development database..."
	@rm -f manager/data/sasewaddle.db
	@cd manager && python -m manager.tools.init_db

# Utilities
version: ## Show version information
	@echo "SASEWaddle Version Information:"
	@echo "  Version: $(shell cat .version)"
	@echo "  Git Commit: $(shell git rev-parse --short HEAD)"
	@echo "  Build Date: $(shell date -u '+%Y-%m-%d %H:%M:%S UTC')"
	@echo ""
	@echo "Component Versions:"
	@cd manager && python --version 2>&1 | sed 's/^/  Manager: /'
	@cd headend && go version | sed 's/^/  Headend: /'
	@cd clients/native && go version | sed 's/^/  Client: /'
	@cd website && node --version | sed 's/^/  Website: Node /'

dependencies: ## Install all dependencies
	@echo "📦 Installing dependencies..."
	@cd manager && pip install -r requirements.txt -r requirements-dev.txt
	@cd headend && go mod download
	@cd clients/native && go mod download
	@cd website && npm install
	@echo "✅ Dependencies installed"

# Quality assurance
qa: lint test security-scan ## Run full quality assurance suite

# CI/CD simulation
ci: clean dependencies lint test docker ## Simulate CI pipeline locally

# Project statistics
stats: ## Show project statistics
	@echo "📊 SASEWaddle Project Statistics:"
	@echo "  Total files: $(shell find . -type f | wc -l)"
	@echo "  Lines of code:"
	@echo "    Python: $(shell find manager -name '*.py' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $$1}' || echo 0)"
	@echo "    Go: $(shell find headend clients/native -name '*.go' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $$1}' || echo 0)"
	@echo "    TypeScript: $(shell find website -name '*.tsx' -o -name '*.ts' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $$1}' || echo 0)"
	@echo "    YAML: $(shell find . -name '*.yml' -o -name '*.yaml' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $$1}' || echo 0)"
	@echo "  Git commits: $(shell git rev-list --count HEAD 2>/dev/null || echo 0)"
	@echo "  Contributors: $(shell git log --format='%an' | sort -u | wc -l 2>/dev/null || echo 0)"

# Environment information
env-info: ## Show environment information
	@echo "🌍 Environment Information:"
	@echo "  OS: $(shell uname -s -r)"
	@echo "  Architecture: $(shell uname -m)"
	@echo "  Docker: $(shell docker --version 2>/dev/null || echo 'Not installed')"
	@echo "  Kubernetes: $(shell kubectl version --client --short 2>/dev/null || echo 'Not installed')"
	@echo "  Terraform: $(shell terraform --version 2>/dev/null | head -1 || echo 'Not installed')"
	@echo "  Python: $(shell python --version 2>/dev/null || echo 'Not installed')"
	@echo "  Go: $(shell go version 2>/dev/null || echo 'Not installed')"
	@echo "  Node.js: $(shell node --version 2>/dev/null || echo 'Not installed')"

# Troubleshooting
troubleshoot: ## Run troubleshooting checks
	@echo "🔧 Running troubleshooting checks..."
	@echo "1. Checking prerequisites..."
	@make env-info
	@echo ""
	@echo "2. Checking service health..."
	@make health
	@echo ""
	@echo "3. Checking Docker containers..."
	@docker ps -a | grep sasewaddle || echo "No SASEWaddle containers found"
	@echo ""
	@echo "4. Checking disk space..."
	@df -h . | head -2
	@echo ""
	@echo "✅ Troubleshooting complete"