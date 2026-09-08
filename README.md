# DevOps Infrastructure Platform

[![CI Quality Gate](https://github.com/hasB223/devops-bootcamp-project/actions/workflows/ci.yml/badge.svg)](https://github.com/hasB223/devops-bootcamp-project/actions/workflows/ci.yml)
[![Documentation Portal](https://github.com/hasB223/devops-bootcamp-project/actions/workflows/pages.yml/badge.svg)](https://hasb223.github.io/devops-bootcamp-project/)
[![Terraform](https://img.shields.io/badge/Terraform-1.10%2B-844FBA?logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Ansible](https://img.shields.io/badge/Ansible-2.16%2B-EE0000?logo=ansible&logoColor=white)](https://www.ansible.com/)
[![Docker](https://img.shields.io/badge/Docker-Engine%20%26%20Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

A secure, multi-tier cloud infrastructure platform deployed on **Amazon Web Services (AWS)** and fronted by **Cloudflare**. The platform hosts a containerized Three.js application alongside an isolated Prometheus/Grafana observability stack, configured through Ansible and delivered via GitHub Actions CI/CD with AWS IAM OIDC identity federation.

---

## Primary Endpoints

| Service | Endpoint | Description | Access Model |
| --- | --- | --- | --- |
| **Web Application** | [web.hasb.dev](https://web.hasb.dev) | Three.js containerized frontend hosted on Web EC2 | Cloudflare Anycast edge proxy (DDoS protection, TLS termination) |
| **Observability Dashboard** | [monitoring.hasb.dev](https://monitoring.hasb.dev) | Grafana monitoring dashboard querying Prometheus | Cloudflare Zero Trust Tunnel (Zero public inbound ports on host) |
| **Source Repository** | [GitHub Repository](https://github.com/hasB223/devops-bootcamp-project) | Complete Infrastructure as Code, playbooks, and runbooks | Git version control |
| **Documentation Portal** | [Documentation Portal](https://hasb223.github.io/devops-bootcamp-project/) | Browsable web documentation, runbooks, and diagrams | GitHub Pages |

---

## Architecture Overview

```text
[ Public Users ]                     [ Operators ]
       |                                   |
       | HTTPS                             | Cloudflare Zero Trust
       v                                   v
+-------------------+             +-------------------------+
|  Cloudflare Edge  |             | Cloudflare Edge Network |
|  (Anycast Proxy)  |             +-------------------------+
+-------------------+                          |
       |                                       | Outbound Encrypted Tunnel
       | HTTP (:80)                            v
+------v---------------------------------------+-----------------------------+
| AWS Singapore (ap-southeast-1)               |                             |
|                                              |                             |
| Public Subnet (10.0.0.0/25)                  |                             |
| +-------------------------+                  |                             |
| | Web Server (10.0.0.5)   |                  |                             |
| | - Docker App (Port 80)  |                  |                             |
| | - node_exporter (:9100) |                  |                             |
| +-------------------------+                  |                             |
|              ^                               |                             |
|              | Metrics Scrape (:9100)        |                             |
|              |                               |                             |
| Private Subnet (10.0.0.128/25)               |                             |
| +-------------------------+      +-----------v---------------------------+ |
| | Ansible Controller      |      | Monitoring Server (10.0.0.136)        | |
| | (10.0.0.135)            |      | - Prometheus (:9090)                  | |
| | - Configuration Engine  |      | - Grafana (:3000)                     | |
| | - SSM Session Access    |      | - cloudflared Daemon                  | |
| +-------------------------+      +---------------------------------------+ |
+----------------------------------------------------------------------------+
```

An interactive diagram of the network topology and service architecture is available in the [Full Screen Architecture Visualizer](https://hasb223.github.io/devops-bootcamp-project/assets/final-project-end-state.html) or on the [Documentation Portal](https://hasb223.github.io/devops-bootcamp-project/).

For detailed technical specifications, see [docs/architecture.md](docs/architecture.md).

---

## Key Technical Features

- **Zero Inbound SSH from Internet**: Administrative access to private and public instances is mediated exclusively through AWS Systems Manager (SSM) Session Manager.
- **Strict Network Isolation**: Web compute is placed in a public subnet (`10.0.0.0/25`), while configuration orchestration and monitoring workloads are isolated in a private subnet (`10.0.0.128/25`) with outbound egress via a NAT Gateway.
- **Zero Inbound Public Ports for Monitoring**: Grafana is served through an outbound Cloudflare Zero Trust Tunnel connector daemon (`cloudflared`), completely hiding the host from public IP scanning.
- **Keyless Container Publishing (OIDC)**: GitHub Actions builds and pushes container images to AWS Private ECR using short-lived STS tokens exchanged via OpenID Connect (zero static AWS access keys).
- **Decoupled Deployment Boundary**: Container artifacts are published to ECR on merge; production container updates on EC2 are orchestrated intentionally via Ansible.
- **Idempotent Multi-Play Automation**: Ansible configuration uses official Galaxy roles (`geerlingguy.docker`) and converges cleanly (`changed=0` on rerun).

---

## Repository Structure

```text
devops-bootcamp-project/
├── .github/
│   └── workflows/
│       ├── ci.yml                 # PR Quality Gate (Terraform, Ansible, App build)
│       ├── build-push-ecr.yml     # Main-branch container build & push to ECR via OIDC
│       └── pages.yml              # Documentation publishing to GitHub Pages
├── ansible/
│   ├── ansible.cfg                # Ansible configuration & defaults
│   ├── requirements.yml           # Galaxy roles & collections declarations
│   ├── inventory.ini.example      # Target host inventory template
│   ├── group_vars/
│   │   └── all.yml                # Dynamic variables and domain configuration
│   ├── templates/                 # Jinja2 templates for Prometheus & Docker Compose
│   ├── files/                     # Grafana datasources & dashboard definitions
│   └── playbook.yml               # Multi-play orchestration playbook
├── app/
│   ├── Dockerfile                 # Multi-stage production container build
│   ├── compose.yaml               # Local application compose definition
│   ├── package.json               # Frontend Node.js dependencies & scripts
│   └── src/                       # Three.js application source code
├── docs/                          # Comprehensive operational runbooks
│   ├── architecture.md            # System architecture specification
│   ├── runbook.md                 # Master 0-to-1 operational runbook
│   ├── terraform.md               # Infrastructure provisioning guide
│   ├── docker.md                  # Containerization guide
│   ├── ansible.md                 # Configuration management runbook
│   ├── monitoring.md              # Observability & dashboard runbook
│   ├── cloudflare.md              # Domain routing & Zero Trust tunnel guide
│   ├── cicd.md                    # CI/CD pipelines & OIDC federation runbook
│   ├── secrets-management.md      # Secrets strategy & Infisical architecture
│   ├── git-workflow.md            # Branching & commit standards
│   └── index.html                 # Documentation portal for GitHub Pages
├── terraform/
│   ├── main.tf                    # VPC, subnets, route tables, and S3 backend
│   ├── ec2.tf                     # EC2 instances, Elastic IPs, and NAT Gateway
│   ├── ecr.tf                     # Private container registry & lifecycle policies
│   ├── iam.tf                     # Instance profiles & GitHub OIDC identity federation
│   ├── security_groups.tf         # Layered security group ingress/egress rules
│   ├── variables.tf               # Input parameter definitions
│   ├── outputs.tf                 # Exported endpoints, role ARNs, and inventory
│   └── terraform.tfvars.example   # Example variable assignments
└── README.md                      # Repository root landing page
```

---

## Quick Reference

### 1. Terraform Verification & Apply
```bash
cd terraform
terraform init -backend=false
terraform fmt -check
terraform validate
```

To plan and apply against AWS:
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 2. Ansible Playbook Syntax Check & Run
```bash
# Validate playbook syntax
ansible-playbook --syntax-check -i ansible/inventory.ini.example ansible/playbook.yml

# Execute configuration from Ansible Controller
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml
```

### 3. Application Build & Smoke Test
```bash
cd app
npm ci
npm run test
npm run build
```

---

## Documentation Index

The complete documentation suite is maintained as durable operational runbooks:

| Document | Focus Area |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Deep-dive network topology, security groups, and component interactions |
| [docs/runbook.md](docs/runbook.md) | Complete 0-to-1 build sequence, verification checklist, and cost management |
| [docs/terraform.md](docs/terraform.md) | VPC networking, EC2 compute, private subnets, security groups, and S3 backend |
| [docs/docker.md](docs/docker.md) | Multi-stage Dockerfile, image minimization, and local compose verification |
| [docs/ansible.md](docs/ansible.md) | Multi-play configuration, Docker runtime, ECR IAM auth, and idempotency |
| [docs/monitoring.md](docs/monitoring.md) | Prometheus metrics collection, node_exporter daemon, and pre-provisioned Grafana |
| [docs/cloudflare.md](docs/cloudflare.md) | DNS A-record proxying, Zero Trust Tunnel setup, and future Terraform IaC path |
| [docs/cicd.md](docs/cicd.md) | GitHub Actions PR gates, AWS OIDC identity federation, and Pages deployment |
| [docs/secrets-management.md](docs/secrets-management.md) | Infisical Cloud strategy, workload identity, and zero static credentials policy |
| [docs/git-workflow.md](docs/git-workflow.md) | Branching conventions, conventional commits, and pull request lifecycle |
