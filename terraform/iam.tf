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
