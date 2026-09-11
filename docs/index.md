# DevOps Platform Documentation

Welcome to the engineering documentation portal for the **DevOps Bootcamp Capstone Platform** (`hasb.dev`).

This documentation covers the end-to-end cloud infrastructure, Zero-Trust network routing, configuration management, secrets lifecycle, and automated CI/CD deployment pipelines.

---

## Live Endpoints

<div class="grid cards" markdown>

- :material-web: __Web Application__

    ---

    Production frontend web application running in a Docker container on AWS EC2, protected by Cloudflare Anycast edge.

    [:octicons-arrow-right-24: https://web.hasb.dev](https://web.hasb.dev){:target="_blank"}

- :material-chart-timeline-variant: __Monitoring & Observability__

    ---

    Grafana observability dashboard visualizing Node Exporter host telemetry, routed privately over Cloudflare Zero Trust Tunnel.

    [:octicons-arrow-right-24: https://monitoring.hasb.dev](https://monitoring.hasb.dev){:target="_blank"}

- :material-book-open-page-variant: __Documentation Portal__

    ---

    Automated technical runbook and architecture portal hosted on custom domain via GitHub Pages and Cloudflare edge.

    [:octicons-arrow-right-24: https://docs.hasb.dev](https://docs.hasb.dev)

- :material-github: __Source Code Repository__

    ---

    Complete declarative Infrastructure as Code, Ansible playbooks, Docker Compose definitions, and CI/CD pipelines.

    [:octicons-arrow-right-24: GitHub Repository](https://github.com/hasB223/devops-bootcamp-project){:target="_blank"}

</div>

---

## Architecture Overview

### Interactive Architecture Canvas
For full pan, zoom, component drill-downs, and infrastructure inspection, open the standalone interactive architecture diagram:

> [!TIP]
> **Explore the Interactive Canvas**: Open the dedicated [**Interactive End-State Architecture Diagram**](assets/final-project-end-state.html){:target="_blank"} for a full-screen interactive view generated via Archify.

---

### End-State System Topology

```mermaid
flowchart TD
    subgraph Users ["Public Internet"]
        Browser["User Browser / Client"]
    end

    subgraph CloudflareEdge ["Cloudflare Anycast Global Edge (hasb.dev)"]
        CF_DNS["Cloudflare DNS"]
        CF_WAF["Cloudflare WAF / DDoS"]
        CF_Rules["Configuration Ruleset (Flexible SSL)"]
        CF_Tunnel["Cloudflare Zero Trust Tunnel"]
    end

    subgraph AWS ["Amazon Web Services (ap-southeast-1)"]
        subgraph VPC ["Custom VPC (10.0.0.0/16)"]
            subgraph PublicSubnet ["Public Subnet (10.0.0.0/24)"]
                EIP["Elastic IP (18.142.89.74)"]
                WebServer["Web EC2 (10.0.0.5)\nDocker: devops-web-app\nnode_exporter: 9100"]
                IGW["Internet Gateway"]
            end

            subgraph PrivateSubnet ["Private Subnet (10.0.0.128/24)"]
                Controller["Ansible Controller (10.0.0.135)\nInfisical CLI & SSM Agent"]
                MonitoringServer["Monitoring EC2 (10.0.0.136)\nPrometheus (9090)\nGrafana (3000)\ncloudflared connector"]
            end

            NAT["NAT Gateway (Parked)"]
            S3_EP["S3 VPC Endpoint (SSM Transport)"]
        end

        ECR["AWS Private ECR\nDocker Container Images"]
        SSM["AWS Systems Manager\nSession & Run Command"]
        S3_Bucket["S3 State & SSM Relay Bucket"]
    end

    subgraph InfisicalCloud ["Secrets Management"]
        Infisical["Infisical Cloud (dev /ansible)"]
    end

    Browser -->|HTTPS :443| CF_WAF
    CF_WAF --> CF_DNS
    CF_DNS -->|A Record :80| WebServer
    CF_DNS -->|CNAME Tunnel| CF_Tunnel
    CF_Tunnel -->|Encrypted Outbound| MonitoringServer
    Controller -->|Ansible over SSM| WebServer
    Controller -->|Ansible over SSM| MonitoringServer
    Controller -->|Fetch Secrets| Infisical
    MonitoringServer -->|Scrape Metrics :9100| WebServer
    WebServer -->|Pull Images| ECR
```

---

## Technical Documentation Guide

<div class="grid cards" markdown>

- :material-file-document-outline: __[System Architecture](architecture.md)__

    ---

    VPC topology, network segmentation, security group isolation, port matrices, and data flow specifications.

- :material-clipboard-check-outline: __[Operational Runbook](runbook.md)__

    ---

    Step-by-step deployment instructions, verification procedures, parking protocols, and break-glass fallbacks.

- :material-cloud-outline: __[AWS Terraform IaC](terraform.md)__

    ---

    VPC, subnets, EC2 instances, security groups, IAM least-privilege roles, ECR repository, and S3 remote backend.

- :material-shield-cloud-outline: __[Cloudflare Edge IaC](cloudflare.md)__

    ---

    Cloudflare Provider v5.24.0 automation: DNS records, Zero Trust Tunnel, and declarative configuration rulesets.

- :material-ansible: __[Ansible Automation](ansible.md)__

    ---

    Ansible over SSM transport with zero SSH port 22, idempotent plays, and automated in-container Grafana password synchronization.

- :material-docker: __[Docker Compose Stack](docker.md)__

    ---

    Multi-container composition, health checks, restart policies, and named volume persistence.

- :material-chart-bell-curve: __[Observability & Monitoring](monitoring.md)__

    ---

    Prometheus scrape jobs, node_exporter metrics, and code-provisioned Grafana dashboards.

- :material-git: __[CI/CD & Delivery](cicd.md)__

    ---

    GitHub Actions OIDC authentication, multi-linter PR gates, automated container builds, and zero-downtime SSM auto-deploys.

- :material-key-outline: __[Secrets Management](secrets-management.md)__

    ---

    Zero-secret repository hygiene, Infisical Cloud integration, machine identities, and Day-2 SQLite volume sync.

</div>

---

## Verified Infrastructure Evidence

All architectural components and operational tracks are verified live in AWS:

| Milestone / Component | Verification Artifact | Description |
| :--- | :--- | :--- |
| **Web Application** | [`assets/web-app-live.png`](assets/web-app-live.png) | Three.js spaceship simulation rendering live over HTTPS at `web.hasb.dev`. |
| **Observability Dashboard** | [`assets/grafana-dashboard-live.png`](assets/grafana-dashboard-live.png) | Declarative Grafana dashboard tracking real-time CPU, RAM, and disk metrics. |
| **Interactive Topology** | [`assets/final-project-end-state.html`](assets/final-project-end-state.html) | Interactive standalone Archify canvas with full system topology. |
| **Secrets Architecture** | [`assets/secrets-management.architecture.json`](assets/secrets-management.architecture.json) | Complete diagrammatic model of the Infisical secrets delivery path. |
