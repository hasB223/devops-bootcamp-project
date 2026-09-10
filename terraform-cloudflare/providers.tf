terraform {
  required_version = ">= 1.10"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket = "devops-bootcamp-terraform-hasb"
    key    = "cloudflare/terraform.tfstate"
    region = "ap-southeast-1"
  }
}

# Authenticates automatically via CLOUDFLARE_API_TOKEN environment variable
provider "cloudflare" {}
