# Tobogganing Documentation Website

This directory contains the complete MkDocs-powered documentation website for Tobogganing, an Open Source Secure Access Service Edge (SASE) solution.

## 🚀 Quick Start

### Development Server (Recommended)

```bash
# Install dependencies
make install

# Start development server with live reload
make serve-dev
```

Visit http://localhost:8000 to view the documentation.

### Docker Development

```bash
# Start development environment
make docker-dev
```

Visit http://localhost:8001 for the development server.

### Production Build

```bash
# Build and run production Docker container
make docker-run
```

Visit http://localhost:8000 for the production server.

## 📁 Project Structure

```
docs-website/
├── mkdocs.yml              # MkDocs configuration
├── requirements.txt        # Python dependencies
├── Dockerfile             # Production Docker image
├── docker-compose.yml     # Docker Compose configuration
├── Makefile              # Build automation
└── docs/                 # Documentation content
    ├── index.md          # Homepage
    ├── stylesheets/      # Custom CSS
    ├── javascripts/      # Custom JavaScript
    └── *.md             # Symbolic links to /docs/*.md
```

## 🛠️ Available Commands

| Command | Description |
|---------|-------------|
| `make help` | Show all available commands |
| `make install` | Install Python dependencies |
| `make serve` | Start local development server |
| `make serve-dev` | Start server with live reload |
| `make build` | Build static documentation |
| `make docker-build` | Build Docker image |
| `make docker-run` | Run production container |
| `make docker-dev` | Start development environment |
| `make clean` | Clean build artifacts |
| `make lint` | Run linting and validation |
| `make test` | Run all tests and validations |

## 🎨 Features

### Theme & Design
- **Material for MkDocs** theme with custom Tobogganing branding
- **Responsive design** optimized for mobile and desktop
- **Dark/light mode** toggle with system preference detection
- **Custom CSS** with brand colors and enhanced styling
- **Interactive elements** with smooth animations

### Navigation & Search
- **Tabbed navigation** with sticky headers
- **Search functionality** with highlighting and suggestions
- **Table of contents** integration with scroll tracking
- **Breadcrumb navigation** for easy orientation

### Content Features
- **Mermaid diagrams** for architecture visualization
- **Code highlighting** with copy-to-clipboard functionality
- **Admonitions** for tips, warnings, and important notes
- **Card layouts** for feature showcasing
- **Tabbed content** for multi-platform instructions

### Development Features
- **Live reload** during development
- **Link checking** and validation
- **SEO optimization** with meta tags and sitemaps
- **Performance optimization** with asset compression

## 📚 Content Organization

The documentation is organized into logical sections:

- **Home**: Overview, quick start, and key features
- **Getting Started**: Installation guides and basic usage
- **Architecture**: Technical deep-dive and system design
- **Administration**: Web portal, monitoring, and management
- **Development**: Contributing guides and API documentation
- **Legal**: Licensing information and legal terms

## 🔧 Customization

### Custom Styling
- Edit `docs/stylesheets/extra.css` for custom styles
- Modify brand colors in CSS variables
- Add new component styles as needed

### Custom JavaScript
- Edit `docs/javascripts/extra.js` for custom functionality
- Add interactive features and enhancements
- Integrate with third-party libraries

### Configuration
- Modify `mkdocs.yml` for site configuration
- Update navigation structure
- Add or remove plugins and extensions

## 🐳 Docker Configuration

### Multi-stage Build
The Dockerfile uses a multi-stage build process:

1. **Builder stage**: Install dependencies and build documentation
2. **Production stage**: Nginx-based lightweight server

### Nginx Configuration
- **Security headers** for enhanced protection
- **Gzip compression** for faster loading
- **Caching rules** for static assets
- **Custom error pages** with branded design
- **Health check endpoint** at `/health`

### Docker Compose
- **Production service**: Optimized for deployment
- **Development service**: Live reload and development tools
- **Volume management** for persistent data
- **Network configuration** for service communication

## 🚀 Deployment Options

### Cloudflare Pages (Recommended)
```bash
# Build static site
make build

# Deploy to Cloudflare Pages
# (Upload the 'site/' directory)
```

### Docker Container
```bash
# Build and deploy Docker image
make docker-build
docker push your-registry/tobogganing-docs:latest
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tobogganing-docs
spec:
  replicas: 2
  selector:
    matchLabels:
      app: tobogganing-docs
  template:
    metadata:
      labels:
        app: tobogganing-docs
    spec:
      containers:
      - name: docs
        image: tobogganing/docs:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "128Mi"
            cpu: "100m"
```

### GitHub Pages
```yaml
# .github/workflows/docs.yml
name: Deploy Documentation
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.12
      - run: pip install -r docs-website/requirements.txt
      - run: cd docs-website && mkdocs gh-deploy --force
```

## 🔍 Quality Assurance

### Automated Validation
- **Configuration validation**: YAML syntax and structure
- **Link checking**: Internal and external link validation
- **Content validation**: Required files and navigation structure
- **Build testing**: Ensure documentation builds successfully

### Performance Optimization
- **Asset compression**: Gzip compression for all text assets
- **Image optimization**: Automatic image compression and format selection
- **Caching strategy**: Browser caching for static assets
- **CDN integration**: Ready for CDN deployment

## 🤝 Contributing

### Adding New Documentation
1. Create or update markdown files in `/docs/`
2. Add symbolic links in `docs-website/docs/`
3. Update navigation in `mkdocs.yml`
4. Test with `make serve-dev`

### Updating Styles
1. Modify `docs/stylesheets/extra.css`
2. Test with live reload
3. Validate with different themes and screen sizes

### Adding Features
1. Update `docs/javascripts/extra.js`
2. Test interactivity and accessibility
3. Ensure mobile compatibility

## 📧 Support

For questions or issues with the documentation website:

- **GitHub Issues**: [Report bugs or feature requests](https://github.com/penguintechinc/tobogganing/issues)
- **Documentation**: This README and inline comments
- **Community**: Join our discussions and contribute improvements

---

Built with ❤️ using [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)