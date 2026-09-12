# Monitoring & Observability Runbook

This document describes the automated deployment, architecture, and operational verification of the **Prometheus** and **Grafana** monitoring stack, paired with **Node Exporter**, across the DevOps capstone infrastructure.

---

## Purpose

The monitoring layer provides metrics collection, alerting foundations, and visual operational dashboards:

- **Host Metrics Telemetry**: Runs `node_exporter` on the **Web Server** (`10.0.0.5`), exposing CPU, memory, disk, and network metrics on port `9100`.
- **Centralized Metrics Aggregation**: Runs **Prometheus** as a containerized service on the **Monitoring Server** (`10.0.0.136`), scraping `node_exporter` every 15 seconds.
- **Operational Visualization**: Runs **Grafana** as a containerized dashboard service on the Monitoring Server, pre-provisioned with the Prometheus data source and a curated Node Exporter dashboard.
- **State Persistence**: Uses a named Docker volume (`grafana-data`) to persist Grafana configurations, dashboards, and operational data across container lifecycle events.
- **VPC-Internal Network Security**: Port `9100` on the Web Server is strictly restricted to the Monitoring Server (`10.0.0.136/32`). Prometheus (`9090`) and Grafana (`3000`) remain completely private within the VPC; public access is deferred to Phase 5 via Cloudflare Tunnel.

---

## Architecture & Metrics Chain

```text
                                  VPC Subnet (10.0.0.0/24)
  +-----------------------------------------------------------------------------------------+
  |                                                                                         |
  |   [Public Subnet: 10.0.0.0/25]                        [Private Subnet: 10.0.0.128/25]   |
  |                                                                                         |
  |   +--------------------------+                        +-----------------------------+   |
  |   |        Web Server        |                        |      Monitoring Server      |   |
  |   |        (10.0.0.5)        |                        |        (10.0.0.136)         |   |
  |   |                          |                        |                             |   |
  |   |   devops-web-app (:80)   |                        |   Prometheus Container      |   |
  |   |   (Public via EIP)       |                        |   (:9090)                   |   |
  |   |                          |                        |   - scrape 10.0.0.5:9100    |   |
  |   |   node_exporter (:9100)  | <--- Scrape (15s) ---- |   - bind mount config       |   |
  |   |   (Restricted SG)        |      Port 9100         |              ^              |   |
  |   +--------------------------+                        |              | Queries      |   |
  |                                                       |              v              |   |
  |                                                       |   Grafana Container         |   |
  |                                                       |   (:3000)                   |   |
  |                                                       |   - named volume            |   |
  |                                                       |     (grafana-data)          |   |
  |                                                       |   - automated datasource    |   |
  |                                                       |   - imported dashboard      |   |
  |                                                       +-----------------------------+   |
  |                                                                      ^                  |
  |                                                                      | Internal tests   |
  |                                                       +-----------------------------+   |
  |                                                       |      Ansible Controller     |   |
  |                                                       |        (10.0.0.135)         |   |
  |                                                       |   - Orchestrates plays      |   |
  |                                                       |   - Verifies target health  |   |
  |                                                       +-----------------------------+   |
  +-----------------------------------------------------------------------------------------+
```

### Metrics Chain Overview:
1. `node_exporter` on `10.0.0.5:9100` exposes machine metrics.
2. Prometheus on `10.0.0.136:9090` polls `http://10.0.0.5:9100/metrics` every 15s via the VPC private network.
3. Grafana on `10.0.0.136:3000` queries Prometheus via Docker container network (`http://prometheus:9090`) and renders operational panels.

!!! note "Deterministic Datasource UID & SSM Inventory Decoupling"
    - **Datasource UID Matching**: The curated dashboard JSON expects datasource UID `"Prometheus"`. Declarative provisioning explicitly sets `uid: Prometheus` in `datasources/prometheus.yaml` so Grafana does not generate a random internal UID on initial volume creation.
    - **Scrape Target Decoupling**: Under Ansible SSM transport (`amazon.aws.aws_ssm`), `ansible_host` contains the AWS Instance ID (`i-...`). The Prometheus template decouples scrape routing by resolving `node_exporter_host` (`10.0.0.5`) or host `private_ip`, preventing unresolvable EC2 instance IDs from entering Docker DNS.

