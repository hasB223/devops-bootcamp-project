# Domain and Cloudflare Integration

This runbook details the architecture, manual control-plane configuration, Ansible
connector automation, and future Infrastructure-as-Code (IaC) path for integrating
Cloudflare DNS and Cloudflare Zero Trust Tunnel into the project infrastructure.

---

## Purpose

Phase 5 establishes secure public entry points for the application and monitoring
planes under the personal domain **`hasb.dev`**:

1. **Public Web Entry (`web.hasb.dev`)**: Routes public HTTP/HTTPS traffic through
   Cloudflare Anycast edge servers to the Web EC2 instance's Elastic IP, providing
   DDoS mitigation, CDN caching, and automatic TLS termination.
2. **Private Monitoring Entry (`monitoring.hasb.dev`)**: Exposes Grafana
   (`localhost:3000`) on the Monitoring EC2 instance (`10.0.0.136`) via an outbound
   Cloudflare Zero Trust Tunnel (`cloudflared`). The monitoring server has **zero**
   public IP addresses and **zero** public inbound ports open in AWS Security Groups.
3. **Control Plane vs. Data Plane Separation**: Clarifies the boundary between
   Cloudflare-side management (DNS, Tunnel registration) and host-level container
   orchestration (Ansible).
4. **Future IaC Expansion**: Documents how the Cloudflare control plane can be
   transitioned from console management into Terraform via the official
   `cloudflare/cloudflare` provider.

---

## Architectural Boundary

The Cloudflare integration is intentionally partitioned into distinct operational
layers:

```text
+-----------------------------------------------------------------------------------+
|                           CLOUDFLARE CONTROL PLANE                                |
|   (Configured via Cloudflare Dashboard; Future IaC: cloudflare/cloudflare)       |
|                                                                                   |
|   1. DNS A-Record: web.hasb.dev -> Elastic IP (Proxied)                           |
|   2. Zero Trust Tunnel: devops-monitoring-tunnel                                  |
|   3. Public Hostname: monitoring.hasb.dev -> HTTP localhost:3000                  |
|   4. SSL/TLS Policy: Flexible (Lab origin) / Full Strict (TLS origin)             |
+-----------------------------------------+-----------------------------------------+
                                          | Outbound TLS Tunnel (Port 443)
                                          v
+-----------------------------------------------------------------------------------+
|                             HOST DATA PLANE (AWS VPC)                             |
|                        (Automated via Ansible Playbook)                           |
|                                                                                   |
|   Web Server (10.0.0.5)               Monitoring Server (10.0.0.136)              |
|   +--------------------------+        +---------------------------------------+   |
|   | Elastic IP: :80 (Public) |        | Private Subnet Only (No Public IP)   |   |
|   | devops-web-app (Nginx)   |        | Grafana (:3000)                       |   |
|   | node_exporter (:9100)    |        | Prometheus (:9090)                    |   |
|   +--------------------------+        | cloudflared (Connector Docker)       |   |
|                                       +---------------------------------------+   |
+-----------------------------------------------------------------------------------+
```

- **Control Plane**:
  - DNS zone records and proxy modes.
  - Zero Trust Tunnel registration and tunnel secret generation.
  - Ingress hostname routing rules on Cloudflare's edge.
  - In this baseline, control-plane resources are configured via the Cloudflare Web
    Console.
- **Data Plane (Connector Runtime)**:
  - The `cloudflared` agent running as a Docker container on the Monitoring EC2
    instance.
  - Automated idempotently via Ansible Play 4 on the `monitoring` inventory host.
- **Secrets Management**:
  - The tunnel connector token (`CLOUDFLARE_TUNNEL_TOKEN`) is stored securely in
    Infisical Cloud (`/ansible`) or supplied via an ephemeral local environment
    variable.
  - Never committed to version control.

---

## Files

| File | Purpose |
| --- | --- |
| `ansible/group_vars/all.yml` | Domain parameters (`hasb.dev`, subdomains) and dynamic `CLOUDFLARE_TUNNEL_TOKEN` lookup. |
| `ansible/templates/monitoring/compose.yaml.j2` | Configures `GF_SERVER_ROOT_URL` so Grafana redirects reflect `https://monitoring.hasb.dev`. |
| `ansible/playbook.yml` | Play 4: Deploys `cloudflared` Docker container with fail-fast preflight token assertion. |
| `docs/cloudflare.md` | Durable production runbook for DNS, Tunnels, and future IaC expansion. |

