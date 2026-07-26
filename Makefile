# Tobogganing - Zero Trust SASE Platform
# Build automation for all services

.PHONY: help all clean build test lint docker deploy setup dev smoke-test
.PHONY: build-hub-api build-hub-router build-hub-webui build-client
.PHONY: test-unit test-integration test-e2e test-hub-api test-hub-router test-hub-webui test-client
.PHONY: lint-hub-api lint-hub-router lint-hub-webui lint-client
.PHONY: docker-build docker-push dev-up dev-down dev-logs dev-restart
.PHONY: deploy-alpha deploy-beta deploy-prod deploy-terraform
.PHONY: helm-lint helm-template seed-mock-data
.PHONY: install-hooks pre-commit-check pre-push-check

VERSION := $(shell cat .version)

# Default target
help: ## Show this help message
	@echo "Tobogganing - Zero Trust SASE Platform"
	@echo "Version: $(VERSION)"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ============================================================
# Setup & Build
# ============================================================

all: clean build test ## Build and test all components

setup: ## Install all dependencies
	@echo "Installing dependencies..."
	@cd services/hub-api && pip install -e ".[dev]" 2>/dev/null || pip install -r requirements.txt
	@cd services/hub-router && go mod download
	@cd services/hub-webui && npm ci
	@cd clients/native && go mod download
	@echo "Dependencies installed"
	@$(MAKE) install-hooks

clean: ## Clean all build artifacts
	@echo "Cleaning build artifacts..."
	@rm -rf build/ dist/ releases/ artifacts/
	@cd services/hub-api && rm -rf __pycache__ .pytest_cache htmlcov/ *.egg-info/ .mypy_cache/
	@cd services/hub-router && rm -rf build/ *.test *.out
	@cd services/hub-webui && rm -rf dist/ node_modules/.cache/ .vite/
	@cd clients/native && rm -rf build/ *.test *.out
	@echo "Clean complete"

build: build-hub-api build-hub-router build-hub-webui build-client ## Build all components

build-hub-api: ## Build Hub API (Quart)
	@echo "Building Hub API..."
	@cd services/hub-api && pip install -e ".[dev]" 2>/dev/null || pip install -r requirements.txt

build-hub-router: ## Build Hub Router (Go)
	@echo "Building Hub Router..."
	@cd services/hub-router && go mod download && CGO_ENABLED=1 go build -o build/hub-router ./proxy
	@cd services/hub-router && go build -o build/healthcheck ./cmd/healthcheck

build-hub-webui: ## Build Hub WebUI (React)
	@echo "Building Hub WebUI..."
	@cd services/hub-webui && npm ci && npm run build

build-client: ## Build Native Client
	@echo "Building Native Client..."
	@cd clients/native && go mod download && go build -o build/tobogganing-client ./cmd

# ============================================================
# Testing
# ============================================================

test: test-hub-api test-hub-router test-hub-webui test-client ## Run all tests

test-unit: test-hub-api test-hub-router test-hub-webui ## Run unit tests only

test-integration: ## Run integration tests
	@echo "Running integration tests..."
	@cd tests/integration && python3 -m pytest -v || true

test-e2e: ## Run end-to-end tests
	@echo "Running e2e tests..."
	@cd tests/e2e && python3 -m pytest -v || true

test-hub-api: ## Test Hub API
	@echo "Testing Hub API..."
	@cd services/hub-api && python3 -m pytest tests/ -v --cov=. || true

test-hub-router: ## Test Hub Router
	@echo "Testing Hub Router..."
	@cd services/hub-router && go test -v -race ./... || true

test-hub-webui: ## Test Hub WebUI
	@echo "Testing Hub WebUI..."
	@cd services/hub-webui && npm test -- --run || true

test-client: ## Test Native Client
	@echo "Testing Native Client..."
	@cd clients/native && go test -v -race ./... || true

