# Stage 1: Builder
FROM node:26-bookworm-slim@sha256:607728e8751f69809c871e2cfa65d645f51ffacb5a0e9fc60f4cb7404ee5c16a AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Runtime
FROM node:26-bookworm-slim@sha256:607728e8751f69809c871e2cfa65d645f51ffacb5a0e9fc60f4cb7404ee5c16a
RUN groupadd -r appuser && useradd -r -g appuser appuser
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/server.js ./server.js
COPY --from=builder /app/node_modules ./node_modules
RUN npm ci --omit=dev || true
USER appuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/healthz', (r) => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"
CMD ["node", "server.js"]
