# Docker Application Containerization

This document describes the containerization of the web application for the DevOps capstone project, packaged using a multi-stage Docker build and verified locally with Docker Compose.

---

## Purpose

This layer owns the application packaging and container runtime:

- Bundles the customizable Three.js ship microsite into a production-grade OCI container.
- Implements a two-stage build to decouple the Node build toolchain from the minimal static Nginx runtime.
- Exposes standard HTTP port 80 with an automated container healthcheck.
- Defines local orchestration via Docker Compose for rapid testing and verification.
- Establishes tagging and push procedures for the private AWS ECR registry.

---

## Files

All application and container assets reside in `app/`:

```text
app/
├── Dockerfile          # Multi-stage container recipe (node:20-alpine -> nginx:alpine)
├── compose.yaml        # Local service definition, port mapping, and health check
├── .dockerignore       # Build context filters (excludes node_modules, dist, git)
├── package.json        # Dependencies and build scripts (vite, three.js)
├── package-lock.json   # Deterministic npm lockfile
├── vite.config.js      # Vite build configuration
├── index.html          # HTML entry point
├── public/             # Static public assets
└── src/                # Application source code
```

---

## Inputs

| Parameter | Value / Default | Description |
| :--- | :--- | :--- |
| **Builder Base Image** | `node:20-alpine` | Lightweight Node.js build environment |
| **Runtime Base Image** | `nginx:alpine` | Minimal static web server |
| **Container Port** | `80` | Internal HTTP listening port |
| **Host Port Mapping** | `80:80` | Local development exposure |
| **ECR Repository URI** | `<ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/devops-bootcamp/final-project-hasb` | Destination registry in AWS |
| **Image Tags** | `latest`, `<git-short-sha>` | Canonical rolling and immutable git tags |

---

## Steps

### 1. Build the Container Image Locally

From the repository root, build the multi-stage container image:

```bash
docker build -t devops-bootcamp-app:local app/
```

Verify that the final image size is minimal (~26 MB):

```bash
docker images devops-bootcamp-app:local
```

### 2. Run Locally with Docker Compose

Launch the container in detached mode:

```bash
docker compose -f app/compose.yaml up --build -d
```

Confirm container status and health check:

```bash
docker compose -f app/compose.yaml ps
```

### 3. Test HTTP Response

Send an HTTP request to verify Nginx serves the web application:

```bash
curl -I http://localhost:80
```

Expected header response:
```text
HTTP/1.1 200 OK
Server: nginx/...
Content-Type: text/html
```

### 4. Authenticate and Push to Private ECR

When ready to publish to AWS ECR, authenticate your Docker CLI using the AWS CLI:

```bash
ECR_URI=$(terraform -chdir=terraform output -raw ecr_repository_url 2>/dev/null || echo "164824552037.dkr.ecr.ap-southeast-1.amazonaws.com/devops-bootcamp/final-project-hasb")

# Authenticate Docker daemon to ECR
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin "$ECR_URI"

# Tag image with 'latest' and immutable git commit SHA
GIT_SHA=$(git rev-parse --short HEAD)
docker tag devops-bootcamp-app:local "$ECR_URI:latest"
docker tag devops-bootcamp-app:local "$ECR_URI:$GIT_SHA"

# Push both tags to ECR
docker push "$ECR_URI:latest"
docker push "$ECR_URI:$GIT_SHA"
```

### 5. Stop Local Container

Shut down the local development container:

```bash
docker compose -f app/compose.yaml down
```

---

## Verification

### Checklist
- [x] Multi-stage build compiles Vite frontend into static assets in `dist/`.
- [x] Final container image size is ~26 MB (under the 30 MB target).
- [x] Build context excludes `node_modules` and metadata via `.dockerignore`.
- [x] Container passes built-in health check (`HEALTHCHECK CMD wget -qO- http://localhost:80/ || exit 1`).
- [x] Root endpoint returns `HTTP/1.1 200 OK`.
- [x] Docker Compose cleanly starts and stops without orphan networks.

---

## Troubleshooting

- **Port 80 already in use**:
  If another service occupies port 80, override the host port in `app/compose.yaml`:
  ```yaml
  ports:
    - "8080:80"
  ```
  Then test via `curl -I http://localhost:8080`.

- **ECR Authentication Expired**:
  ECR authorization tokens expire after 12 hours. If `docker push` returns `401 Unauthorized`, re-run `aws ecr get-login-password` to refresh the session token.

- **Vite Build Memory Warning**:
  If building on constrained memory environments, set `NODE_OPTIONS=--max-old-space-size=1024` in the builder stage.
