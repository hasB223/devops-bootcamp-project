# System Architecture Specification

Status: verified

This document specifies the end-to-end system architecture, network topology, security boundaries, and data flows of the DevOps platform deployed on Amazon Web Services (AWS) and exposed through Cloudflare under the domain `hasb.dev`.

---

## Purpose

The platform delivers a secure, containerized web application alongside an isolated observability stack. Key architectural goals include:
- **Zero Inbound SSH from Internet**: Administrative access to private and public instances is mediated exclusively through AWS Systems Manager (SSM) Session Manager.
- **Strict Network Segmentation**: Publicly facing web compute is separated from internal orchestration and monitoring workloads via RFC 1918 subnets.
- **Zero Inbound Public Ports for Observability**: The monitoring server resides entirely within a private subnet without an Elastic IP or public inbound security group rules, exposed securely via an outbound Cloudflare Zero Trust Tunnel.
- **Keyless CI/CD Authentication**: Automated container image publishing authenticates to private AWS ECR using short-lived OpenID Connect (OIDC) tokens issued by GitHub Actions.
- **Decoupled Deployment Boundary**: Container artifacts are published to AWS Private ECR via GitHub Actions; container rollouts on EC2 are orchestrated intentionally through the private Ansible Controller.

---

## High-Level Architecture

```text
                                   +--------------------------+
                                   |       Public Users       |
                                   +--------------------------+
                                      /                    \
                     HTTPS (port 443)|                      | HTTPS (port 443)
                    DNS: web.hasb.dev|                      | DNS: monitoring.hasb.dev
                                     v                      v
                       +-------------------+   +----------------------------+
                       |  Cloudflare Edge  |   |  Cloudflare Zero Trust     |
                       |  (Proxied / CDN)  |   |  Edge Network              |
                       +-------------------+   +----------------------------+
                                 |                            |
                       HTTP (80) |                            | Outbound Encrypted
                                 v                            | Tunnel (QUIC / TLS)
          +---------------------------------------------------|--------------------+
          | AWS VPC (10.0.0.0/24) - ap-southeast-1            |                    |
          |                                                   |                    |
          |   +-----------------------------------------------+----------------+   |
          |   | Public Subnet (10.0.0.0/25)                   |                |   |
          |   |                                               |                |   |
          |   |  +--------------------+             +---------v-------------+  |   |
          |   |  |    Web Server      |             |     NAT Gateway       |  |   |
          |   |  |     10.0.0.5       |             |   nat-0a3f940984...   |  |   |
          |   |  |  (Elastic IP)      |             +-----------------------+  |   |
          |   |  |                    |                         ^              |   |
          |   |  | - Docker Web App   |                         | Outbound     |   |
          |   |  |   (Port 80)        |                         | Internet     |   |
          |   |  | - Node Exporter    |                         | Only         |   |
          |   |  |   (Port 9100)      |                         |              |   |
          |   |  +--------------------+                         |              |   |
          |   +-------------------------------------------------|--------------+   |
          |                                                     |                  |
          |   +-------------------------------------------------|--------------+   |
          |   | Private Subnet (10.0.0.128/25)                  |              |   |
          |   |                                                 |              |   |
          |   |  +---------------------+             +----------+-----------+  |   |
          |   |  | Ansible Controller  |             |  Monitoring Server   |  |   |
          |   |  |     10.0.0.135      |             |     10.0.0.136       |  |   |
          |   |  | (No Public IP)      |             |  (No Public IP)      |  |   |
          |   |  |                     |             |                      |  |   |
          |   |  | - Ansible Playbook  |             | - Prometheus (:9090) |  |   |
          |   |  | - SSH to targets    |             | - Grafana (:3000)    |  |   |
          |   |  | - SSM Session Only  |             | - cloudflared Daemon |  |   |
          |   |  +---------------------+             +----------------------+  |   |
          |   +----------------------------------------------------------------+   |
          +------------------------------------------------------------------------+
```

---

## Network Architecture

The network layer is provisioned via Terraform in the AWS Singapore region (`ap-southeast-1`).

### Subnet Layout

