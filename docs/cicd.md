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
| `terraform/iam.tf` | OIDC identity provider (`token.actions.githubusercontent.com`) and scoped IAM roles/policies |
| `terraform/outputs.tf` | Exports the legacy and role-specific GitHub Actions role ARNs |

---

## Inputs

### AWS IAM OIDC Federation

Authentication between GitHub Actions and AWS is established using OpenID Connect (OIDC). No static credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are stored in GitHub Secrets.

| Parameter | Configuration / Value |
| --- | --- |
| **OIDC Provider URL** | `https://token.actions.githubusercontent.com` |
| **Audience (`aud`)** | `sts.amazonaws.com` |
| **Runtime Subject Claim (`sub`)** | Exact immutable-ID subjects using `StringEquals`: publisher, lifecycle, and status use `repo:hasB223@124649481/devops-bootcamp-project@1358353685:ref:refs/heads/main`; deployer uses `repo:hasB223@124649481/devops-bootcamp-project@1358353685:environment:production`. The branch-ref form was observed in manual and scheduled diagnostic runs; the name-only form was not observed. |
| **Runtime Roles** | ECR publisher, SSM deployer, lifecycle mutator, and status read-only. Each workflow job assumes only the role needed for its action. |
| **Terraform Planner** | A fifth read-only role is defined for the later state-backed PR plan gate. Same-repository PR #53 diagnostic run `35090523901` observed `repo:hasB223@124649481/devops-bootcamp-project@1358353685:pull_request`, matching the role's exact `StringEquals` trust condition. |
| **Legacy Migration Role** | `devops-github-actions-role` remains temporarily as the rollback anchor during soak. Its wildcard trust is removed in the follow-up retirement change, after the scoped roles pass live acceptance. |

### GitHub Actions Variables

The pipelines consume non-sensitive parameters as **Repository Variables** (`vars.<NAME>`) in GitHub:

| Variable Name | Example / Production Value | Source |
| --- | --- | --- |
| `AWS_REGION` | `ap-southeast-1` | AWS deployment region |
| `AWS_ROLE_PUBLISH` | Role ARN | `terraform output github_actions_ecr_publisher_role_arn` |
| `AWS_ROLE_DEPLOY` | Role ARN | `terraform output github_actions_ssm_deployer_role_arn` |
| `AWS_ROLE_LIFECYCLE` | Role ARN | `terraform output github_actions_lifecycle_mutator_role_arn` |
| `AWS_ROLE_READONLY` | Role ARN | `terraform output github_actions_status_readonly_role_arn` |
| `AWS_ROLE_TERRAFORM_PLAN` | Role ARN | `terraform output github_actions_terraform_planner_role_arn` (reserved for the later PR plan gate) |
| `AWS_ROLE_TO_ASSUME` | Legacy role ARN | Temporary rollback anchor; do not remove until scoped-role soak completes |
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

#### Security Scanning

Two additional jobs run alongside the lint and build gates.

**Secret scanning (Gitleaks).** `gitleaks/gitleaks-action@v3` scans for
hardcoded credentials on pull requests and pushes. The checkout uses
`fetch-depth: 0` so the scan covers the **full commit history**, not just the
tip: a secret added in an earlier commit and deleted later would otherwise go
undetected, and deletion is not remediation — anything committed is still in
the history. The repository is personal-account owned, so no `GITLEAKS_LICENSE`
is required (that applies to organizations only). If this job ever exceeds
roughly two minutes, switch to a bounded range scan rather than dropping
history coverage.

**Vulnerability and misconfiguration scanning (Trivy).** Three modes:

| Mode | Target | Enforcement |
| --- | --- | --- |
| `fs` | `app/` dependencies | **Blocking** at HIGH/CRITICAL (`ignore-unfixed`) |
| `image` | the container built in-job | **Blocking** at HIGH/CRITICAL |
| `config` | Terraform in both roots | **Advisory** (`continue-on-error`) |

The image scan builds the container and scans it **before any registry push**.
This is deliberate and complements — rather than duplicates — ECR's
`scan_on_push`: scan-on-push reports findings only *after* the image is in the
registry and already pullable, so it is detection after the fact. The CI scan is
the gate that stops a vulnerable artifact from being published. Keeping both
gives pre-publication blocking plus ongoing registry-side visibility as new CVEs
are disclosed against images already stored.

The IaC scan starts advisory on purpose: its findings have not yet been
triaged, and a wall of unassessed warnings blocking every PR trains people to
ignore the signal. Promote it to blocking after roughly two weeks of observed
output.

#### Dependency Updates

`.github/dependabot.yml` enables Dependabot for four ecosystems:
`github-actions` (weekly), `docker` in `/app` (weekly), `npm` in `/app`
(weekly), and `pip` at the root (monthly — the only pip manifest is
`requirements-docs.txt`). Updates are grouped per ecosystem to keep PR volume
reviewable.

`app/Dockerfile` pins both base images by digest
(`node:20-alpine@sha256:…`, `nginx:alpine-slim@sha256:…`) so a rebuild resolves
the exact same bytes instead of whatever the floating tag points at. The pinned
values are multi-arch manifest-list digests, which keeps normal platform
resolution intact if builds ever go multi-platform. Dependabot's `docker`
ecosystem revises the tag and digest together.

The runtime stage uses **`nginx:alpine-slim`**, the official minimal nginx
variant, and installs or upgrades **no packages at all**. Both properties
matter:

