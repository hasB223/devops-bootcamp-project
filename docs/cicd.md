# CI/CD Automation Runbook

**Verification scope:** Checked against current Terraform, GitHub Actions workflows, repository variables, and captured CI/CD run evidence.

This document describes the continuous integration, container publishing, and documentation delivery pipelines for the DevOps platform, automated using **GitHub Actions** and secured via **AWS IAM OpenID Connect (OIDC)** identity federation.

---

## Purpose

The CI/CD pipeline implements a secure, automated delivery lifecycle for all infrastructure and application code:

- **Pull Request Quality Gates**: Automatically validates Terraform code formatting, configuration validity (backendless), Ansible playbook syntax, and frontend Node.js unit tests/production builds on every PR before merge.
- **Keyless AWS Authentication**: Uses short-lived OIDC tokens exchanged directly with AWS Security Token Service (STS) to authenticate GitHub Actions runners without creating or storing long-lived AWS IAM access keys.
- **Automated Container Publishing**: Builds and tags the Three.js multi-stage container image upon merges to `main` and publishes it to AWS Private Elastic Container Registry (ECR).
- **Decoupled Deployment Boundary**: Container images are pushed to ECR upon application code changes (`app/**`), decoupling artifact storage from EC2 runtime execution. Host container rollout on Web EC2 is orchestrated independently via Ansible.
- **Continuous Documentation Publishing**: Deploys the static documentation portal in `docs/` directly to GitHub Pages upon merges to `main`.

---

## Files

| File | Purpose |
| --- | --- |
| `.github/workflows/ci.yml` | Quality gate pipeline for PRs (Terraform fmt/validate, Ansible syntax, App test/build) |
| `.github/workflows/build-push-ecr.yml` | Main-branch container image build and push to private AWS ECR via OIDC |
| `.github/workflows/pages.yml` | Main-branch static documentation portal deployment to GitHub Pages |
| `docs/index.html` | Browsable project documentation portal exposing endpoints, runbooks, and architecture |
| `terraform/iam.tf` | OIDC identity provider (`token.actions.githubusercontent.com`) and scoped IAM role/policy |
| `terraform/outputs.tf` | Exports `github_actions_role_arn` for pipeline configuration |

---

## Inputs

### AWS IAM OIDC Federation

Authentication between GitHub Actions and AWS is established using OpenID Connect (OIDC). No static credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are stored in GitHub Secrets.

| Parameter | Configuration / Value |
| --- | --- |
| **OIDC Provider URL** | `https://token.actions.githubusercontent.com` |
| **Audience (`aud`)** | `sts.amazonaws.com` |
| **Subject Claim (`sub`)** | Wildcard matching (`StringLike`) for two accepted repository subject prefixes:<br>1. Standard: `repo:hasB223/devops-bootcamp-project:*`<br>2. Immutable-ID: `repo:hasB223@124649481/devops-bootcamp-project@1358353685:*`<br>Any workflow run in this repository (any branch, PR, or environment) can therefore assume the role. Tightening trust to exact subjects is planned follow-up work. |
| **IAM Role** | `devops-github-actions-role` |
| **Role Permissions** | Scoped ECR push: `ecr:GetAuthorizationToken` (`*`), and image actions on `aws_ecr_repository.app.arn` |

### GitHub Actions Variables

The pipelines consume non-sensitive parameters as **Repository Variables** (`vars.<NAME>`) in GitHub:

| Variable Name | Example / Production Value | Source |
| --- | --- | --- |
| `AWS_REGION` | `ap-southeast-1` | AWS deployment region |
| `AWS_ROLE_TO_ASSUME` | `arn:aws:iam::164824552037:role/devops-github-actions-role` | `terraform output github_actions_role_arn` |
| `ECR_REPOSITORY` | `devops-bootcamp/final-project-hasb` | `terraform output ecr_repository_url` (name segment) |

!!! important "Zero Static Credentials Policy"
    Do not create or store AWS IAM access keys in GitHub Secrets. All AWS API calls from Actions runners authenticate through temporary credentials issued via `sts:AssumeRoleWithWebIdentity`.

---

## Pipeline Architectures & Workflows

### 1. CI Quality Gate (`ci.yml`)

The CI workflow acts as a mandatory pre-merge quality gate. It executes on every pull request targeting `main`, as well as on pushes to `feature/**` and `fix/**` branches.

```text
  Pull Request / Push (feature/*)
               |
        +------+------+
        |             |
        v             v
+---------------+  +---------------+
| Job 1:        |  | Job 2:        |
| Terraform &   |  | Node.js 20    |
| Ansible Gate  |  | App Build     |
+---------------+  +---------------+
  |                  |
  |-- terraform fmt  |-- npm ci
  |-- terraform init |-- npm run test
  |   (-backend=false)|-- npm run build
  |-- terraform      |
  |   validate       v
  |-- ansible        [Pass / Fail]
  |   --syntax-check
  v
[Pass / Fail]
```