---

## Security & Network Boundaries

| Service | Port | Bound Interface | Allowed Ingress | Enforcement Layer |
| :--- | :--- | :--- | :--- | :--- |
| **Node Exporter** | `9100` | `0.0.0.0` (Container) | `10.0.0.136/32` (Monitoring Server only) | `devops-public-sg` (AWS Security Group) |
| **Prometheus** | `9090` | `0.0.0.0` (Container) | VPC CIDR (`10.0.0.0/24`) only | `devops-private-sg` (AWS Security Group) |
| **Grafana** | `3000` | `0.0.0.0` (Container) | VPC CIDR (`10.0.0.0/24`) only | `devops-private-sg` (AWS Security Group) |

!!! important
    Neither Prometheus (`9090`) nor Grafana (`3000`) is accessible from the public internet. External access to Grafana is provisioned exclusively in Phase 5 via Cloudflare Tunnel (`cloudflared`) without opening any inbound firewall ports.

---

## Files

All configuration templates and provisioning files are tracked in `ansible/`:

```text
ansible/
├── group_vars/
│   └── all.yml                                                 # Monitoring images, ports, and vault vars
├── templates/
│   └── monitoring/
│       ├── compose.yaml.j2                                     # Docker Compose definition for Prometheus + Grafana
│       └── prometheus.yaml.j2                                  # Prometheus scrape configuration template
├── files/
│   └── monitoring/
│       └── grafana/
│           └── provisioning/
│               ├── datasources/
│               │   └── prometheus.yaml                         # Declarative default Prometheus datasource
│               └── dashboards/
│                   ├── dashboards.yaml                         # Declarative dashboard file provider
│                   └── definitions/
│                       └── node-exporter.json                  # Curated Node Exporter dashboard JSON
└── playbook.yml                                                # Master playbook plays for Web and Monitoring
```

---

## Secret & Credential Direction

The Grafana admin password is **never** committed or hardcoded in version control:
- In `ansible/group_vars/all.yml`, `grafana_admin_password` resolves dynamically from the `GRAFANA_ADMIN_PASSWORD` environment variable:
  ```yaml
  grafana_admin_password: "{{ lookup('env', 'GRAFANA_ADMIN_PASSWORD') | default('VAULT_MANAGED_PLACEHOLDER_INJECT_VIA_INFISICAL', true) }}"
  ```
- **Operator Workflow with Infisical**:
  ```bash
  # Inject secret directly from Infisical project vault into runtime subshell
  export GRAFANA_ADMIN_PASSWORD=$(infisical secrets get GRAFANA_ADMIN_PASSWORD --plain)
  ansible-playbook playbook.yml
  ```
- **Fail-Fast Preflight Validation**: Play 3 asserts that `grafana_admin_password` is defined, has a minimum length of 12 characters, and does not equal the default vault placeholder. If the environment variable is unset or insecure, execution halts immediately with `no_log: true` before generating `compose.yaml` or starting containers.
- **Local Fallback**: Alternatively, create an untracked `ansible/vault.yml` (gitignored) and pass `--extra-vars @vault.yml`.

---

## Deployment Steps

All plays are executed from the **Ansible Controller** (`10.0.0.135`):

### 1. Connect to Ansible Controller
```bash
# Connect via AWS Systems Manager
CONTROLLER_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=ansible-controller" "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text)
aws ssm start-session --target "$CONTROLLER_ID"
sudo su - ubuntu
cd devops-bootcamp-project/ansible
```

### 2. Verify Scrape Targets in Inventory
Ensure `inventory.ini` specifies the correct internal IPs:
```ini
[web]
web-server ansible_host=10.0.0.5

[monitoring]
monitoring-server ansible_host=10.0.0.136
```

### 3. Run Playbook
```bash
ansible-playbook playbook.yml
```