| Subnet | CIDR Block | Available IPs | Purpose | Routing & Egress |
| --- | --- | --- | --- | --- |
| **Public Subnet** | `10.0.0.0/25` | 128 (123 usable) | Internet-facing workloads and NAT Gateway | Default route `0.0.0.0/0` -> Internet Gateway (`igw`) |
| **Private Subnet** | `10.0.0.128/25` | 128 (123 usable) | Management controller and monitoring infrastructure | Default route `0.0.0.0/0` -> NAT Gateway (`nat`) |

### Routing Table Configuration

1. **Public Route Table (`devops-public-rt`)**:
   - `10.0.0.0/24` -> `local` (intra-VPC traffic)
   - `0.0.0.0/0` -> `aws_internet_gateway.gw` (outbound internet access)
2. **Private Route Table (`devops-private-rt`)**:
   - `10.0.0.0/24` -> `local` (intra-VPC traffic)
   - `0.0.0.0/0` -> `aws_nat_gateway.nat` (egress via NAT Gateway in public subnet)

---

## Compute Topology & Server Roles

All compute instances run **Ubuntu 24.04 LTS (Noble Numbat)** on 64-bit ARM architecture (`t4g.small`):

### 1. Web Server (`10.0.0.5`)
- **Placement**: Public Subnet (`10.0.0.0/25`).
- **Addressing**: Private IP `10.0.0.5` + AWS Elastic IP.
- **Role**: Hosts the production Three.js containerized frontend.
- **Runtime Components**:
  - **Docker Engine**: Installed and managed via official Galaxy role `geerlingguy.docker`.
  - **Web Application Container** (`devops-web-app`): Production Nginx runtime container exposing port 80.
  - **Node Exporter Container** (`node-exporter`): Gathers host system metrics (CPU, memory, disk, network) on port 9100.
- **IAM Profile**: `devops-web-server-profile` (AWS SSM access + read-only authorization for AWS Private ECR).

### 2. Ansible Controller (`10.0.0.135`)
- **Placement**: Private Subnet (`10.0.0.128/25`).
- **Addressing**: Private IP `10.0.0.135` (Zero public IPs).
- **Role**: Centralized configuration management engine. All configuration changes and application rollouts are initiated from this node.
- **Runtime Components**:
  - **Ansible Core**: Executes multi-play orchestrations against target hosts.
  - **SSH Keypair**: Internal key (`devops-bootcamp-key`) authorized on target instances for VPC-internal management.
- **IAM Profile**: `devops-controller-profile` (AWS SSM access).

### 3. Monitoring Server (`10.0.0.136`)
- **Placement**: Private Subnet (`10.0.0.128/25`).
- **Addressing**: Private IP `10.0.0.136` (Zero public IPs).
- **Role**: Metrics scraping, storage, visualization, and edge tunneling.
- **Runtime Components**:
  - **Prometheus** (`prom/prometheus:v2.53.0`): Scrapes metrics from `10.0.0.5:9100` every 15s; binds internally to port 9090.
  - **Grafana** (`grafana/grafana:11.1.0`): Visualizes metrics on port 3000; pre-configured with declarative Prometheus data source and curated Node Exporter dashboard.
  - **Cloudflare Connector** (`cloudflare/cloudflared:2024.8.3`): Outbound Zero Trust Tunnel daemon connecting to Cloudflare Edge.
- **IAM Profile**: `devops-monitoring-server-profile` (AWS SSM access).

---

## Security Architecture & Network Boundaries

Security groups enforce least-privilege traffic flow across instances:

```text
[ Internet ]
     |
     | Port 80 (HTTP)
     v
+------------------+         Port 9100 (Metrics)         +----------------------+
|  Web Server SG   | ----------------------------------> | Monitoring Server SG |
| (web-server-sg)  | <---------------------------------- | (monitoring-server)  |
+------------------+        Prometheus Scrape Request    +----------------------+
     ^                                                             ^
     |                     SSH (Port 22)                           |
     +-------------------------------------------------------------+
                                   |
                       +-----------------------+
                       | Ansible Controller SG |
                       | (controller-sg)       |
                       +-----------------------+
                                   ^
                                   | AWS SSM Session Manager
                             [ Engineer ]
```

