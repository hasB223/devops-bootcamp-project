# Documentation Conventions

Write the tracked documentation as future-self runbooks: practical, repeatable,
and specific to this project. The goal is not to document only what automation
can verify. The goal is to make the project rebuildable later without guessing.

## Documentation Map

Use modular docs by layer, then one end-to-end runbook:

```text
docs/
├── architecture.md
├── git-workflow.md
├── terraform.md
├── docker.md
├── ansible.md
├── cicd.md
├── monitoring.md
├── cloudflare.md
├── runbook.md
└── submission.md
```

## Page Shape

Each modular doc should use this shape unless the topic is too small:

```text
# Topic

## Purpose
What this layer owns.

## Files
Where the code/config lives.

## Inputs
Variables, credentials, account IDs, domain names, passwords, and UI values.
Document where values come from, not secret values themselves.

## Steps
Exact commands or UI actions.

## Verification
What proves it worked.

## Troubleshooting
Real issues encountered during the project, not imagined encyclopedia content.
```

## Commands

Use exact command blocks when a step happens in the terminal:

```bash
terraform init
terraform plan
terraform apply
```

Document the working directory before commands when it matters:

```bash
cd terraform
terraform plan
```

## UI Steps

Use concrete UI paths where the class or project uses a dashboard:

```text
Grafana -> Connections -> Data sources -> Add data source -> Prometheus

URL:
http://localhost:9090

Action:
Save & test
```

Write where passwords, tokens, or connection values are entered, but never write
real secret values.

## Secrets

Document placement and naming, not values:

```text
Grafana admin password:
Store in a password manager or ignored local file.

Cloudflare API token:
Export as CLOUDFLARE_API_TOKEN before running Terraform.

Application .env:
Create from .env.example and keep the real .env ignored.
```

## Status Labels

Use honest status labels so manual and verified work can coexist:

```text
Status: verified
Status: manual, based on class workflow
Status: planned nice-to-have
```

This lets the docs include dashboard steps, Cloudflare setup, and console
observations without pretending every click is automated.

## CI/CD Coverage

Track CI/CD in `docs/cicd.md`. Start with GitHub Actions because this project is
hosted on GitHub. Add GitLab CI only if the project later moves to GitLab or if a
comparison is useful.

The CI/CD doc should cover:

- pipeline file location, usually `.github/workflows/<name>.yml`
- trigger, such as push to `main`, pull request, or manual `workflow_dispatch`
- build steps for the app image
- test or smoke-check commands
- authentication to AWS/ECR
- Docker image tag convention
- push to ECR
- deployment handoff, if the pipeline triggers Ansible or a server-side pull
- required repository secrets and where to configure them in GitHub
- how to verify a successful run in the Actions dashboard

For GitHub Actions secrets, document UI placement like this:

```text
GitHub -> Repository -> Settings -> Secrets and variables -> Actions

Repository secrets:
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_REGION
- ECR_REPOSITORY
- SSH_PRIVATE_KEY, if the pipeline deploys over SSH
```

Do not commit secret values. If a secret can be replaced by OIDC later, document
that as a hardening improvement after the baseline pipeline works.

## Rule Of Thumb

Docs should be reproducible enough to rebuild the project six months later, but
not so generalized that they stop describing this project.
