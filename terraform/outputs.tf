# ==============================================================================
# Network Outputs
# ==============================================================================
output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "The ID of the public subnet"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "The ID of the private subnet"
  value       = aws_subnet.private.id
}

# ==============================================================================
# Compute Outputs
# ==============================================================================
output "web_public_ip" {
  description = "Elastic IP of the Web Server"
  value       = aws_eip.web.public_ip
}

output "web_private_ip" {
  description = "Private IP of the Web Server"
  value       = aws_instance.web.private_ip
}

output "controller_private_ip" {
  description = "Private IP of the Ansible Controller"
  value       = aws_instance.controller.private_ip
}

output "monitoring_private_ip" {
  description = "Private IP of the Monitoring Server"
  value       = aws_instance.monitoring.private_ip
}

# ==============================================================================
# ECR Outputs
# ==============================================================================
output "ecr_repository_url" {
  description = "The URL of the ECR repository"
  value       = aws_ecr_repository.app.repository_url
}

# ==============================================================================
# Ansible Outputs
# ==============================================================================
output "ansible_inventory" {
  description = "Generated inventory content for Ansible controller"
  value       = <<-EOT
    [web]
    web-server ansible_host=${aws_instance.web.private_ip}

    [monitoring]
    monitoring-server ansible_host=${aws_instance.monitoring.private_ip}

    [targets:children]
    web
    monitoring

    [targets:vars]
    ansible_user=ubuntu
    ansible_ssh_private_key_file=~/.ssh/devops-bootcamp-key
  EOT
}

# ==============================================================================
# Compute Instance IDs (for SSM Targeting)
# ==============================================================================
output "web_instance_id" {
  description = "EC2 Instance ID of the Web Server"
  value       = aws_instance.web.id
}

output "monitoring_instance_id" {
  description = "EC2 Instance ID of the Monitoring Server"
  value       = aws_instance.monitoring.id
}

output "controller_instance_id" {
  description = "EC2 Instance ID of the Ansible Controller"
  value       = aws_instance.controller.id
}

output "ansible_ssm_bucket_name" {
  description = "Dedicated S3 bucket for Ansible SSM transport relay"
  value       = aws_s3_bucket.ansible_ssm.bucket
}

# ==============================================================================
# CI/CD Outputs
# ==============================================================================
output "github_actions_role_arn" {
  description = "Legacy IAM Role ARN retained temporarily during scoped-role migration"
  value       = aws_iam_role.github_actions.arn
}

output "github_actions_ecr_publisher_role_arn" {
  description = "IAM role ARN for publishing container images from main"
  value       = aws_iam_role.github_actions_scoped["ecr_publisher"].arn
}

output "github_actions_ssm_deployer_role_arn" {
  description = "IAM role ARN for production-environment SSM deployments"
  value       = aws_iam_role.github_actions_scoped["ssm_deployer"].arn
}

output "github_actions_lifecycle_mutator_role_arn" {
  description = "IAM role ARN for platform park and unpark operations"
  value       = aws_iam_role.github_actions_scoped["lifecycle_mutator"].arn
}

output "github_actions_status_readonly_role_arn" {
  description = "IAM role ARN for read-only platform status checks"
  value       = aws_iam_role.github_actions_scoped["status_readonly"].arn
}

output "github_actions_terraform_planner_role_arn" {
  description = "IAM role ARN for read-only pull-request Terraform plans"
  value       = aws_iam_role.github_actions_scoped["terraform_planner"].arn
}

# ==============================================================================
# Ansible SSM Inventory Output
# ==============================================================================
output "ansible_ssm_inventory" {
  description = "Generated SSM inventory content for Ansible controller"
  value       = <<-EOT
    [web]
    web-server ansible_host=${aws_instance.web.id}

    [monitoring]
    monitoring-server ansible_host=${aws_instance.monitoring.id}

    [targets:children]
    web
    monitoring

    [targets:vars]
    ansible_connection=amazon.aws.aws_ssm
    ansible_aws_ssm_region=${var.aws_region}
    ansible_aws_ssm_bucket_name=${aws_s3_bucket.ansible_ssm.bucket}
    ansible_aws_ssm_s3_addressing_style=auto
    ansible_python_interpreter=/usr/bin/python3
  EOT
}
