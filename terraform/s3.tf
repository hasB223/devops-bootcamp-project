# ==============================================================================
# Dedicated S3 Bucket for Transient Ansible SSM File & Module Transfers
# ==============================================================================
resource "aws_s3_bucket" "ansible_ssm" {
  bucket        = "devops-bootcamp-ansible-ssm-${var.owner_slug}"
  force_destroy = true

  tags = {
    Name        = "devops-bootcamp-ansible-ssm-${var.owner_slug}"
    Purpose     = "Ansible SSM Transport Relay"
    Environment = var.environment
  }
}

# Versioning explicitly suspended to prevent transient payloads/tokens from lingering
resource "aws_s3_bucket_versioning" "ansible_ssm" {
  bucket = aws_s3_bucket.ansible_ssm.id

  versioning_configuration {
    status = "Suspended"
  }
}

# Server-Side Encryption (AES256)
resource "aws_s3_bucket_server_side_encryption_configuration" "ansible_ssm" {
  bucket = aws_s3_bucket.ansible_ssm.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "ansible_ssm" {
  bucket = aws_s3_bucket.ansible_ssm.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Automated lifecycle cleanup: expire objects after 1 day and abort incomplete multipart uploads
resource "aws_s3_bucket_lifecycle_configuration" "ansible_ssm" {
  bucket = aws_s3_bucket.ansible_ssm.id

  rule {
    id     = "purge-transient-ssm-payloads"
    status = "Enabled"

    filter {}

    expiration {
      days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}
