# ==============================================================================
# Stage 1: Build static assets
# ==============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Cache dependency installation
COPY package*.json ./
RUN npm clean-install

# Copy source and build static bundle into dist/
COPY . .
RUN npm run build

# ==============================================================================
# Stage 2: Minimal static runtime
# ==============================================================================
FROM nginx:alpine

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose standard HTTP port
EXPOSE 80

# Health check to ensure nginx is serving requests
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost:80/ || exit 1

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]