#### Steps Executed

1. **Terraform Format Check**: `terraform -chdir=terraform fmt -check` enforces canonical formatting.
2. **Backendless Initialization**: `terraform -chdir=terraform init -backend=false` prepares provider plugins without requiring S3 bucket access or AWS credentials.
3. **Terraform Validation**: `terraform -chdir=terraform validate` verifies syntax and resource argument validity.
4. **Ansible Syntax Check**: Installs Ansible via pip, installs declared Galaxy roles/collections (`geerlingguy.docker`), and validates syntax:
   ```bash
   ansible-galaxy install -r ansible/requirements.yml -p ansible/roles
   ansible-playbook --syntax-check -i ansible/inventory.ini.example ansible/playbook.yml
   ```
5. **Frontend Test & Build**:
   ```bash
   cd app
   npm ci
   npm run test
   npm run build
   ```

---

### 2. ECR Image Build & Push (`build-push-ecr.yml`)

This workflow packages the containerized application and publishes it to AWS Private ECR.

#### Trigger & Path Filter

- Fires on `push` to `main` **only** when files under `app/**` or the workflow itself change:
  ```yaml
  paths:
    - 'app/**'
    - '.github/workflows/build-push-ecr.yml'
  ```
- Can also be manually invoked via `workflow_dispatch`.

#### Workflow Execution Flow

1. **OIDC Authentication**: `aws-actions/configure-aws-credentials@v4` requests a signed JWT from GitHub's OIDC provider and exchanges it for temporary AWS STS credentials using `role-to-assume: ${{ vars.AWS_ROLE_TO_ASSUME }}`.
2. **ECR Login**: `aws-actions/amazon-ecr-login@v2` authenticates Docker Engine to the private ECR registry.
3. **Container Build**: Builds the container using `app/Dockerfile` with the `app/` directory as context:
   ```bash
   docker build \
     -t "$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" \
     -t "$ECR_REGISTRY/$ECR_REPOSITORY:latest" \
     -f app/Dockerfile \
     app
   ```
4. **Tag & Push**: Pushes both the full commit-SHA tag (`${{ github.sha }}`) and the mutable `latest` tag to ECR. The SHA tag is unique per commit by convention; tag immutability is not enforced by the registry (see `image_tag_mutability` in `terraform/ecr.tf`).

!!! note "Decoupled Deployment Boundary"
    Pushing a new container to ECR does not automatically trigger rolling restarts on Web EC2. Production container updates on the host are executed intentionally via the Ansible Controller playbook (`ansible/playbook.yml`).

---

### 3. GitHub Pages Deployment (`pages.yml`)

This workflow publishes the interactive documentation portal (`docs/index.html`, runbooks, and embedded architecture diagrams) to GitHub Pages.

#### Trigger

- Fires on `push` to `main` when documentation files change (`docs/**`, `README.md`, `.github/workflows/pages.yml`), or via `workflow_dispatch`.

#### Concurrency & Permissions

- Permissions: `pages: write`, `id-token: write`, `contents: read`.
- Concurrency group `pages` with `cancel-in-progress: false` ensures sequential, reliable publishing.

#### Workflow Execution Flow

1. Configures Pages runtime with `actions/configure-pages@v5`.
2. Packages the `docs/` directory as an artifact with `actions/upload-pages-artifact@v3`.
3. Deploys the artifact to the GitHub Pages environment via `actions/deploy-pages@v4`.

#### CDN Edge Caching & Invalidation

