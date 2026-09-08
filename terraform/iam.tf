# ==============================================================================
# IAM Trust Policy for EC2
# ==============================================================================
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# ==============================================================================
# Base SSM Role & Instance Profile for EC2 Instances
# ==============================================================================
resource "aws_iam_role" "ssm_role" {
  name               = "devops-ec2-ssm-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Name = "devops-ec2-ssm-role"
  }
}

# Attach SSM Core policy for Systems Manager Session Manager
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Attach ECR ReadOnly policy so instances can pull Docker images
resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  role       = aws_iam_role.ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Base Instance Profile attached to instances
resource "aws_iam_instance_profile" "ssm_profile" {
  name = "devops-ec2-ssm-profile"
  role = aws_iam_role.ssm_role.name

  tags = {
    Name = "devops-ec2-ssm-profile"
  }
}

# ==============================================================================
# Dedicated Controller IAM Role (Bonus: IAM Least Privilege & Infisical Trust)
# ==============================================================================
resource "aws_iam_role" "controller_role" {
  name               = "devops-controller-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Name = "devops-controller-role"
  }
}

resource "aws_iam_role_policy_attachment" "controller_ssm_core" {
  role       = aws_iam_role.controller_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "controller_ecr_readonly" {
  role       = aws_iam_role.controller_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "controller_profile" {
  name = "devops-controller-profile"
  role = aws_iam_role.controller_role.name

  tags = {
    Name = "devops-controller-profile"
  }
}

# ==============================================================================
# GitHub Actions OIDC Provider & Role for Automated ECR Image Publishing
# ==============================================================================
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c5824a6f5a8794cb5c879d799042b5a5101a613"
  ]

  tags = {
    Name = "github-actions-oidc-provider"
  }
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:hasB223/devops-bootcamp-project:ref:refs/heads/main",
        "repo:hasB223@*/devops-bootcamp-project@*:ref:refs/heads/main"
      ]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "devops-github-actions-role"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json

  tags = {
    Name = "devops-github-actions-role"
  }
}

data "aws_iam_policy_document" "github_actions_ecr_push" {
  statement {
    sid       = "ECRGetAuthorizationToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "ECRPushImageClaims"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload"
    ]
    resources = [aws_ecr_repository.app.arn]
  }
}

resource "aws_iam_policy" "github_actions_ecr" {
  name        = "devops-github-actions-ecr-policy"
  description = "Scoped policy allowing GitHub Actions OIDC workflow to push container images"
  policy      = data.aws_iam_policy_document.github_actions_ecr_push.json
}

resource "aws_iam_role_policy_attachment" "github_actions_ecr" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_actions_ecr.arn
}

