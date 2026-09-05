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

Keep commits modular. Each commit should explain one useful change and leave the
repo in a working state.

Good commit examples:

```text
Add VPC and subnet Terraform resources
Add Dockerfile for web app
Configure Prometheus scrape target
Document deployment runbook
```

Avoid mixed commits such as Terraform, Ansible, docs, and app changes all in one
commit unless they are inseparable.

Before committing:

```bash
git status
git diff
```

## Pull Requests

Open a pull request for each feature branch before merging into `main`.

Each PR should include:

- What changed
- How it was tested
- Screenshots or URLs when the change affects the running app, docs, or Grafana
- Any known limitation

Small PRs are easier to review and easier to fix.

## Merge Rule

Merge only after the branch has been checked locally and the PR description is
clear. Prefer squash merge for small feature branches so `main` stays readable.

After merging:

```bash
git checkout main
git pull
git branch -d feature/branch-name
```

## Private Notes

Do not put private planning, scratch notes, credentials, `.env` files, keys, or
generated secrets into commits. Keep the submitted repository limited to the
implementation, reproducible configuration, and clean documentation.
