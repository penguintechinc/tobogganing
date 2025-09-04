# Multi-stage Dockerfile for MkDocs Documentation Site
FROM python:3.12-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy MkDocs configuration
COPY mkdocs.yml .

# Copy documentation source
COPY docs/ docs/

# Build the documentation
RUN mkdocs build --strict --verbose

# Production stage with lightweight web server
FROM nginx:alpine

# Install security updates
RUN apk update && apk upgrade && apk add --no-cache \
    curl \
    && rm -rf /var/cache/apk/*

# Copy built documentation from builder stage
COPY --from=builder /app/site /usr/share/nginx/html

# Copy custom nginx configuration
COPY <<EOF /etc/nginx/conf.d/default.conf
server {
    listen 80;
    listen [::]:80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data: https: http:; font-src 'self' https://fonts.gstatic.com;" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/javascript
        application/xml+rss
        application/json;

    # Cache static assets
    location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Handle HTML files
    location ~* \.html$ {
        expires 1h;
        add_header Cache-Control "public, must-revalidate";
    }

    # Main location block
    location / {
        try_files \$uri \$uri/ \$uri.html /index.html;
        
        # Add trailing slash to directories
        if (\$request_uri ~* "^/([^/]+)$") {
            return 301 /\$1/;
        }
    }

    # API endpoints (if any)
    location /api/ {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
    }

    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    # Block access to sensitive files
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    location ~ /(README|CHANGELOG|LICENSE|\.git) {
        deny all;
        access_log off;
        log_not_found off;
    }

    # Custom error pages
    error_page 404 /404.html;
    error_page 500 502 503 504 /50x.html;

    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

# Create custom 404 page
COPY <<EOF /usr/share/nginx/html/404.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Not Found - Tobogganing Documentation</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            text-align: center;
            padding: 50px;
            background: linear-gradient(135deg, #1976d2, #03a9f4);
            color: white;
            margin: 0;
            height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
        }
        h1 {
            font-size: 6rem;
            margin: 0;
            opacity: 0.8;
        }
        h2 {
            font-size: 2rem;
            margin: 20px 0;
        }
        p {
            font-size: 1.2rem;
            margin: 20px 0;
            opacity: 0.9;
        }
        a {
            color: white;
            text-decoration: none;
            background: rgba(255, 255, 255, 0.2);
            padding: 10px 20px;
            border-radius: 25px;
            display: inline-block;
            margin: 10px;
            transition: background 0.3s;
        }
        a:hover {
            background: rgba(255, 255, 255, 0.3);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>404</h1>
        <h2>🛡️ Page Not Found</h2>
        <p>The documentation page you're looking for doesn't exist.</p>
        <p>Let's get you back on track:</p>
        <a href="/">🏠 Home</a>
        <a href="/quickstart/">🚀 Quick Start</a>
        <a href="/api/">📚 API Docs</a>
    </div>
</body>
</html>
EOF

# Set proper permissions
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Expose port
EXPOSE 80

# Labels for metadata
LABEL maintainer="Penguin Technologies Inc <support@penguintech.io>"
LABEL description="Tobogganing Documentation Site - MkDocs with Material Theme"
LABEL version="1.0.0"
LABEL org.opencontainers.image.title="Tobogganing Documentation"
LABEL org.opencontainers.image.description="Complete documentation for Tobogganing SASE solution"
LABEL org.opencontainers.image.url="https://docs.tobogganing.io"
LABEL org.opencontainers.image.source="https://github.com/penguintechinc/tobogganing"
LABEL org.opencontainers.image.vendor="Penguin Technologies Inc"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Start nginx
CMD ["nginx", "-g", "daemon off;"]