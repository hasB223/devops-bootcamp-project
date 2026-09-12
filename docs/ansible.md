# Ansible Configuration Management Runbook

This document describes the automated configuration management layer for the DevOps capstone infrastructure, orchestrated via **Ansible** from a dedicated **Ansible Controller** node to private VPC targets.

---

## Purpose

This layer automates server provisioning, container runtime setup, and application deployment across AWS instances:

- **Centralized Execution**: All configurations are initiated strictly from the private **Ansible Controller** (`10.0.0.135`), not from local engineer workstations.
- **Role-Based Docker Installation**: Uses the battle-tested, official Ansible Galaxy role `geerlingguy.docker` to deploy and manage Docker Engine and Compose plugins.
- **Private ECR Integration**: Authenticates to AWS Elastic Container Registry (ECR) using EC2 IAM instance profile credentials (no hardcoded static keys).
- **Application Deployment**: Pulls the multi-stage Three.js web application image from ECR and runs it as a daemonized container with port 80 exposed.
- **Idempotency Guarantee**: All tasks and plays converge to a steady state such that consecutive playbook runs yield `changed=0`.
- **Zero Inbound SSH (Ansible over SSM)**: Inter-node configuration management uses the AWS Systems Manager transport plugin (`amazon.aws.aws_ssm`), completely eliminating the need for inbound SSH port 22 in Security Groups. Workstation access to the Controller is mediated via SSM Session Manager.
- **Break-Glass SSH Capability**: A Terraform variable (`enable_ssh_ingress`, default `false`) provides break-glass VPC SSH ingress if ever required for emergency recovery.

---

## Architecture

```text
                                  +---------------------------------------+
                                  |         Engineer Workstation          |
                                  +---------------------------------------+
                                                      |
                                         AWS SSM Session Manager
                                         (No port 22 from Internet)
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |     Ansible Controller (Private)      |
                                  |             10.0.0.135                |
                                  +---------------------------------------+
                                            |                  |
                       HTTPS 443 (SSM)      |                  |   HTTPS 443 (SSM)
                       No port 22 required  |                  |   No port 22 required
                                            v                  v
                               +------------------------------------+
                               |     AWS Systems Manager API /      |
                               |      S3 Relay VPC Endpoint         |
                               +------------------------------------+
                                            /                  \
                                           v                    v
            +------------------------------------+    +------------------------------------+
            |        Web Server (Public)         |    |     Monitoring Server (Private)    |
            |             10.0.0.5               |    |             10.0.0.136             |
            |  - Docker Engine                   |    |  - Docker Engine                   |
            |  - Web Container (Port 80)         |    |  - /opt/monitoring directory       |
            |  - IAM Profile: ECR ReadOnly       |    |  - IAM Profile: SSM Managed        |
            +------------------------------------+    +------------------------------------+
```

!!! note "Evolution from Baseline"
    The capstone baseline initially utilized internal VPC SSH (`port 22`) from the Ansible Controller. Under the **Ansible over SSM (+3%)** track, transport was upgraded to `amazon.aws.aws_ssm` over encrypted AWS SSM HTTPS endpoints, allowing port 22 to be closed by default in all security groups.

---

## Files

All configuration assets reside in `ansible/`:

```text
ansible/
├── ansible.cfg              # Ansible defaults: inventory, SSH optimization, role paths
├── requirements.yml         # Galaxy dependencies (geerlingguy.docker, community.docker, amazon.aws)
├── inventory.ini.example    # Tracked reference inventory specifying internal VPC hosts (SSH fallback)
├── inventory-ssm.ini.example # Tracked SSM inventory targeting EC2 Instance IDs via amazon.aws.aws_ssm
├── inventory.ini            # Live inventory file (gitignored to avoid committing dynamic state)
├── group_vars/
│   └── all.yml              # Global variables (AWS region, ECR URIs, container definitions)
└── playbook.yml             # Master playbook with 3 distinct plays: Docker, Web App, Monitoring
```

---

## Inputs & Variables

The following parameters are declared in `ansible/group_vars/all.yml` and `ansible/inventory.ini`:

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Controller Private IP** | `10.0.0.135` | Host executing Ansible playbooks |
| **Web Server Private IP** | `10.0.0.5` | Target running web application container |
| **Monitoring Server Private IP** | `10.0.0.136` | Target prepared for Prometheus/Grafana stack |
| **AWS Region** | `ap-southeast-1` | Target AWS deployment region |
| **ECR Registry** | `164824552037.dkr.ecr.ap-southeast-1.amazonaws.com` | Private container registry |
| **App Image** | `devops-bootcamp/final-project-hasb:latest` | Application repository and tag |
| **Docker Role** | `geerlingguy.docker` (v7.4.4) | Ansible Galaxy role for Docker Engine |
| **Docker Users** | `ubuntu`, `ssm-user` | Users added to the `docker` group |
| **App Host Port** | `80` | Public HTTP listening port on web server |

---

## Steps

### 1. Connect to Ansible Controller via SSM

Because the Ansible Controller resides in a private subnet with no public IP, connect via AWS Systems Manager Session Manager:

