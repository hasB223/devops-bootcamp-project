variable "aws_region" {
  description = "AWS deployment region"
  type        = string
  default     = "ap-southeast-1"
}

variable "owner_slug" {
  description = "Owner slug identifier for unique resource naming"
  type        = string
  default     = "hasb"
}

variable "environment" {
  description = "Deployment environment identifier (e.g. dev, lab, prod)"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/24"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.0.0.0/25"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet"
  type        = string
  default     = "10.0.0.128/25"
}

variable "web_private_ip" {
  description = "Fixed private IP address for Web EC2 instance"
  type        = string
  default     = "10.0.0.5"
}

variable "controller_private_ip" {
  description = "Fixed private IP address for Ansible Controller EC2 instance"
  type        = string
  default     = "10.0.0.135"
}

variable "monitoring_private_ip" {
  description = "Fixed private IP address for Monitoring EC2 instance"
  type        = string
  default     = "10.0.0.136"
}

variable "instance_type" {
  description = "EC2 instance type for all nodes"
  type        = string
  default     = "t3.micro"
}
