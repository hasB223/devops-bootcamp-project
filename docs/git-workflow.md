# Git Workflow

Use GitHub as the collaboration and review layer for this project. Keep `main`
stable, work in feature branches, and merge through pull requests.

## Branches

Create one branch per focused change:

```bash
git checkout main
git pull
git checkout -b feature/terraform-foundation
```

Use short branch names that describe the work:

```text
feature/terraform-foundation
feature/app-container
feature/ansible-deploy
feature/monitoring
feature/docs
fix/security-group-rules
docs/submission-evidence
```

## Commits

Use Conventional Commits. Keep commits modular: each commit should explain one
useful change and leave the repo in a working state.

```text
<type>(<scope>): <subject>
```

### Types

| Type | Use for |
| --- | --- |
| `feat` | New infrastructure, application capability, or pipeline stage |
| `fix` | Correcting something broken or misconfigured |
| `refactor` | Restructuring that does not change the applied result |
| `docs` | Documentation only |
| `chore` | Ignore files, tooling, and housekeeping |
| `ci` | Changes to the pipeline definition itself |

Treat the infrastructure as the product. Adding a NAT Gateway is `feat`, not
`chore`. Correcting a security group rule that blocks required traffic is `fix`.
Moving resources between files without changing `terraform plan` output is
`refactor`.

### Scopes

Scope names the layer the change belongs to, matching the documentation map:

```text
terraform  docker  ansible  monitoring  cloudflare  cicd  secrets  app  git
```

Scope names the layer, never the kind of file. A documentation change about
Terraform is `docs(terraform)`, not `docs(docs)`.

### Subject

Imperative mood, lowercase after the colon, no trailing period, under about 72
characters. Use the body to explain why when the subject is not enough.

```text
feat(terraform): add VPC and subnet resources
feat(docker): add Dockerfile for the web app
fix(terraform): allow HTTP ingress on the web security group
refactor(terraform): move networking resources into their own file
docs(monitoring): document the Prometheus scrape configuration
chore(git): ignore local Terraform state files
```

Avoid mixed commits such as Terraform, Ansible, docs, and app changes all in one
commit unless they are inseparable.

Before committing:

```bash
git status
git diff
```

This convention is documented, not enforced by a hook. If it later needs
enforcing, add the check to the same CI workflow that runs `terraform fmt
-check`.

## Pull Requests

Open a pull request for each feature branch before merging into `main`.

Title the pull request using the same Conventional Commits format as a commit.
Under squash merging the title becomes the commit subject on `main`, so a
non-conventional title breaks the history even when every branch commit was
clean.

Each PR should include:

- What changed
- How it was tested
- Screenshots or URLs when the change affects the running app, docs, or Grafana
- Any known limitation

Small PRs are easier to review and easier to fix.

## Merge Rule

Merge only after the branch has been checked locally and the PR description is
clear. Prefer squash merge for small feature branches so `main` stays readable.

Squash merging composes the commit message from the pull request. Set
`Settings -> General -> Pull Requests -> Default commit message for squash
merging` to `Pull request title and description` so `main` records the
conventional title and the reasoning, rather than a list of branch commits.

Note that GitHub falls back to the single commit's own message when a branch
contains exactly one commit, so both the commits and the PR title need to follow
the convention.

After merging:

```bash
git checkout main
git pull
git branch -d feature/branch-name
```

## Private Notes

Do not put private planning, scratch notes, credentials, `.env` files, keys, or
generated secrets into commits. Keep the public repository limited to the
implementation, reproducible configuration, and clean documentation.