smoke-test: ## Run smoke tests (build, start, API health)
	@echo "Running smoke tests..."
	@cd tests/smoke && bash run-smoke-tests.sh || true

seed-mock-data: ## Populate database with test data
	@echo "Seeding mock data..."
	@cd services/hub-api && python3 -m scripts.seed_mock_data || true

# ============================================================
# Linting
# ============================================================

lint: ## Run all linting
	@echo "=== Linting ==="
	@cd services/hub-api && echo "-- flake8 --" && python3 -m flake8 . --max-line-length=120 --exclude=.git,__pycache__,venv,node_modules 2>/dev/null || true
	@cd services/hub-api && echo "-- black --" && python3 -m black --check . 2>/dev/null || true
	@cd services/hub-api && echo "-- isort --" && python3 -m isort --check-only . 2>/dev/null || true
	@cd services/hub-api && echo "-- mypy --" && python3 -m mypy . --ignore-missing-imports 2>/dev/null || true
	@cd services/hub-router && echo "-- golangci-lint --" && golangci-lint run 2>/dev/null || true
	@cd clients/native && echo "-- golangci-lint --" && golangci-lint run 2>/dev/null || true
	@cd services/hub-webui && echo "-- eslint --" && npm run lint 2>/dev/null || true
	@find . -name "Dockerfile*" -not -path "*/.git/*" -exec echo "-- hadolint: {} --" \; -exec hadolint {} \; 2>/dev/null || true
	@find . -name "*.sh" -not -path "*/.git/*" -exec echo "-- shellcheck: {} --" \; -exec shellcheck {} \; 2>/dev/null || true
	@echo "Linting complete"

lint-hub-api: ## Lint Hub API
	@echo "Linting Hub API..."
	@cd services/hub-api && python3 -m flake8 . || true
	@cd services/hub-api && python3 -m black --check . || true
	@cd services/hub-api && python3 -m isort --check-only . || true
	@cd services/hub-api && python3 -m mypy . || true
	@cd services/hub-api && python3 -m bandit -r . -x tests || true

lint-hub-router: ## Lint Hub Router
	@echo "Linting Hub Router..."
	@cd services/hub-router && golangci-lint run || true

lint-hub-webui: ## Lint Hub WebUI
	@echo "Linting Hub WebUI..."
	@cd services/hub-webui && npm run lint || true

lint-client: ## Lint Native Client
	@echo "Linting Native Client..."
	@cd clients/native && golangci-lint run || true

# ============================================================
# Docker
# ============================================================

docker: docker-build ## Build all Docker images

docker-build: ## Build all Docker images
	@echo "Building Docker images..."
	@docker build -t tobogganing/hub-api:latest ./services/hub-api
	@docker build -t tobogganing/hub-router:latest ./services/hub-router
	@docker build -t tobogganing/hub-webui:latest ./services/hub-webui
	@docker build -t tobogganing/client:latest ./clients/docker

docker-push: ## Push Docker images to registry
	@echo "Pushing Docker images..."
	@docker push tobogganing/hub-api:latest
	@docker push tobogganing/hub-router:latest
	@docker push tobogganing/hub-webui:latest
	@docker push tobogganing/client:latest

# ============================================================
# Development
# ============================================================

dev: dev-up ## Start development environment

dev-up: ## Start development environment
	@echo "Starting development environment..."
	@docker compose -f docker-compose.dev.yml up -d
	@echo "Development environment started"
	@echo "  Hub API:          http://localhost:8080"
	@echo "  Hub WebUI:        http://localhost:3000"
	@echo "  Redis Commander:  http://localhost:8081"
	@echo "  Adminer:          http://localhost:8082"

dev-down: ## Stop development environment
	@echo "Stopping development environment..."
	@docker compose -f docker-compose.dev.yml down
	@echo "Development environment stopped"

dev-logs: ## Show development environment logs
	@docker compose -f docker-compose.dev.yml logs -f

dev-restart: dev-down dev-up ## Restart development environment

