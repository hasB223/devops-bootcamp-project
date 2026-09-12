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
# Web Host IAM Role & Instance Profile (Least Privilege ECR Pull)
# ==============================================================================
resource "aws_iam_role" "web_role" {
  name               = "devops-web-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Name = "devops-web-role"
  }
}

resource "aws_iam_role_policy_attachment" "web_ssm_core" {
  role       = aws_iam_role.web_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "web_ecr_pull" {
  statement {
    sid       = "ECRGetAuthorizationToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "ECRPullAppImage"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer"
    ]
    resources = [aws_ecr_repository.app.arn]
  }
}

resource "aws_iam_policy" "web_ecr_pull" {
  name        = "devops-web-ecr-pull-policy"
  description = "Least-privilege policy allowing Web EC2 to pull container images from private ECR"
  policy      = data.aws_iam_policy_document.web_ecr_pull.json
}

resource "aws_iam_role_policy_attachment" "web_ecr_pull" {
  role       = aws_iam_role.web_role.name
  policy_arn = aws_iam_policy.web_ecr_pull.arn
}

resource "aws_iam_instance_profile" "web_profile" {
  name = "devops-web-profile"
  role = aws_iam_role.web_role.name

  tags = {
    Name = "devops-web-profile"
  }
}

# ==============================================================================
# Monitoring Host IAM Role & Instance Profile (SSM Core Only)
# ==============================================================================
resource "aws_iam_role" "monitoring_role" {
  name               = "devops-monitoring-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Name = "devops-monitoring-role"
  }
}

