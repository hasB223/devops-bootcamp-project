# ==============================================================================
# AMI Lookup: Ubuntu 24.04 LTS (Noble Numbat)
# ==============================================================================
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Target Node Bootstrap: Hardened sudoers group for ssm-user (required by Ansible become over SSM)
locals {
  target_user_data = <<-EOF
    #!/bin/bash
    set -e
    groupadd -f ansible-admin
    id ssm-user >/dev/null 2>&1 || useradd -m -s /bin/bash ssm-user
    usermod -aG ansible-admin ssm-user
    echo "%ansible-admin ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ansible-admin
    chmod 0440 /etc/sudoers.d/ansible-admin
    visudo -cf /etc/sudoers.d/ansible-admin
  EOF
}

# ==============================================================================
# 1. Web EC2 Instance (Public Subnet, 10.0.0.5)
# ==============================================================================
resource "aws_instance" "web" {
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = var.instance_type
  key_name             = var.key_name
  subnet_id            = aws_subnet.public.id
  private_ip           = var.web_private_ip
  iam_instance_profile = aws_iam_instance_profile.web_profile.name

  vpc_security_group_ids = [
    aws_security_group.public.id
  ]

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  user_data                   = local.target_user_data
  user_data_replace_on_change = false

  tags = {
    Name     = "web-server"
    Role     = "web"
    AutoPark = "true"
  }
}

# Elastic IP for Web Server
resource "aws_eip" "web" {
  domain   = "vpc"
  instance = aws_instance.web.id

  tags = {
    Name = "devops-web-eip"
  }

  depends_on = [aws_internet_gateway.gw]
}

# ==============================================================================
# 2. Ansible Controller EC2 Instance (Private Subnet, 10.0.0.135)
# ==============================================================================
resource "aws_instance" "controller" {
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = var.instance_type
  key_name             = var.key_name
  subnet_id            = aws_subnet.private.id
  private_ip           = var.controller_private_ip
  iam_instance_profile = aws_iam_instance_profile.controller_profile.name

  vpc_security_group_ids = [
    aws_security_group.private.id
  ]

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = {
    Name     = "ansible-controller"
    Role     = "controller"
    AutoPark = "true"
  }
}

# ==============================================================================
# 3. Monitoring EC2 Instance (Private Subnet, 10.0.0.136)
# ==============================================================================
resource "aws_instance" "monitoring" {
  ami                  = data.aws_ami.ubuntu.id
  instance_type        = var.instance_type
  key_name             = var.key_name
  subnet_id            = aws_subnet.private.id
  private_ip           = var.monitoring_private_ip
  iam_instance_profile = aws_iam_instance_profile.monitoring_profile.name

  vpc_security_group_ids = [
    aws_security_group.private.id
  ]

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  user_data                   = local.target_user_data
  user_data_replace_on_change = false

  tags = {
    Name     = "monitoring-server"
    Role     = "monitoring"
    AutoPark = "true"
  }
}