# ============================================================
# Deployment
# ============================================================

deploy-alpha: ## Deploy to alpha (local K8s)
	@echo "Deploying to alpha..."
	@kubectl apply -k k8s/kustomize/overlays/alpha

deploy-beta: ## Deploy to beta cluster
	@echo "Deploying to beta..."
	@kubectl apply -k k8s/kustomize/overlays/beta

deploy-prod: ## Deploy to production
	@echo "Deploying to production..."
	@kubectl apply -k k8s/kustomize/overlays/prod

deploy-terraform: ## Deploy infrastructure with Terraform
	@echo "Deploying with Terraform..."
	@cd deploy/terraform && terraform init && terraform plan && terraform apply

helm-lint: ## Lint Helm chart
	@helm lint k8s/helm/tobogganing

helm-template: ## Dry-run Helm template rendering
	@helm template tobogganing k8s/helm/tobogganing

# ============================================================
# Security & Quality
# ============================================================

security-scan: ## Run security scans
	@echo "Running security scans..."
	@cd services/hub-api && python3 -m bandit -r . -x tests || true
	@cd services/hub-api && pip-audit || true
	@cd services/hub-router && gosec ./... || true
	@cd services/hub-webui && npm audit || true
	@docker run --rm -v $(PWD):/workspace aquasec/trivy fs /workspace || true

qa: lint test security-scan ## Run full quality assurance suite

ci: clean setup lint test docker-build ## Simulate CI pipeline locally

# ============================================================
# Utilities
# ============================================================

version: ## Show version information
	@echo "Tobogganing Version Information:"
	@echo "  Version: $(VERSION)"
	@echo "  Git Commit: $(shell git rev-parse --short HEAD)"
	@echo "  Build Date: $(shell date -u '+%Y-%m-%d %H:%M:%S UTC')"
	@echo ""
	@echo "Component Versions:"
	@cd services/hub-api && python3 --version 2>&1 | sed 's/^/  Hub API: /' || true
	@cd services/hub-router && go version 2>&1 | sed 's/^/  Hub Router: /' || true
	@cd services/hub-webui && node --version 2>&1 | sed 's/^/  Hub WebUI: Node /' || true

health: ## Check system health
	@echo "Checking system health..."
	@curl -sf http://localhost:8080/healthz && echo " Hub API: healthy" || echo " Hub API: not responding"
	@curl -sf http://localhost:9090/health && echo " Hub Router: healthy" || echo " Hub Router: not responding"
	@curl -sf http://localhost:3000 > /dev/null && echo " Hub WebUI: healthy" || echo " Hub WebUI: not responding"

certs-generate: ## Generate development certificates
	@echo "Generating development certificates..."
	@mkdir -p certs
	@openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout certs/dev.key -out certs/dev.crt \
		-subj "/C=US/ST=Development/L=Local/O=Tobogganing/CN=localhost"
	@echo "Development certificates generated in ./certs/"

db-migrate: ## Run database migrations
	@echo "Running database migrations..."
	@cd services/hub-api && python3 -m scripts.migrate

db-reset: ## Reset development database
	@echo "Resetting development database..."
	@rm -f services/hub-api/data/tobogganing.db
	@cd services/hub-api && python3 -m scripts.init_db

install: build ## Install Tobogganing client locally
	@echo "Installing Tobogganing..."
	@sudo cp clients/native/build/tobogganing-client /usr/local/bin/
	@echo "Installation complete"
	@echo "  Run 'tobogganing-client --help' to get started"

uninstall: ## Uninstall Tobogganing client
	@echo "Uninstalling Tobogganing..."
	@sudo rm -f /usr/local/bin/tobogganing-client
	@echo "Uninstallation complete"