---

## Inputs

| Parameter | Type | Source / Location | Description |
| --- | --- | --- | --- |
| `domain_name` | Config | `ansible/group_vars/all.yml` | Root domain: `hasb.dev` |
| `web_subdomain` | Config | `ansible/group_vars/all.yml` | Web application subdomain: `web` |
| `monitoring_subdomain` | Config | `ansible/group_vars/all.yml` | Monitoring dashboard subdomain: `monitoring` |
| `web_public_ip` | Runtime | Terraform output `web_public_ip` | Elastic IP assigned to Web EC2 instance |
| `CLOUDFLARE_TUNNEL_TOKEN` | Secret | Infisical path `/ansible` | Tunnel authentication secret generated by Cloudflare Zero Trust |
| `cloudflared_image` | Config | `ansible/group_vars/all.yml` | Pinned Docker container image: `cloudflare/cloudflared:2024.8.3` |

---

## Prerequisites

1. **Infisical & Local Fallback**:
   - Setting up Infisical is not required to write or test playbook code.
   - For live deployment of `cloudflared` on the monitoring server,
     `CLOUDFLARE_TUNNEL_TOKEN` must be available either via Infisical CLI or exported
     directly in the shell session.
2. **Fail-Fast Security Guarantee**:
   - The playbook enforces a preflight assertion on `CLOUDFLARE_TUNNEL_TOKEN`.
   - If the variable is unset or remains set to the default placeholder
     (`VAULT_MANAGED_PLACEHOLDER_INJECT_VIA_INFISICAL`), execution halts immediately
     with `no_log: true` before launching any Docker containers.

---

## Steps

### Part 1: Cloudflare DNS Setup for Web Application (`web.hasb.dev`)

1. **Navigate to DNS Management**:
   ```text
   Cloudflare Dashboard -> Websites -> hasb.dev -> DNS -> Records
   ```
2. **Create Web Application A-Record**:
   - Click **Add record**.
   - **Type**: `A`
   - **Name**: `web` (resolves to `web.hasb.dev`)
   - **IPv4 address**: Enter the Web Server Elastic IP (retrieved from `terraform output -raw web_public_ip`).
   - **Proxy status**: Set to **Proxied** (Orange cloud icon).
   - **TTL**: Auto.
   - Click **Save**.

3. **Configure SSL/TLS Encryption Mode**:
   ```text
   Cloudflare Dashboard -> Websites -> hasb.dev -> SSL/TLS -> Overview
   ```
   - **Target / Production Mode**: `Full` or `Full (strict)` is required when the
     origin web server has an SSL/TLS certificate installed.
   - **Lab / Current Phase Mode**: Because the Web Server Nginx container serves
     plain HTTP on port 80 (origin certificates are not yet provisioned on the host),
     select **Flexible** (or create a Configuration Rule for `web.hasb.dev` with
     SSL set to `Flexible`).
   - *Security Note*: `Flexible` encrypts traffic between the browser and Cloudflare
     Edge, but transmits plain HTTP between Cloudflare Edge and the EC2 origin. When
     custom origin certificates or Let's Encrypt are provisioned in later phases,
     immediately switch to `Full (strict)`.

---

### Part 2: Cloudflare Zero Trust Tunnel Setup for Monitoring (`monitoring.hasb.dev`)

1. **Open Zero Trust Dashboard**:
   ```text
   Cloudflare Dashboard -> Zero Trust -> Networks -> Tunnels
   ```
2. **Create New Tunnel**:
   - Click **Create a tunnel**.
   - Select connector type: **Cloudflared**.
   - Click **Next**.
   - **Tunnel name**: `devops-monitoring-tunnel`.
   - Click **Save tunnel**.

3. **Capture Connector Token**:
   - Under **Choose your environment**, select **Docker**.
   - Locate the command snippet displayed in the console:
     ```bash
     docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TOKEN_VALUE>
     ```
   - Copy only the `<TOKEN_VALUE>` string. This token contains the tunnel's
     cryptographic credentials.