```bash
# Retrieve Controller Instance ID
CONTROLLER_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=ansible-controller" "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text)

# Start SSM interactive session
aws ssm start-session --target "$CONTROLLER_ID"
```

Once inside the session, switch to the `ubuntu` user:

```bash
sudo su - ubuntu
```

---

### 2. Configure Inventory and SSH Key

On the Ansible Controller, clone the repository (or pull down the configuration) and configure the private SSH key:

```bash
# Clone repository
git clone https://github.com/hasB223/devops-bootcamp-project.git
cd devops-bootcamp-project/ansible

# Copy template inventory to live inventory
cp inventory.ini.example inventory.ini

# Ensure SSH private key is present with restricted permissions
chmod 600 ~/.ssh/devops-bootcamp-key
```

Verify that `inventory.ini` targets match the internal VPC private IPs:

```ini
[web]
web-server ansible_host=10.0.0.5

[monitoring]
monitoring-server ansible_host=10.0.0.136

[targets:children]
web
monitoring

[targets:vars]
ansible_user=ubuntu
ansible_ssh_private_key_file=~/.ssh/devops-bootcamp-key
ansible_python_interpreter=/usr/bin/python3
```

---

### 3. Install Galaxy Dependencies

Install the official `geerlingguy.docker` role and the `community.docker` collection declared in `requirements.yml`:

```bash
# Install role to local roles directory
ansible-galaxy role install -r requirements.yml -p ./roles

# Install collection
ansible-galaxy collection install -r requirements.yml
```

---

### 4. Test Connectivity with Ad-hoc Ping

Run the ad-hoc `ping` module against all targets:

```bash
ansible all -m ping
```

**Expected Output:**

```json
web-server | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "ping": "pong"
}
monitoring-server | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "ping": "pong"
}
```

Both targets return `pong` without errors.

---

### 5. Execute the Master Configuration Playbook

Run `ansible-playbook` to configure Docker, deploy the containerized web app, and verify endpoints:

```bash
ansible-playbook playbook.yml
```

**Execution Flow:**
1. **Play 1 (`targets`)**: Updates package caches, installs prerequisites (`python3-docker`, `curl`, AWS CLI v2), runs `geerlingguy.docker` to install Docker CE, and enables the systemd service.
2. **Play 2 (`web`)**: Uses the web server's IAM instance profile to obtain an ECR authorization token, logs into the private registry, pulls `devops-bootcamp/final-project-hasb:latest`, starts container `devops-web-app` bound to port 80, and checks HTTP 200 response.
3. **Play 3 (`monitoring`)**: Verifies Docker daemon functionality on the monitoring server and provisions `/opt/monitoring` for the future Prometheus/Grafana stack.

---

### 6. Verify Idempotency

Execute the playbook a second time immediately after the initial run:

```bash
ansible-playbook playbook.yml
```

**Expected Result:**

```text
PLAY RECAP *********************************************************************
monitoring-server          : ok=11   changed=0    unreachable=0    failed=0    skipped=2    rescued=0    ignored=1
web-server                 : ok=15   changed=0    unreachable=0    failed=0    skipped=2    rescued=0    ignored=1
```

The second sequential execution reports **`changed=0`**, satisfying the idempotency requirement.

---

### 7. Verify Web Application Endpoint

Verify that the web application responds with `HTTP/1.1 200 OK` both from within the VPC and externally via the Elastic IP:

```bash
# Internal check from Ansible Controller
curl -I http://10.0.0.5:80

# External check from workstation
curl -I http://<WEB_ELASTIC_IP>:80
```

**Expected Response:**

```http
HTTP/1.1 200 OK
Server: nginx/1.31.3
Content-Type: text/html
Content-Length: 404
Connection: keep-alive
```

---

## Bonus: Ansible without Port 22 (AWS Systems Manager Plugin)

To satisfy the **+3% bonus** for running Ansible without port 22 open:

### 1. Transport Architecture
Ansible uses the official `amazon.aws.aws_ssm` connection plugin to execute tasks and modules via AWS Systems Manager Session Manager WebSocket connections (`ssm:StartSession`, `ssm:TerminateSession`) over HTTPS 443:
- **Zero Port 22 Ingress**: Port 22 is completely closed by default in `devops-public-sg` and `devops-private-sg`.
- **Dedicated S3 Transit Relay**: A dedicated bucket (`devops-bootcamp-ansible-ssm-hasb`) is provisioned with versioning explicitly suspended and a 1-day lifecycle purge rule.
- **S3 VPC Gateway Endpoint**: An `aws_vpc_endpoint.s3` gateway endpoint routes all S3 traffic across the private AWS network at zero cost ($0.00/mo), bypassing NAT data transfer fees.
- **Break-Glass SSH Capability**: A Terraform variable (`enable_ssh_ingress`, default `false`) provides dynamic port 22 restoration for emergency administrative recovery:
  ```bash
  terraform -chdir=terraform apply -var="enable_ssh_ingress=true"
  ```

