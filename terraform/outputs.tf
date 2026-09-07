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