4. **Store Token in Infisical**:
   - Store the token in Infisical Cloud under project `devops-bootcamp-project`,
     environment `prod`, path `/ansible`:
     ```bash
     infisical secrets set \
       --projectId="6c8dad30-9f25-44dd-ae65-08c06580ceed" \
       --env=prod \
       --path=/ansible \
       CLOUDFLARE_TUNNEL_TOKEN="<TOKEN_VALUE>"
     ```
   - *Temporary shell fallback (if running without Infisical)*:
     ```bash
     export CLOUDFLARE_TUNNEL_TOKEN="<TOKEN_VALUE>"
     ```

5. **Configure Public Hostname Ingress**:
   - In the Cloudflare Zero Trust Tunnel creation wizard, click the **Public Hostnames** tab.
   - Click **Add a public hostname**.
   - **Public hostname settings**:
     - **Subdomain**: `monitoring`
     - **Domain**: `hasb.dev`
     - **Path**: Leave empty
   - **Service settings**:
     - **Type**: `HTTP`
     - **URL**: `localhost:3000` (or `127.0.0.1:3000`)
   - Click **Save hostname**.

---

### Part 3: Deploy Cloudflare Tunnel Connector via Ansible

Execute Play 4 from the Ansible Controller (`10.0.0.135`):

```bash
# Option A: Injected securely via Infisical CLI
infisical run \
  --projectId="6c8dad30-9f25-44dd-ae65-08c06580ceed" \
  --env=prod \
  --path=/ansible \
  -- ansible-playbook -i inventory.ini playbook.yml --tags cloudflare

# Option B: Run with exported local environment variables
GRAFANA_ADMIN_PASSWORD="<grafana_password>" \
CLOUDFLARE_TUNNEL_TOKEN="<tunnel_token>" \
ansible-playbook -i inventory.ini playbook.yml
```

The playbook executes:
1. **Preflight Assertion**: Verifies `CLOUDFLARE_TUNNEL_TOKEN` is present, valid length, and non-placeholder.
2. **Container Pull**: Fetches `cloudflare/cloudflared:2024.8.3`.
3. **Container Launch**: Deploys `cloudflared` with `network_mode: host` and `restart_policy: unless-stopped`.
4. **Health Inspection**: Queries the Docker daemon to confirm `cloudflared` is active and running.

---

## Future IaC Expansion: Cloudflare Terraform Provider

While the baseline uses Cloudflare Console for control-plane configuration to
maintain decoupling and avoid upfront API token bootstrapping, the control plane
is designed to be managed via Terraform in a later expansion.

### Provider Declaration

```hcl
# terraform/cloudflare.tf (or a dedicated root module terraform-cloudflare/)
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.39.0"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
```

### DNS Record via Terraform

```hcl
resource "cloudflare_record" "web" {
  zone_id = var.cloudflare_zone_id
  name    = "web"
  content = aws_eip.web.public_ip
  type    = "A"
  proxied = true
  ttl     = 1
}
```

### Zero Trust Tunnel via Terraform

```hcl
resource "random_id" "tunnel_secret" {
  byte_length = 35
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "monitoring_tunnel" {
  account_id = var.cloudflare_account_id
  name       = "devops-monitoring-tunnel"
  secret     = random_id.tunnel_secret.b64_std
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "monitoring_tunnel_cfg" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.monitoring_tunnel.id

  config {
    ingress_rule {
      hostname = "monitoring.${var.domain_name}"
      service  = "http://localhost:3000"
    }
    ingress_rule {
      service = "http_status:404"
    }
  }
}

resource "cloudflare_record" "monitoring_cname" {
  zone_id = var.cloudflare_zone_id
  name    = "monitoring"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.monitoring_tunnel.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

output "cloudflare_tunnel_token" {
  value     = cloudflare_zero_trust_tunnel_cloudflared.monitoring_tunnel.tunnel_token
  sensitive = true
}
```