The documentation portal is accelerated by Cloudflare edge caching backed by the GitHub Pages origin (`max-age=600`). Canonical URLs may briefly serve cached responses following deployment until edge TTLs expire. For major visual releases (such as Archify diagrams or homepage previews), follow the manual single-file Cloudflare purge procedure documented in the [Operational Runbook](runbook.md#documentation-portal-deployment-cdn-cache-invalidation).

---

## Configuration Steps

### 1. Apply Terraform Infrastructure & OIDC Configuration

#### Normal Project Workflow
The standard project workflow plans and applies the full infrastructure stack (networking, compute, security groups, ECR, and IAM roles) together:

```bash
cd terraform
terraform plan
terraform apply
```

#### Narrow Bootstrap / Surgical Update Option
Targeted apply using `-target` is reserved strictly as a narrow bootstrap or surgical update option (for example, provisioning or updating the CI/OIDC IAM role and ECR repository without spinning up the full EC2 compute instances):

```bash
cd terraform
terraform apply -target=aws_ecr_repository.app \
                -target=aws_ecr_lifecycle_policy.app \
                -target=aws_iam_openid_connect_provider.github \
                -target=aws_iam_role.github_actions \
                -target=aws_iam_policy.github_actions_ecr \
                -target=aws_iam_role_policy_attachment.github_actions_ecr
```

Retrieve the provisioned role ARN:
```bash
terraform output github_actions_role_arn
# Output: arn:aws:iam::164824552037:role/devops-github-actions-role
```

### 2. Configure GitHub Repository Variables

Set the required Actions variables in GitHub repository settings (**Settings** -> **Secrets and variables** -> **Actions** -> **Variables** tab):

```bash
# Using GitHub CLI:
gh variable set AWS_REGION --body "ap-southeast-1"
gh variable set AWS_ROLE_TO_ASSUME --body "$(cd terraform && terraform output -raw github_actions_role_arn)"
gh variable set ECR_REPOSITORY --body "devops-bootcamp/final-project-hasb"
```

### 3. Enable GitHub Pages & Custom Domain

Configure GitHub Pages to deploy from GitHub Actions with the branded domain:

1. In the repository, navigate to **Settings** -> **Pages**.
2. Under **Build and deployment** -> **Source**, select **GitHub Actions**.
3. Under **Custom domain**, configure `docs.hasb.dev`.

    - **Source of Truth**: The repository Pages custom-domain setting (configured via repository Settings or `gh api repos/{owner}/{repo}/pages -f cname="docs.hasb.dev"`) is the active domain binding and certificate trigger.
    - **Artifact Tracking**: `docs/CNAME` records the intended custom domain in the deployed docs artifact to keep configuration aligned in Git, but for GitHub Actions-based Pages deployment, it should not be described as the sole mechanism that binds the domain.

4. Once DNS verification completes and the TLS certificate is issued, ensure **Enforce HTTPS** is checked.

---

## Verification

### 1. Local Pipeline Preflight Checks

Run the same checks locally that the CI quality gate executes:

```bash
# 1. Terraform formatting & backendless validation
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform fmt -check
terraform -chdir=terraform validate

# 2. Ansible playbook syntax validation
ansible-playbook --syntax-check -i ansible/inventory.ini.example ansible/playbook.yml

# 3. Application preflight test and production build
cd app
npm ci
npm run test
npm run build
```

Expected output:

- `terraform validate`: `Success! The configuration is valid.`
- `ansible-playbook --syntax-check`: `playbook: ansible/playbook.yml` with exit code 0.
- `npm run test`: `✓ pre-flight OK — "Nebula Runner" cleared for launch`.
- `npm run build`: `✓ built in ... dist/`.

### 2. Actions Workflow Execution Verification

After pushing or merging to `main`:

1. Navigate to repository **Actions** tab.
2. Confirm `CI Quality Gate` passes on the pull request.
3. Confirm `Deploy Documentation to GitHub Pages` completes with green check.
4. Confirm `Build & Push Container to ECR` completes and logs output image tags.
5. Verify container image exists in private ECR:
   ```bash
   aws ecr describe-images \
     --repository-name devops-bootcamp/final-project-hasb \
     --region ap-southeast-1 \
     --query 'imageDetails[*].imageTags'
   ```

---

## Troubleshooting

### 1. OIDC AssumeRole Denied (`403 AccessDenied`)
- **Symptom**: `aws-actions/configure-aws-credentials` fails with:
  ```text
  Error: Not authorized to perform sts:AssumeRoleWithWebIdentity
  ```
- **Cause**: The IAM role trust policy does not match the GitHub repository or branch claim.
- **Fix**: Verify `terraform/iam.tf` includes both accepted wildcard subject prefixes in the trust policy condition:
  ```hcl
  test     = "StringLike"
  variable = "token.actions.githubusercontent.com:sub"
  values = [
    "repo:hasB223/devops-bootcamp-project:*",
    "repo:hasB223@124649481/devops-bootcamp-project@1358353685:*"
  ]
  ```
  Also ensure `audience = "sts.amazonaws.com"`.

### 2. Terraform Validate Fails in CI
- **Symptom**: `terraform validate` fails with missing provider or module errors.
- **Cause**: `terraform init` was skipped or attempted to connect to remote backend.
- **Fix**: Ensure `terraform -chdir=terraform init -backend=false` is executed immediately prior to `terraform validate`.

### 3. GitHub Pages 404 Not Found
- **Symptom**: Pages URL displays a 404 error after successful workflow run.
- **Cause**: Repository Pages setting is set to "Deploy from a branch" instead of "GitHub Actions".
- **Fix**: Set **Settings** -> **Pages** -> **Source** to **GitHub Actions**.

### 4. ECR Push Layer Upload Denied
- **Symptom**: Docker push fails during layer upload to ECR.
- **Cause**: Scoped IAM policy missing `ecr:UploadLayerPart` or `ecr:CompleteLayerUpload`.
- **Fix**: Verify `aws_iam_policy.github_actions_ecr` contains all standard ECR push actions:
  `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`.
