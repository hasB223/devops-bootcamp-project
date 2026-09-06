# Secrets Management

This project uses Infisical Cloud as the central store for secrets. AWS IAM and
OpenID Connect (OIDC) are used where possible so permanent credentials do not
need to exist.

## Decision

Use the Infisical Cloud free tier for the capstone. Do not self-host Infisical as
part of the baseline.

Both deployment models provide the same core secrets-management platform, but
their operational responsibilities differ:

| Concern | Infisical Cloud free tier | Self-hosted Infisical |
| --- | --- | --- |
| Setup | Create an account and project | Deploy Infisical, PostgreSQL and Redis |
| Operations | Infisical manages availability and upgrades | We manage uptime, TLS, upgrades, monitoring and recovery |
| Data location | Infisical-managed infrastructure | Infrastructure we control |
| Cost | No charge within current free-tier limits | Compute, storage, backups and operational time |
| Capacity | Currently five human or machine identities | Determined by the deployment and licence |
| Failure ownership | Managed-service dependency | Our service, database or cache can fail |
| Best fit | Individual capstone | Compliance or control requirements that justify operating another platform |

Self-hosting would add a new critical service whose Docker Compose deployment
requires at least three containers: Infisical, PostgreSQL and Redis. It also
creates a second set of bootstrap secrets, including the Infisical encryption
key, authentication secret and database credentials. That work does not improve
the capstone's required AWS, Ansible, application or monitoring path.

References:

- [Cloud and self-hosted deployment models](https://infisical.com/docs/documentation/getting-started/concepts/deployment-models)
- [Cloud pricing and current free-tier limits](https://infisical.com/pricing)
- [Docker Compose deployment and requirements](https://infisical.com/docs/self-hosting/deployment-options/docker-compose)

## What Counts As A Secret

A secret is a value that grants access or proves identity. A configuration value
describes where or how a system runs but does not grant access by itself.

| Value | Handling |
| --- | --- |
| Cloudflare tunnel or API token | Infisical |
| Grafana administrator password | Infisical |
| Grafana reviewer password | Infisical, then share outside the public repository |
| Application signing key or external API token | Infisical |
| Database password, if a database is added | Infisical |
| AWS credentials for GitHub Actions | Do not create; use GitHub OIDC to assume an AWS role |
| AWS credentials on EC2 | Do not create; use EC2 instance profiles |
| GitHub workflow token | Use the job's temporary `GITHUB_TOKEN` |
| Region, account ID, domains, IP addresses and repository names | Normal configuration |
| Infisical project and machine-identity IDs | Normal configuration; these are identifiers, not credentials |

## Secret Layout

Use one Infisical project named `devops-bootcamp-project` and its `prod`
environment. Add a secret only when a deployed component consumes it.

```text
/ansible
  CLOUDFLARE_TUNNEL_TOKEN
  GF_SECURITY_ADMIN_PASSWORD
  GRAFANA_REVIEWER_PASSWORD

/app
  APP_SECRET                 # only when the application needs one
  DATABASE_URL               # only if a database is added
```

Do not add placeholder secrets merely to fill this layout. Empty folders and
unused credentials create maintenance work without protecting anything.

## Identity And Delivery

### Human administrator

Use the normal Infisical account with two-factor authentication for setup and
emergency administration. Do not share this account with the reviewer.

### GitHub Actions

Create a machine identity when the CI/CD workflow first needs an Infisical
secret. Authenticate it using GitHub OIDC, not an Infisical client secret. The
workflow receives a short-lived token and injects only the selected environment
and path for the lifetime of the job.

See [Infisical's GitHub Actions OIDC guide](https://infisical.com/docs/integrations/cicd/githubactions).

### Ansible controller

Create an Infisical machine identity that trusts the controller EC2 instance's
IAM role. The controller then authenticates without an Infisical client secret:

```bash
export INFISICAL_TOKEN="$(infisical login \
  --method=aws-iam \
  --machine-identity-id="$INFISICAL_MACHINE_IDENTITY_ID" \
  --silent \
  --plain)"

infisical run \
  --projectId="$INFISICAL_PROJECT_ID" \
  --env=prod \
  --path=/ansible \
  -- ansible-playbook playbook.yml

unset INFISICAL_TOKEN
```

The final secret paths will be chosen with the playbook structure. This command
documents the authentication flow, not a command to run before those IDs and
paths exist.

See [Infisical CLI AWS IAM login](https://infisical.com/docs/cli/commands/login)
and [AWS Auth](https://infisical.com/docs/documentation/platform/identities/aws-auth).

## Safety Rules

- Never commit secret values, `.env` files, tokens, private keys or generated
  credentials.
- Never place secret values in Terraform arguments unless the resource truly
  requires them; values can otherwise persist in Terraform state.
- Mark Ansible tasks that handle secret values with `no_log: true`.
- Do not print environment variables or enable shell tracing around secret
  retrieval.
- Give GitHub Actions and the Ansible controller separate machine identities.
- Scope each identity to only the project environment and paths it consumes,
  within the access controls available on the selected plan.
- Rotate a secret immediately if it appears in Git history, logs, screenshots or
  submission documentation. Removing the visible text is not sufficient.
- Keep reviewer credentials separate from administrator credentials and revoke
  them after the review.

## Phase 0 Checklist

Complete these items before Phase 1 needs a real secret:

- [ ] Create the Infisical Cloud account and enable two-factor authentication.
- [ ] Create project `devops-bootcamp-project` with environment `prod`.
- [ ] Confirm the current free-tier identity and access-control limits.
- [ ] Record only the non-secret project identifier in local planning notes.
- [ ] Keep all real values out of Git and Terraform state.

Complete these just in time, when their consumers exist:

- [ ] Add Cloudflare secrets before the Cloudflare phase.
- [ ] Add Grafana credentials before the monitoring deployment.
- [ ] Create the controller machine identity after its IAM role exists.
- [ ] Create the GitHub OIDC machine identity when the workflow needs secrets.
- [ ] When writing the GitHub Actions workflow, put non-secret values (AWS
  region, role ARN to assume, bucket names) in GitHub Actions variables, not
  hardcoded in YAML or stored as GitHub secrets.
- [ ] Verify each identity can read its required path and cannot read unrelated
  secrets where the selected plan supports that restriction.
