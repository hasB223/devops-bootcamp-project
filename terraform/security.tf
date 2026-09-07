# ==============================================================================
# Public Security Group (Web Server)
# ==============================================================================
resource "aws_security_group" "public" {
  name        = "devops-public-sg"
  description = "Security group for public web server"
  vpc_id      = aws_vpc.main.id

  # HTTP port 80 exposed publicly
  ingress {
    description = "Public HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Port 9100 strictly restricted to Monitoring EC2 (10.0.0.136)
  ingress {
    description = "Node Exporter from Monitoring Server only"
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    cidr_blocks = ["${var.monitoring_private_ip}/32"]
  }

  # SSH port 22 from VPC CIDR only
  ingress {
    description = "SSH from VPC subnet"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "devops-public-sg"
  }
}

# ==============================================================================
# Private Security Group (Controller and Monitoring Server)
# ==============================================================================
resource "aws_security_group" "private" {
  name        = "devops-private-sg"
  description = "Security group for private controller and monitoring servers"
  vpc_id      = aws_vpc.main.id

  # SSH port 22 from VPC CIDR only
  ingress {
    description = "SSH from VPC subnet"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Allow internal traffic between private nodes
  ingress {
    description = "Internal communication between private instances"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    description = "Allow all outbound traffic via NAT"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "devops-private-sg"
  }
}