resource "aws_iam_role_policy_attachment" "monitoring_ssm_core" {
  role       = aws_iam_role.monitoring_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "monitoring_profile" {
  name = "devops-monitoring-profile"
  role = aws_iam_role.monitoring_role.name

  tags = {
    Name = "devops-monitoring-profile"
  }
}

# ==============================================================================
# Dedicated Controller IAM Role (SSM Core + Scoped SSM/S3 Relay Policy)
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

resource "aws_iam_instance_profile" "controller_profile" {
  name = "devops-controller-profile"
  role = aws_iam_role.controller_role.name

  tags = {
    Name = "devops-controller-profile"
  }
}

# ==============================================================================
# Controller SSM & S3 Policy for Ansible Transport over Systems Manager
# ==============================================================================
data "aws_iam_policy_document" "controller_ssm_ops" {
  statement {
    sid    = "SSMSessionManagerInstances"
    effect = "Allow"
    actions = [
      "ssm:StartSession",
      "ssm:SendCommand"
    ]
    resources = [
      aws_instance.web.arn,
      aws_instance.monitoring.arn,
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:document/*",
      "arn:aws:ssm:${var.aws_region}::document/*"
    ]
  }

  statement {
    sid    = "SSMSessionTracking"
    effect = "Allow"
    actions = [
      "ssm:TerminateSession",
      "ssm:ResumeSession",
      "ssm:GetCommandInvocation",
      "ssm:ListCommands",
      "ssm:ListCommandInvocations",
      "ssm:DescribeInstanceInformation",
      "ssm:GetConnectionStatus",
      "ssm:DescribeSessions"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "SSMSessionDataChannel"
    effect = "Allow"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel"
    ]
    # Note: AWS Session Manager data-channel actions (ssmmessages) do not support resource-level ARNs
    resources = ["*"]
  }

  statement {
    sid    = "SSMTransferBucketMetadata"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket"
    ]
    resources = [aws_s3_bucket.ansible_ssm.arn]
  }

  statement {
    sid    = "SSMTransferObjectAccess"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject"
    ]
    resources = ["${aws_s3_bucket.ansible_ssm.arn}/i-*"]
  }
}

resource "aws_iam_policy" "controller_ssm" {
  name        = "devops-controller-ssm-policy"
  description = "Scoped policy allowing Ansible Controller to manage instances via SSM and dedicated S3 relay"
  policy      = data.aws_iam_policy_document.controller_ssm_ops.json
}

resource "aws_iam_role_policy_attachment" "controller_ssm" {
  role       = aws_iam_role.controller_role.name
  policy_arn = aws_iam_policy.controller_ssm.arn
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
        "repo:hasB223/devops-bootcamp-project:*",
        "repo:hasB223@124649481/devops-bootcamp-project@1358353685:*"
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

# ==============================================================================
# GitHub Actions Policy for Automated SSM Deployment to Web EC2
# ==============================================================================
data "aws_iam_policy_document" "github_actions_ssm_deploy" {
  statement {
    sid       = "EC2DescribeInstancesForDeployment"
    effect    = "Allow"
    actions   = ["ec2:DescribeInstances"]
    resources = ["*"]
  }

  statement {
    sid    = "SSMSendCommandToWebInstance"
    effect = "Allow"
    actions = [
      "ssm:SendCommand"
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:document/AWS-RunShellScript",
      "arn:aws:ssm:${var.aws_region}::document/AWS-RunShellScript",
      aws_instance.web.arn
    ]
  }

  statement {
    sid    = "SSMCommandInvocationTracking"
    effect = "Allow"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommands",
      "ssm:ListCommandInvocations",
      "ssm:DescribeInstanceInformation"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "github_actions_ssm" {
  name        = "devops-github-actions-ssm-policy"
  description = "Scoped policy allowing GitHub Actions OIDC workflow to deploy container updates to Web EC2 via SSM"
  policy      = data.aws_iam_policy_document.github_actions_ssm_deploy.json
}

resource "aws_iam_role_policy_attachment" "github_actions_ssm" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_actions_ssm.arn
}

# ==============================================================================
# GitHub Actions Policy for Platform Lifecycle Automation (Park & Unpark)
# ==============================================================================
data "aws_iam_policy_document" "github_actions_lifecycle" {
  # 1. AWS ec2:Describe* APIs (AWS specification: Describe* does not support resource-level permissions or condition keys)
  statement {
    sid    = "EC2DescribeReadPlatformState"
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeInstanceStatus",
      "ec2:DescribeInstanceCreditSpecifications",
      "ec2:DescribeNatGateways",
      "ec2:DescribeAddresses",
      "ec2:DescribeRouteTables",
      "ec2:DescribeVpcEndpoints",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSecurityGroupRules",
      "ec2:DescribeAvailabilityZones",
      "ec2:DescribeImages",
      "ec2:DescribeInternetGateways",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeTags"
    ]
    resources = ["*"]
  }

  # 2. EC2 Compute Power Management (Strictly scoped to project EC2 instance ARNs)
  statement {
    sid    = "EC2ComputePowerManagement"
    effect = "Allow"
    actions = [
      "ec2:StartInstances",
      "ec2:StopInstances"
    ]
    resources = [
      aws_instance.web.arn,
      aws_instance.controller.arn,
      aws_instance.monitoring.arn
    ]
  }

  # 3. NAT Gateway Lifecycle (Scoped to project NAT Gateway ARNs, Subnet, and EIP)
  statement {
    sid    = "EC2NatGatewayLifecycle"
    effect = "Allow"
    actions = [
      "ec2:CreateNatGateway",
      "ec2:DeleteNatGateway"
    ]
    resources = [
      "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:natgateway/*",
      aws_subnet.public.arn,
      "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:elastic-ip/*"
    ]
  }

  # 4. Elastic IP Allocation / Release (AWS specification: AllocateAddress and ReleaseAddress do not support resource ARNs)
  statement {
    sid    = "EC2ElasticIpLifecycle"
    effect = "Allow"
    actions = [
      "ec2:AllocateAddress",
      "ec2:ReleaseAddress"
    ]
    resources = ["*"]
  }

  # 5. Route Table & Routing Lifecycle
  statement {
    sid    = "EC2RouteTableLifecycle"
    effect = "Allow"
    actions = [
      "ec2:CreateRouteTable",
      "ec2:DeleteRouteTable",
      "ec2:CreateRoute",
      "ec2:DeleteRoute",
      "ec2:AssociateRouteTable",
      "ec2:DisassociateRouteTable"
    ]
    resources = [
      "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:route-table/*",
      aws_vpc.main.arn,
      aws_subnet.private.arn,
      aws_subnet.public.arn
    ]
  }

  # 6. S3 VPC Gateway Endpoint Lifecycle
  statement {
    sid    = "EC2VpcEndpointLifecycle"
    effect = "Allow"
    actions = [
      "ec2:CreateVpcEndpoint",
      "ec2:DeleteVpcEndpoints",
      "ec2:ModifyVpcEndpoint"
    ]
    resources = [
      "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:vpc-endpoint/*",
      aws_vpc.main.arn
    ]
  }

  # 7. EC2 Resource Tagging
  statement {
    sid    = "EC2TaggingManagement"
    effect = "Allow"
    actions = [
      "ec2:CreateTags",
      "ec2:DeleteTags"
    ]
    resources = [
      "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*/*"
    ]
  }

  # 8. S3 Remote State Bucket-Level Actions
  statement {
    sid    = "S3RemoteStateBucketAccess"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetBucketVersioning"
    ]
    resources = [
      "arn:aws:s3:::devops-bootcamp-terraform-${var.owner_slug}"
    ]
  }

  # 9. S3 Remote State Object-Level Actions
  statement {
    sid    = "S3RemoteStateObjectAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [
      "arn:aws:s3:::devops-bootcamp-terraform-${var.owner_slug}/*"
    ]
  }

  # 10. IAM State Read Refresh (Required for full terraform plan/refresh across managed roles and policies)
  statement {
    sid    = "IAMStateReadRefresh"
    effect = "Allow"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyVersions",
      "iam:GetInstanceProfile",
      "iam:GetOpenIDConnectProvider"
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/devops-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/devops-*",
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/devops-*",
      aws_iam_openid_connect_provider.github.arn
    ]
  }

  # 11. ECR Repository State Read Refresh
  statement {
    sid    = "ECRStateReadRefresh"
    effect = "Allow"
    actions = [
      "ecr:DescribeRepositories",
      "ecr:GetRepositoryPolicy",
      "ecr:GetLifecyclePolicy"
    ]
    resources = [
      aws_ecr_repository.app.arn
    ]
  }

  # 12. Ansible SSM S3 Bucket Read Refresh
  statement {
    sid    = "S3AnsibleBucketReadRefresh"
    effect = "Allow"
    actions = [
      "s3:GetBucketAcl",
      "s3:GetBucketCORS",
      "s3:GetBucketWebsite",
      "s3:GetBucketVersioning",
      "s3:GetAccelerationConfiguration",
      "s3:GetBucketRequestPayment",
      "s3:GetBucketLogging",
      "s3:GetLifecycleConfiguration",
      "s3:GetReplicationConfiguration",
      "s3:GetEncryptionConfiguration",
      "s3:GetBucketObjectLockConfiguration",
      "s3:GetBucketTagging",
      "s3:GetBucketPolicy",
      "s3:GetBucketPublicAccessBlock"
    ]
    resources = [
      aws_s3_bucket.ansible_ssm.arn,
      "${aws_s3_bucket.ansible_ssm.arn}/*"
    ]
  }
}

resource "aws_iam_policy" "github_actions_lifecycle" {
  name        = "devops-github-actions-lifecycle-policy"
  description = "Scoped policy allowing GitHub Actions OIDC workflow to manage platform park/unpark lifecycle"
  policy      = data.aws_iam_policy_document.github_actions_lifecycle.json
}

resource "aws_iam_role_policy_attachment" "github_actions_lifecycle" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_actions_lifecycle.arn
}
