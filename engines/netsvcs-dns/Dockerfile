# Stage 1: Builder
FROM python:3.13-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7 AS builder

WORKDIR /build

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

# Copy requirements and compile/install dependencies
COPY requirements.txt .
RUN uv pip install --system --require-hashes -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (service directory)
COPY . .

# Copy proto definitions from repo root
COPY proto/ /app/proto/

# Set ownership to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add repo root to Python path for proto imports
ENV PYTHONPATH=/app:$PYTHONPATH

# Health check using native Python (no curl/wget)
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python3 -c "import http.client; conn = http.client.HTTPConnection('localhost', 8080, timeout=2); conn.request('GET', '/healthz'); res = conn.getresponse(); exit(0 if res.status == 200 else 1)"

# Run the application
ENTRYPOINT ["python3", "-m", "app.main"]
