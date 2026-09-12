# Terraform Foundation Infrastructure

This document describes the foundational AWS infrastructure for the DevOps Bootcamp final project, provisioned declaratively via Terraform.

## Purpose

This layer owns the base cloud environment in AWS region `ap-southeast-1`:

- Remote state backend in S3 with state locking
- Virtual Private Cloud (`devops-vpc`) with split public and private subnets
- Egress connectivity via Internet Gateway (`devops-igw`) and NAT Gateway (`devops-ngw`)
- Strict security groups (`devops-public-sg`, `devops-private-sg`)
- Identity and Access Management (IAM) instance profiles for SSM Session Manager and ECR access
- Three EC2 virtual machines with fixed static private IP addresses
- Elastic IP allocation for the public Web server
- Private Elastic Container Registry (ECR) repository for Docker images

## Files

All infrastructure code resides in the `terraform/` directory:

```text
terraform/
├── providers.tf            # AWS provider and remote S3 backend
├── variables.tf            # Configurable inputs and defaults
├── network.tf              # VPC, subnets, IGW, NAT gateway, route tables
├── security.tf             # Security group ingress/egress firewall rules
├── iam.tf                  # EC2 SSM and ECR instance profile roles
├── ec2.tf                  # Compute instances (web, controller, monitoring)
├── ecr.tf                  # Container registry and image lifecycle
├── outputs.tf              # Exported IDs, IP addresses, and repository URLs
└── terraform.tfvars.example# Reference variable definitions
```

## Inputs

| Name | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `aws_region` | string | `ap-southeast-1` | Target AWS region |
| `owner_slug` | string | `hasb` | Unique slug for project resource identification, bucket, and ECR naming |
| `environment` | string | `dev` | Deployment environment identifier (e.g. `dev`, `lab`) |
| `vpc_cidr` | string | `10.0.0.0/24` | CIDR block for devops-vpc |
| `public_subnet_cidr` | string | `10.0.0.0/25` | CIDR block for devops-public-subnet |
| `private_subnet_cidr` | string | `10.0.0.128/25` | CIDR block for devops-private-subnet |
| `web_private_ip` | string | `10.0.0.5` | Static private IP for Web Server |
| `controller_private_ip` | string | `10.0.0.135` | Static private IP for Ansible Controller |
| `monitoring_private_ip` | string | `10.0.0.136` | Static private IP for Monitoring Server |
| `instance_type` | string | `t3.micro` | Instance size for all three servers |

## Steps

### 1. Prerequisites & Installation

#### Install Terraform (macOS / Homebrew)

If Terraform is not installed on the host machine, install it via HashiCorp's official tap (Terraform resides in HashiCorp's tap rather than `homebrew-core`):

```bash
# 2. Terraform, from HashiCorp's official tap
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

Verify the installation:

```bash
terraform version
```

#### AWS Authentication & Remote State Setup (One-Time Bootstrap)

!!! note "Bootstrap Context (The Chicken-and-Egg Problem)"
    Terraform needs an S3 bucket to store its remote state (`terraform.tfstate`) and track resources. However, it cannot declare and create its own backend storage bucket within the same module where that backend is consumed. Therefore, the S3 state bucket is provisioned once via the AWS CLI as a prerequisite bootstrap step. All subsequent infrastructure (VPC, Subnets, Gateways, EC2 instances, Security Groups, IAM, and ECR) is managed 100% declaratively through Terraform.

Ensure your local shell has AWS credentials configured:

```bash
export AWS_REGION=ap-southeast-1
```

Confirm or create the S3 state bucket `devops-bootcamp-terraform-hasb` with versioning enabled:

```bash
# Check if bucket exists
aws s3api head-bucket --bucket devops-bootcamp-terraform-hasb 2>/dev/null || {
  # Create bucket in ap-southeast-1
  aws s3api create-bucket \
    --bucket devops-bootcamp-terraform-hasb \
    --region ap-southeast-1 \
    --create-bucket-configuration LocationConstraint=ap-southeast-1

  # Enable versioning for state recovery and safety
  aws s3api put-bucket-versioning \
    --bucket devops-bootcamp-terraform-hasb \
    --versioning-configuration Status=Enabled
}
```

### 2. Initialize Terraform

```bash
cd terraform
terraform init
```

### 3. Format and Validate

```bash
terraform fmt -check
terraform validate
```

### 4. Review Plan

```bash
terraform plan
```

Verify that:

- 1 VPC, 2 Subnets, 1 IGW, 1 NAT Gateway, 2 Route Tables are planned
- 2 Security groups (`devops-public-sg` with port 80 public & 9100 restricted to `10.0.0.136`; `devops-private-sg`)
- 3 EC2 instances with assigned IPs (`10.0.0.5`, `10.0.0.135`, `10.0.0.136`)
- 1 ECR repository (`devops-bootcamp/final-project-hasb`)

### 5. Apply Infrastructure

```bash
terraform apply
```

### 6. Destruction Safety

When tearing down the environment at the end of testing or lifecycle:

```bash
terraform destroy
```

## Verification

After applying, confirm the following items:

```bash
terraform output
```

### Checklist
- [ ] `vpc_id` matches CIDR `10.0.0.0/24`
- [ ] `web_private_ip` is `10.0.0.5` and has an Elastic IP assigned (`web_public_ip`)
- [ ] `controller_private_ip` is `10.0.0.135` and has NO public IP
- [ ] `monitoring_private_ip` is `10.0.0.136` and has NO public IP
- [ ] `devops-public-sg` opens port 80 to `0.0.0.0/0`, port 9100 only to `10.0.0.136/32`, and port 22 only to `10.0.0.0/24`
- [ ] `devops-private-sg` opens port 22 only to `10.0.0.0/24`
- [ ] All instances connect via AWS Systems Manager Session Manager (zero open SSH port required to the internet)
- [ ] ECR repository `devops-bootcamp/final-project-hasb` is active with scan on push enabled

## Troubleshooting

- **NAT Gateway EIP dependency**:
  NAT Gateway requires an Elastic IP and depends on the Internet Gateway being attached first. This is handled explicitly via `depends_on = [aws_internet_gateway.gw]`.
- **SSM connection delay**:
  When EC2 instances first launch, the Amazon SSM Agent takes 1–2 minutes to register with the Systems Manager service.
- **Port 9100 security alert**:
  Port 9100 is strictly bound to `10.0.0.136/32`. Never allow `0.0.0.0/0` on port 9100 as it exposes host metrics to the internet and violates security best practices.