- **Controlled build inputs.** Two specific things are fixed, and it is worth
  being precise about which:
    - Digest pinning fixes the **contents of the selected base image**, so an
      upstream tag move cannot silently change that input between builds.
    - Removing `apk` operations eliminates **live Alpine-repository resolution**
      from the runtime stage, so package versions are not chosen at build time
      from a moving repository.

    What this does *not* establish: it is **not** a guarantee that two separate
    builds produce byte-identical images. PR CI scans a **candidate image built
    from the proposed source and Dockerfile**. The deployment workflow
    **rebuilds after merge**, so artifact identity between the scanned image and
    the deployed image **is not guaranteed**. Guaranteeing that the scanned
    artifact is exactly the deployed artifact would require
    **build-once-and-promote** — build, scan, push, then deploy that same
    digest — which is **outside this PR's scope**.
- **Passing the gate without a floating upgrade.** The fuller `alpine` and
  `stable-alpine` variants ship util-linux/`libuuid`, which currently carries 7
  fixable HIGH/CRITICAL advisories and fails the blocking image scan.
  `alpine-slim` omits those packages and scans clean, so the gate is satisfied
  by choosing a smaller base rather than by mutating packages at build time or
  relaxing the scan.

Security patches therefore arrive one way only: **advance the pinned digest**
(weekly, via Dependabot). Do not add package installation to the runtime stage.

!!! note "Accepted risk: third-party actions are pinned by tag, not SHA"
    Workflow steps reference actions by major-version tag (`@v4`) rather than a
    commit SHA. A tag is mutable, so a compromised upstream release could reach
    this pipeline. This deferral is an **explicit accepted risk (medium)**:
    Dependabot's `github-actions` ecosystem provides update visibility, but it
    does not eliminate the exposure. Revisit if this repository starts handling
    third-party contributions.

Digest pinning has a cost worth stating: between Dependabot cycles the base
images are frozen, so a patched upstream image is not picked up until an update
PR lands. The weekly cadence bounds that staleness to about a week plus review
time. That is the deliberate trade for controlled build inputs — a build-time
package upgrade would shorten the patch lag, but it would reintroduce
repository-time resolution and make the base-image contents vary between builds
of the same commit.

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

1. **OIDC Authentication**: `aws-actions/configure-aws-credentials@v6` requests a signed JWT from GitHub's OIDC provider and exchanges it for temporary AWS STS credentials. Publishing uses `vars.AWS_ROLE_PUBLISH`; the two production deployment jobs use `vars.AWS_ROLE_DEPLOY` and the protected `production` environment.
2. **ECR Login**: `aws-actions/amazon-ecr-login@v2` authenticates Docker Engine to the private ECR registry.
3. **Container Build**: Builds the container using `app/Dockerfile` with the `app/` directory as context:
   ```bash
   docker build \
     -t "$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" \
     -t "$ECR_REGISTRY/$ECR_REPOSITORY:latest" \
     -f app/Dockerfile \
     app
   ```
4. **Tag & Push**: Pushes both the full commit-SHA tag (`${{ github.sha }}`) and the mutable `latest` tag to ECR. SHA tags are enforced immutable by the registry (`IMMUTABLE_WITH_EXCLUSION`, `terraform/ecr.tf`): Amazon ECR rejects **any** push that uses an already-existing immutable SHA tag with `ImageTagAlreadyExistsException` — including a rebuilt image whose content or manifest is identical to what was previously published. Only `latest` remains mutable through the exclusion. A rerun of this workflow after its SHA tag was published may therefore fail during the push step; recover by deploying the already-published SHA via the `deploy_tag` input, or by creating a new commit to publish under a new SHA.

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

For the scoped-role migration, review and apply a saved **full** plan. Do not use a targeted apply: the acceptance condition is an additive action set with no deletion of the legacy role, its three attachments, or the shared managed policies.

Retrieve the provisioned role ARNs:
```bash
terraform output github_actions_role_arn
terraform output github_actions_ecr_publisher_role_arn
terraform output github_actions_ssm_deployer_role_arn
terraform output github_actions_lifecycle_mutator_role_arn
terraform output github_actions_status_readonly_role_arn
terraform output github_actions_terraform_planner_role_arn
```

### 2. Configure GitHub Repository Variables

Set the required Actions variables in GitHub repository settings (**Settings** -> **Secrets and variables** -> **Actions** -> **Variables** tab):

```bash
# Using GitHub CLI:
gh variable set AWS_REGION --body "ap-southeast-1"
gh variable set AWS_ROLE_PUBLISH --body "$(cd terraform && terraform output -raw github_actions_ecr_publisher_role_arn)"
gh variable set AWS_ROLE_DEPLOY --body "$(cd terraform && terraform output -raw github_actions_ssm_deployer_role_arn)"
gh variable set AWS_ROLE_LIFECYCLE --body "$(cd terraform && terraform output -raw github_actions_lifecycle_mutator_role_arn)"
gh variable set AWS_ROLE_READONLY --body "$(cd terraform && terraform output -raw github_actions_status_readonly_role_arn)"
gh variable set AWS_ROLE_TERRAFORM_PLAN --body "$(cd terraform && terraform output -raw github_actions_terraform_planner_role_arn)"
gh variable set ECR_REPOSITORY --body "devops-bootcamp/final-project-hasb"
```

Create the `production` environment separately, restrict deployment branches to `main`, and configure the owner as required reviewer before switching deploy jobs to the scoped role. Keep `AWS_ROLE_TO_ASSUME` during soak so the workflow variables can be rolled back without a Terraform change.

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
- **Fix**: Match the role to the job context and verify its exact `StringEquals` subject:
  ```hcl
  test     = "StringEquals"
  variable = "token.actions.githubusercontent.com:sub"
  values   = ["repo:hasB223@124649481/devops-bootcamp-project@1358353685:ref:refs/heads/main"]
  ```
  The deployer instead requires the `:environment:production` subject. Also ensure `audience = "sts.amazonaws.com"`, the selected workflow ref is `main`, and the corresponding `AWS_ROLE_*` variable points to the intended role.

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
