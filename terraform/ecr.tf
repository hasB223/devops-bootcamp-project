# ==============================================================================
# ECR Private Repository
# ==============================================================================
resource "aws_ecr_repository" "app" {
  name = "devops-bootcamp/final-project-${var.owner_slug}"
  # SHA-tagged images are immutable once pushed; `latest` is excluded so the
  # rolling tag (used by the Ansible deploy path) can keep moving.
  image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"

  image_tag_mutability_exclusion_filter {
    filter_type = "WILDCARD"
    filter      = "latest"
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "devops-bootcamp/final-project-${var.owner_slug}"
  }
}

# Lifecycle policy to retain the latest 10 images
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