### 2. Controller Runtime Prerequisites
On the Ansible Controller (`ansible-controller`, Ubuntu 24.04 LTS):
```bash
# 1. Install AWS Session Manager Plugin
which session-manager-plugin || {
  curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "/tmp/session-manager-plugin.deb"
  sudo dpkg -i /tmp/session-manager-plugin.deb
}

# 2. Install Python AWS SDK
python3 -c "import boto3, botocore" || pip install boto3 botocore

# 3. Install Ansible AWS Collection
ansible-galaxy collection install -r requirements.yml
```

### 3. Inventory Configuration (`inventory-ssm.ini`)
Target EC2 instances using their Instance IDs:
```ini
[web]
web-server ansible_host=i-0128d6c619f0f8684

[monitoring]
monitoring-server ansible_host=i-0054eda9287d889ff

[targets:children]
web
monitoring

[targets:vars]
ansible_connection=amazon.aws.aws_ssm
ansible_aws_ssm_region=ap-southeast-1
ansible_aws_ssm_bucket_name=devops-bootcamp-ansible-ssm-hasb
ansible_aws_ssm_s3_addressing_style=auto
ansible_python_interpreter=/usr/bin/python3
```

### 4. IAM Scoping & Prefix Isolation
The Ansible Controller role (`devops-controller-role`) is granted scoped permissions:
- `ssm:StartSession`, `ssm:SendCommand` strictly on target instance ARNs and standard SSM documents.
- `ssm:TerminateSession`, `ssm:ResumeSession`, `ssm:DescribeInstanceInformation` for session lifecycle management.
- `ssmmessages:CreateControlChannel`, `ssmmessages:CreateDataChannel`, `ssmmessages:OpenControlChannel`, `ssmmessages:OpenDataChannel` on `*` (required by AWS Session Manager client to open WebSocket communication channels).
- `s3:GetBucketLocation` and `s3:ListBucket` on the bucket ARN (required for `HeadBucket` bucket-level region and accessibility validation by `amazon.aws.aws_ssm`).
- `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` restricted strictly to `arn:aws:s3:::devops-bootcamp-ansible-ssm-hasb/i-*`.

!!! note
    `HeadBucket` checks bucket existence and region without passing an `s3:prefix` context key. Object payloads remain strictly isolated under the instance ID prefix `i-*`.

### 5. Target Node Sudoers Bootstrap (Rebuild / Recovery Procedure)
Target instances (`web` and `monitoring`) provisioned via Terraform automatically configure passwordless sudo for `ssm-user` via cloud-init `user_data` using a dedicated `ansible-admin` group. If target nodes are ever rebuilt or recovered manually without cloud-init, execute this one-time bootstrap from your workstation:

```bash
aws ssm send-command \
  --targets "Key=tag:Role,Values=web,monitoring" \
  --document-name "AWS-RunShellScript" \
  --comment "Bootstrap ssm-user passwordless sudo for Ansible" \
  --parameters 'commands=[
    "set -e",
    "groupadd -f ansible-admin",
    "id ssm-user >/dev/null 2>&1 || useradd -m -s /bin/bash ssm-user",
    "usermod -aG ansible-admin ssm-user",
    "echo \"%ansible-admin ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/ansible-admin",
    "chmod 0440 /etc/sudoers.d/ansible-admin",
    "visudo -cf /etc/sudoers.d/ansible-admin"
  ]'
```

### 6. Execution
```bash
# Test connectivity via SSM ad-hoc ping
ansible -i inventory-ssm.ini targets -m ping

# Execute configuration playbook over SSM
ansible-playbook -i inventory-ssm.ini playbook.yml
```

---

## Verification Checklist

- [x] Controller is located at `10.0.0.135` in private subnet.
- [x] Target inventory lists `10.0.0.5` and `10.0.0.136`.
- [x] `ansible all -m ping` returns `pong` from both targets.
- [x] Docker installed via official `geerlingguy.docker` Galaxy role.
- [x] Container image pulled from private AWS ECR using IAM instance profile credentials.
- [x] Web container running on port 80 with healthy status.
- [x] HTTP request to `http://10.0.0.5:80` returns `200 OK`.
- [x] Sequential playbook run yields `changed=0` (Idempotent).

---

## Troubleshooting

| Symptom | Cause | Remediation |
| :--- | :--- | :--- |
| **`Permission denied (publickey)`** | Incorrect permissions or wrong SSH key path | Ensure SSH key on controller has `chmod 600` and matches the EC2 `key_name` deployed via Terraform. |
| **`Host key verification failed`** | Host checking enabled on fresh instance | Ensure `ansible.cfg` has `host_key_checking = False`. |
| **`docker: command not found`** | PATH not refreshed or role failed | Ensure `geerlingguy.docker` completed successfully and user belongs to `docker` group. |
| **`Cannot connect to the Docker daemon`** | Group permissions not active in current subshell | Log out and back into the shell, or prepend tasks with `become: true`. |
| **`ECR Login Denied`** | Missing IAM policy on EC2 instance | Confirm `AmazonEC2ContainerRegistryReadOnly` is attached to instance profile in `terraform/iam.tf`. |
| **`changed > 0 on rerun`** | Non-idempotent task (e.g. bare shell command) | Ensure commands use `changed_when: false` or declarative Ansible modules (`community.docker.docker_container`). |