env-info: ## Show environment information
	@echo "Environment Information:"
	@echo "  OS: $(shell uname -s -r)"
	@echo "  Architecture: $(shell uname -m)"
	@echo "  Docker: $(shell docker --version 2>/dev/null || echo 'Not installed')"
	@echo "  Kubernetes: $(shell kubectl version --client --short 2>/dev/null || echo 'Not installed')"
	@echo "  Terraform: $(shell terraform --version 2>/dev/null | head -1 || echo 'Not installed')"
	@echo "  Python: $(shell python3 --version 2>/dev/null || echo 'Not installed')"
	@echo "  Go: $(shell go version 2>/dev/null || echo 'Not installed')"
	@echo "  Node.js: $(shell node --version 2>/dev/null || echo 'Not installed')"

troubleshoot: ## Run troubleshooting checks
	@echo "Running troubleshooting checks..."
	@echo "1. Checking prerequisites..."
	@make env-info
	@echo ""
	@echo "2. Checking service health..."
	@make health
	@echo ""
	@echo "3. Checking Docker containers..."
	@docker ps -a | grep tobogganing || echo "No Tobogganing containers found"
	@echo ""
	@echo "4. Checking disk space..."
	@df -h . | head -2
	@echo ""
	@echo "Troubleshooting complete"

stats: ## Show project statistics
	@echo "Tobogganing Project Statistics:"
	@echo "  Total files: $(shell find . -type f -not -path './.git/*' -not -path '*/node_modules/*' | wc -l)"
	@echo "  Lines of code:"
	@echo "    Python: $(shell find services/hub-api -name '*.py' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $$1}' || echo 0)"
	@echo "    Go: $(shell find services/hub-router clients/native -name '*.go' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $$1}' || echo 0)"
	@echo "    TypeScript: $(shell find services/hub-webui/src -name '*.tsx' -o -name '*.ts' 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $$1}' || echo 0)"
	@echo "  Git commits: $(shell git rev-list --count HEAD 2>/dev/null || echo 0)"

test-functional: ## Run functional tests (APIs, pages, tabs, modals, buttons)
	@echo "No functional tests defined"

test-security: ## Run security tests (gosec, bandit, npm audit, trivy)
	@echo "=== Security Scans ==="
	@cd services/hub-api && echo "-- bandit --" && python3 -m bandit -r . -x tests 2>/dev/null || true
	@echo "-- pip-audit --" && find services/hub-api -name "requirements.txt" -exec pip-audit -r {} 2>/dev/null \; || true
	@cd services/hub-router && echo "-- gosec --" && gosec ./... 2>/dev/null || true
	@cd clients/native && echo "-- gosec --" && gosec ./... 2>/dev/null || true
	@cd services/hub-router && echo "-- govulncheck --" && govulncheck ./... 2>/dev/null || true
	@cd clients/native && echo "-- govulncheck --" && govulncheck ./... 2>/dev/null || true
	@cd services/hub-webui && echo "-- npm audit --" && npm audit 2>/dev/null || true
	@echo "-- gitleaks --" && gitleaks detect --source . --no-git 2>/dev/null || true
	@echo "Security scans complete"

install-hooks: ## Install pre-commit and pre-push git hooks from scripts/hooks/
	@echo "Installing git hooks..."
	@ln -sf "$(PWD)/scripts/hooks/pre-commit" "$(PWD)/.git/hooks/pre-commit"
	@ln -sf "$(PWD)/scripts/hooks/pre-push"   "$(PWD)/.git/hooks/pre-push"
	@chmod +x scripts/hooks/pre-commit scripts/hooks/pre-push
	@echo "✓ pre-commit → .git/hooks/pre-commit"
	@echo "✓ pre-push   → .git/hooks/pre-push"

pre-commit-check: ## Run pre-commit checks manually (same as git pre-commit hook)
	@scripts/hooks/pre-commit

pre-push-check: ## Run pre-push checks manually (same as git pre-push hook)
	@scripts/hooks/pre-push

pre-commit: pre-commit-check ## Alias for pre-commit-check

deploy-dev: ## Deploy to dev environment (alias to deploy-alpha)
	@$(MAKE) deploy-alpha