### Security Group Ingress Matrix

| Security Group | Ingress Source | Port / Protocol | Rationale |
| --- | --- | --- | --- |
| **`web-server-sg`** | `0.0.0.0/0` | Port 80 (TCP) | Public HTTP traffic routed from Cloudflare edge proxy |
| **`web-server-sg`** | `10.0.0.136/32` (Monitoring Server) | Port 9100 (TCP) | Allows Prometheus to scrape host node_exporter metrics |
| **`web-server-sg`** | `10.0.0.135/32` (Controller) | Port 22 (TCP) | Internal SSH configuration management from Controller |
| **`monitoring-server-sg`** | `10.0.0.135/32` (Controller) | Port 22 (TCP) | Internal SSH configuration management from Controller |
| **`monitoring-server-sg`** | `10.0.0.136/32` (Self) | Ports 3000, 9090 (TCP) | Inter-container metrics flow and local tunnel ingress |
| **`controller-sg`** | None (Zero inbound rules) | None | Controller accepts no inbound connections; access is SSM-only |

### Security Group Egress Rules
- All security groups allow outbound traffic (`0.0.0.0/0`) for package updates, container image pulls from ECR, and outbound Cloudflare tunnel traffic via the NAT Gateway or Internet Gateway.

---

## Ingress & Edge Access Plane

Traffic entering the platform uses two distinct routing patterns:

| Endpoint | Ingress Pattern | Public Inbound Ports on Host | Origin Security & Encryption |
| --- | --- | --- | --- |
| **`web.hasb.dev`** | Cloudflare DNS A-Record (Orange Cloud Proxied) | Port 80 (HTTP) | Cloudflare Anycast edge provides DDoS mitigation and TLS termination (`Full (strict)` or `Flexible`). Origin serves HTTP. |
| **`monitoring.hasb.dev`** | Cloudflare Zero Trust Tunnel (`cloudflared`) | **Zero public ports** | Tunnel connector establishes outbound TLS/QUIC connection to Cloudflare edge. Cloudflare terminates TLS and proxies traffic through the tunnel to `localhost:3000`. |

---

## CI/CD & Keyless Container Pipeline

The delivery pipeline automates quality checks and publishes immutable container artifacts without static AWS credentials:

```text
Developer Push / PR
       |
       v
+------------------------+
| GitHub Actions Runner  |
+------------------------+
  |
  | 1. Request signed OIDC JWT token
  v
[ GitHub OIDC Provider ] (token.actions.githubusercontent.com)
  |
  | 2. Exchange JWT via sts:AssumeRoleWithWebIdentity
  v
[ AWS STS ] (sts.amazonaws.com)
  |
  | 3. Validate Role Trust Policy:
  |    - aud: sts.amazonaws.com
  |    - sub: repo:hasB223/devops-bootcamp-project:ref:refs/heads/main
  |    - sub: repo:hasB223@124649481/devops-bootcamp-project@1358353685:ref:refs/heads/main
  v
[ Issue Temporary AWS Credentials ]
  |
  | 4. docker build -f app/Dockerfile app/
  | 5. docker push 164824552037.dkr.ecr.ap-southeast-1.amazonaws.com/...
  v
[ AWS Private ECR ]
```

---

## Failure Modes & Operational Boundaries

1. **Host Failure (Web Server)**:
   - The web container is stateless. Re-running the Ansible playbook on a newly provisioned instance immediately restores the service.
   - The Elastic IP can be dynamically re-associated with a replacement instance without changing DNS records.
2. **Monitoring Failure**:
   - Grafana dashboard definitions and datasource configurations are provisioned declaratively from files in `ansible/files/monitoring/`.
   - Historical time-series data is stored in the Docker volume `grafana-data`. Re-deploying containers preserves dashboards and user sessions.
3. **NAT Gateway Dependency**:
   - The private subnet relies on the NAT Gateway for outbound connectivity (apt updates, ECR pulls, Cloudflare tunnel). If the NAT Gateway is deleted to save costs, private instances retain local VPC connectivity but cannot reach external endpoints until the NAT Gateway is reprovisioned.
