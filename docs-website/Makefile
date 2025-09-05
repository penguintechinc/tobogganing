# Makefile for Tobogganing Documentation

.PHONY: help install build serve serve-dev clean docker-build docker-run docker-dev lint deploy

# Default target
help: ## Show this help message
	@echo "Tobogganing Documentation Build System"
	@echo "======================================"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	@echo "🔧 Installing dependencies..."
	pip install -r requirements.txt

build: ## Build the documentation site
	@echo "🏗️  Building documentation..."
	mkdocs build --strict --verbose

serve: ## Serve the documentation locally
	@echo "🌐 Starting local server..."
	mkdocs serve --dev-addr=127.0.0.1:8000

serve-dev: ## Serve with live reload and verbose output
	@echo "🔄 Starting development server with live reload..."
	mkdocs serve --dev-addr=127.0.0.1:8000 --livereload --verbose

clean: ## Clean build artifacts
	@echo "🧹 Cleaning build artifacts..."
	rm -rf site/
	rm -rf .cache/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +

# Docker targets
docker-build: ## Build Docker image
	@echo "🐳 Building Docker image..."
	docker build -t tobogganing/docs:latest .

docker-run: docker-build ## Build and run Docker container
	@echo "🚀 Starting Docker container..."
	docker run -d \
		--name tobogganing-docs \
		-p 8000:80 \
		--restart unless-stopped \
		tobogganing/docs:latest
	@echo "📖 Documentation available at http://localhost:8000"

docker-dev: ## Start development environment with Docker Compose
	@echo "🔄 Starting development environment..."
	docker-compose --profile dev up -d docs-dev
	@echo "📖 Development server available at http://localhost:8001"

docker-prod: ## Start production environment with Docker Compose
	@echo "🚀 Starting production environment..."
	docker-compose up -d docs
	@echo "📖 Production server available at http://localhost:8000"

docker-stop: ## Stop all Docker containers
	@echo "🛑 Stopping Docker containers..."
	docker-compose down
	-docker stop tobogganing-docs
	-docker rm tobogganing-docs

docker-logs: ## View Docker container logs
	@echo "📋 Docker container logs:"
	docker-compose logs -f

# Quality assurance
lint: ## Run linting and validation
	@echo "🔍 Running linting..."
	@echo "Checking MkDocs configuration..."
	mkdocs build --strict --quiet
	@echo "Checking for broken links..."
	@if command -v linkchecker >/dev/null 2>&1; then \
		mkdocs serve --dev-addr=127.0.0.1:8000 & \
		SERVER_PID=$$!; \
		sleep 5; \
		linkchecker http://127.0.0.1:8000; \
		kill $$SERVER_PID; \
	else \
		echo "⚠️  linkchecker not installed, skipping link validation"; \
	fi

validate: ## Validate documentation structure
	@echo "✅ Validating documentation structure..."
	@./validate.py

# Deployment targets
deploy-staging: ## Deploy to staging environment
	@echo "🚀 Deploying to staging..."
	@echo "This would deploy to your staging environment"

deploy-prod: ## Deploy to production environment
	@echo "🚀 Deploying to production..."
	@echo "This would deploy to your production environment"

# Development helpers
new-page: ## Create a new documentation page (usage: make new-page PAGE=filename)
	@if [ -z "$(PAGE)" ]; then \
		echo "❌ Usage: make new-page PAGE=filename"; \
		exit 1; \
	fi
	@echo "📄 Creating new page: $(PAGE).md"
	@echo "# $(PAGE)" > docs/$(PAGE).md
	@echo "" >> docs/$(PAGE).md
	@echo "TODO: Add content for $(PAGE)" >> docs/$(PAGE).md
	@echo "✅ Created docs/$(PAGE).md"
	@echo "💡 Don't forget to add it to mkdocs.yml navigation!"

update-deps: ## Update Python dependencies
	@echo "🔄 Updating dependencies..."
	pip install --upgrade -r requirements.txt
	pip freeze > requirements.txt
	@echo "✅ Dependencies updated"

# Testing
test: lint validate ## Run all tests and validations
	@echo "🧪 Running all tests..."
	@echo "✅ All tests passed!"

# Info
info: ## Show project information
	@echo "Tobogganing Documentation"
	@echo "========================"
	@echo ""
	@echo "Project Structure:"
	@find . -type f -name "*.md" -o -name "*.yml" -o -name "*.yaml" -o -name "*.py" | head -20
	@echo ""
	@echo "Quick Commands:"
	@echo "  Development: make serve-dev"
	@echo "  Production:  make docker-run"
	@echo "  Validate:    make test"