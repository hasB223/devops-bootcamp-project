terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    bucket       = "devops-bootcamp-terraform-hasb"
    key          = "foundation/terraform.tfstate"
    region       = "ap-southeast-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "devops-bootcamp-project"
      ManagedBy   = "terraform"
      Owner       = var.owner_slug
      Environment = var.environment
    }
  }
}

data "aws_caller_identity" "current" {}