**Playbook Actions for Monitoring:**
1. **Web Server (`web`)**: Deploys `prom/node-exporter:v1.8.2` container with `/proc` and `/sys` mounts, verifies `http://127.0.0.1:9100/metrics` returns HTTP 200.
2. **Monitoring Server (`monitoring`)**:
   - Creates `/opt/monitoring` directory hierarchy.
   - Deploys `prometheus.yaml` with scrape target `10.0.0.5:9100`.
   - Copies automated Grafana provisioning definitions (datasource and dashboard).
   - Deploys `compose.yaml` declaring `prometheus`, `grafana`, and named volume `grafana-data`.
   - Launches containers via `docker compose up -d`.
   - Validates health endpoints on ports 9090 and 3000.

---

## Operational Verification

### 1. Verify Node Exporter Metrics (Web Server)
From the Ansible Controller or within Web Server:
```bash
curl -s http://10.0.0.5:9100/metrics | head -n 20
```
**Expected**: Prometheus exposition formatted metrics (e.g. `node_cpu_seconds_total`, `node_memory_MemAvailable_bytes`).

### 2. Verify Prometheus Health & Scrape Targets (Monitoring Server)
From the Ansible Controller:
```bash
# Health check
curl -s http://10.0.0.136:9090/-/healthy
# Returns: Prometheus Server is Healthy.

# Target inspection API
curl -s http://10.0.0.136:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, instance: .labels.instance, health: .health}'
```
**Expected JSON Output**:
```json
{
  "job": "prometheus",
  "instance": "localhost:9090",
  "health": "up"
}
{
  "job": "node_exporter",
  "instance": "10.0.0.5:9100",
  "health": "up"
}
```
Both `prometheus` and `node_exporter` show `"health": "up"`.

### 3. Verify Grafana Datasource & Dashboard (Monitoring Server)
From the Ansible Controller:
```bash
# Health check
curl -s http://10.0.0.136:3000/api/health
# Returns: {"commit":"...","database":"ok","version":"11.1.0"}

# Check pre-provisioned data sources
curl -s -u admin:<GRAFANA_ADMIN_PASSWORD> http://10.0.0.136:3000/api/datasources | jq '.[].name'
# Returns: "Prometheus"
```

---

## Verification Checklist

- [x] Node Exporter deployed on Web Server (`10.0.0.5`) exposing metrics on port 9100.
- [x] Port 9100 restricted to Monitoring Server (`10.0.0.136/32`) via `devops-public-sg`.
- [x] Prometheus deployed via Docker Compose on Monitoring Server (`10.0.0.136:9090`).
- [x] `prometheus.yaml` mounted via bind mount scraping `10.0.0.5:9100`.
- [x] Grafana deployed via Docker Compose on Monitoring Server (`10.0.0.136:3000`).
- [x] Named Docker volume `grafana-data` declared and mounted for persistence.
- [x] Automated provisioning configures Prometheus datasource in Grafana (`http://prometheus:9090`).
- [x] Node Exporter host metrics dashboard automatically loaded on startup.
- [x] Grafana admin password managed via Infisical/environment variable without hardcoded credentials.
- [x] Ports 9090 and 3000 remain private within the VPC (zero public ingress).

---

## Troubleshooting

| Symptom | Cause | Remediation |
| :--- | :--- | :--- |
| **Prometheus shows `node_exporter` target `DOWN`** | Security group ingress blocking port 9100, or `node_exporter` not running | Verify `devops-public-sg` allows port 9100 from `10.0.0.136/32`. Check container status on Web Server: `docker ps -f name=node_exporter`. |
| **Grafana datasource test fails: `connection refused`** | Wrong Prometheus URL in datasource config | Ensure Grafana datasource points to `http://prometheus:9090` (Docker internal DNS name), not `localhost:9090`. |
| **Dashboard panels show `No Data`** | Prometheus empty or time range mismatch | Check Prometheus targets at `http://10.0.0.136:9090/api/v1/targets`. Ensure host clock is synchronized via NTP (`timedatectl`). |
| **Grafana restarts lose dashboards or settings** | Named volume not mounted | Confirm `compose.yaml` has `volumes: [grafana-data:/var/lib/grafana]` and top-level `volumes: { grafana-data: }`. |
| **`permission denied` accessing `/opt/monitoring`** | Incorrect directory ownership | Ensure `/opt/monitoring` is owned by `ubuntu:ubuntu` with mode `0755`. |
