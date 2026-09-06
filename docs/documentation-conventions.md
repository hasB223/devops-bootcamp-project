# Documentation Conventions

Write the tracked documentation as future-self runbooks: practical, repeatable,
and specific to this project. The goal is not to document only what automation
can verify. The goal is to make the project rebuildable later without guessing.

## Documentation Map

Use modular docs by layer, then one end-to-end runbook:

```text
docs/
├── architecture.md
├── secrets-management.md
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
Store as GF_SECURITY_ADMIN_PASSWORD in Infisical path /ansible.

Cloudflare tunnel token:
Store as CLOUDFLARE_TUNNEL_TOKEN in Infisical path /ansible.

Application .env:
Define its secret names in .env.example; retrieve real values from Infisical.
```

Follow `docs/secrets-management.md` for the authoritative secret inventory,
identity flows and safety rules.

## Status Labels

Use honest status labels so manual and verified work can coexist:

```text
Status: verified
Status: manual, based on class workflow
Status: planned nice-to-have
```

This lets the docs include dashboard steps, Cloudflare setup, and console
observations without pretending every click is automated.

## Testing And Verification

Every implementation doc should include a `Verification` section. Verification
applies to IaC, containers, Ansible, monitoring, domains, and CI/CD.

For Terraform/IaC, start with layered checks:

```bash
terraform fmt -check
terraform validate
terraform plan
```

After apply, document concrete verification commands or observations:

```bash
terraform output
aws ec2 describe-instances
aws ec2 describe-security-groups
aws ec2 describe-route-tables
```

The Terraform verification checklist should confirm:

- VPC CIDR is `10.0.0.0/24`
- public subnet is `10.0.0.0/25`
- private subnet is `10.0.0.128/25`
- Web EC2 has an Elastic IP
- Web EC2 allows public HTTP on port 80
- private instances do not have public IPs
- private subnet has outbound access through NAT

CI/CD can later automate some checks, especially `fmt`, `validate`, and `plan`
on pull requests.

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
- required Infisical paths and non-secret workflow configuration
- how to verify a successful run in the Actions dashboard

Authenticate GitHub Actions to AWS and Infisical with OIDC. Document normal
configuration separately from secrets:

```text
GitHub Actions OIDC -> AWS IAM role
GitHub Actions OIDC -> Infisical machine identity

Repository or environment variables:
- AWS_REGION
- AWS_ACCOUNT_ID
- ECR_REPOSITORY
```

Do not create permanent AWS access keys for the workflow. If a provider cannot
support identity-based authentication, document any GitHub repository secret as
an explicit fallback and explain why it is needed.

## Rule Of Thumb

Docs should be reproducible enough to rebuild the project six months later, but
not so generalized that they stop describing this project.