### Decoupling Recommendation
Keep the Cloudflare Terraform configuration in a separate workspace or root
module (e.g., `terraform/cloudflare/`) using `terraform_remote_state` to read
`aws_eip.web.public_ip` from the AWS state file. This prevents Cloudflare API token
requirements from blocking AWS infrastructure lifecycle tasks.

---

## Verification

### 1. DNS Resolution & Edge Proxy Check

Test whether `web.hasb.dev` resolves to Cloudflare Anycast edge IP addresses
rather than exposing the real Elastic IP:

```bash
dig web.hasb.dev +short
```

- **Proxied Output (Expected)**: Returns Cloudflare edge IPs (e.g., `104.21.x.x`, `172.67.x.x`). The AWS Elastic IP is hidden.
- **DNS-Only (Grey Cloud diagnostic test)**: Returns the raw AWS Elastic IP (`aws_eip.web.public_ip`).

### 2. Web Application HTTPS Verification

Verify HTTP-to-HTTPS redirection and TLS termination at Cloudflare edge:

```bash
curl -Iv https://web.hasb.dev
```

Expected response headers:
```text
HTTP/2 200
server: cloudflare
cf-ray: ...
```

### 3. Monitoring Dashboard Zero-Trust Access

Verify Grafana UI is accessible via Cloudflare Tunnel over public HTTPS:

```bash
curl -Iv https://monitoring.hasb.dev/api/health
```

Expected response:
```text
HTTP/2 200
content-type: application/json
{"commit":"...","database":"ok","version":"11.1.0"}
```

### 4. Zero Inbound Ports Verification on Monitoring EC2

Verify that AWS Security Group `devops-private-sg` has **no** open inbound ports
from the public internet (`0.0.0.0/0`):

```bash
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=devops-private-sg" \
  --query "SecurityGroups[0].IpPermissions" \
  --output json
```

Expected output: Ports 9090 and 3000 allow traffic strictly from inside the VPC
CIDR (`10.0.0.0/24`) or the Web Server (`10.0.0.5/32`). No inbound rule exposes port
3000 to `0.0.0.0/0`.

### 5. Host Container Status on Monitoring EC2

```bash
docker ps --filter "name=cloudflared" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Inspect connection establishment in `cloudflared` container logs:

```bash
docker logs --tail 20 cloudflared
```

Expected log indicators:
```text
INF Registered tunnel connection connIndex=0 connection=... ip=... location=SIN
INF Registered tunnel connection connIndex=1 connection=... ip=... location=KUL
INF Updated to new configuration config="..."
```

---

## Troubleshooting

### Cloudflare Error 521: Web Server Is Down
- **Cause**: Cloudflare Edge cannot connect to origin Web EC2 on port 80 or 443.
- **Resolution**:
  1. Verify the web container is running: `docker ps --filter name=devops-web-app`.
  2. Verify Web EC2 security group allows inbound port 80 from `0.0.0.0/0`.
  3. Verify local curl on Web EC2 responds: `curl -I http://127.0.0.1:80`.

### Cloudflare Error 522: Connection Timed Out
- **Cause**: Cloudflare SSL mode is set to `Full`, but the origin server does not
  listen on port 443 or negotiate TLS.
- **Resolution**: In Cloudflare Dashboard -> SSL/TLS -> Overview, ensure mode is set
  to **Flexible** until origin HTTPS certificates are provisioned.

### Cloudflare Error 1033: Cloudflare Tunnel Error
- **Cause**: The `cloudflared` daemon is not running on the Monitoring EC2, or it is
  unable to communicate with Cloudflare edge.
- **Resolution**:
  1. Check container state: `docker inspect --format='{{.State.Running}}' cloudflared`.
  2. Check outbound NAT connectivity from private subnet: `curl -I https://cloudflare.com`.
  3. Verify the tunnel token matches the active tunnel registered in Cloudflare Zero Trust dashboard.

### Grafana Host Header / Redirect Mismatch
- **Cause**: Grafana redirects users to `localhost:3000` instead of `https://monitoring.hasb.dev`.
- **Resolution**: Confirm `GF_SERVER_ROOT_URL=https://monitoring.hasb.dev` is set in
  `/opt/monitoring/compose.yaml`. Re-run `docker compose up -d` to recreate the
  Grafana container.
