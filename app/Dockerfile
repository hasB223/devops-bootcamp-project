# ==============================================================================
# Stage 1: Build static assets
# ==============================================================================
# Base images are digest-pinned so a rebuild resolves the exact same image.
# The pinned digest is the multi-arch manifest-list digest, which preserves
# normal platform resolution if builds ever go multi-platform (the workflow is
# amd64-only today). Dependabot's docker ecosystem revises tag and digest
# together; see .github/dependabot.yml.
FROM node:26-alpine@sha256:c6ad9e9c1d80f6eb607c26b4b0a132ff7a2344fad1c78ea3baa2a7d4c8de6d94 AS builder

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
# `alpine-slim` is the official minimal nginx runtime: same mainline release
# channel as `alpine`, but without the extra packages layered on top. That
# smaller surface is what makes it pass the CI HIGH/CRITICAL image gate with no
# package installation of any kind — the `alpine` and `stable-alpine` variants
# both ship util-linux/libuuid, which currently carries 7 fixable
# HIGH/CRITICAL advisories.
#
# What the pinning actually gives us, stated narrowly:
#   - The digest fixes the contents of the selected base image, so an upstream
#     tag move cannot silently change this input.
#   - This stage performs no `apk` operations, so live Alpine-repository
#     resolution is eliminated from the runtime stage.
# Do not add `apk add` or `apk upgrade` here: that would reintroduce
# repository-time resolution as a build input.
#
# What it does NOT give us: this is not a guarantee that two separate builds
# produce byte-identical images. PR CI scans a *candidate* image built from the
# proposed source and this Dockerfile; the deployment workflow rebuilds after
# merge, so artifact identity between those two builds is not guaranteed.
# Guaranteeing that the scanned artifact is exactly the deployed artifact would
# require build-once-and-promote (build, scan, push, then deploy that same
# digest), which is outside this change's scope.
#
# Patching model: security updates arrive by advancing this digest (Dependabot
# `docker`, weekly, revises tag and digest together), not by mutating packages
# at build time.
FROM nginx:alpine-slim@sha256:f45171d36c76a8b2f5ef97108a3a8a2294248a6578a0a180edc2d78f7d2edc26

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose standard HTTP port
EXPOSE 80

# Health check to ensure nginx is serving requests
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost:80/ || exit 1

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]
