# Secrets Management

This project uses Infisical Cloud as the central store for secrets. AWS IAM and
OpenID Connect (OIDC) are used where possible so permanent credentials do not
need to exist.

## Interactive Secrets Architecture

The platform enforces a Zero-Trust secrets architecture that decouples cloud provider authorization from runtime application secrets. Infisical Cloud (`devops-bootcamp-project`, environment `dev`) serves as the central secrets vault, organized strictly by functional path (`/ansible` and `/terraform-cloudflare`).

Workload identities and operators authenticate through scoped, ephemeral mechanisms:

- **Human Operator / Admin**: Configures secrets via the Infisical Web UI with 2FA TOTP and executes `infisical run --env=dev --path=/terraform-cloudflare -- terraform apply` to inject `CLOUDFLARE_API_TOKEN` for declarative edge DNS, SSL rulesets, and tunnels.
- **Ansible Controller**: The durable target path is for the Ansible Controller to authenticate to Infisical Cloud via Infisical AWS Auth, using its EC2 IAM instance profile. Until that machine identity is configured, the documented interactive/controller login path remains the manual fallback. When invoked, it executes `infisical run --env=dev --path=/ansible -- ansible-playbook playbook.yml` to inject runtime credentials (`GRAFANA_ADMIN_PASSWORD`, `CLOUDFLARE_TUNNEL_TOKEN`) directly into playbook process memory without writing secrets to disk or Git.
- **GitHub Actions & AWS IAM**: Decoupled from application secrets. CI/CD workflows authenticate via GitHub OIDC to assume short-lived AWS IAM deployer roles (`sts.amazonaws.com`), completely eliminating static cloud credentials from repository secrets.

!!! tip "Interactive Architecture Canvas"
    Click the architecture blueprint preview below or <a href="../assets/secrets-management.html" target="_blank" rel="noopener"><strong>Open Interactive Secrets Architecture →</strong></a> for full-screen pan, zoom, component inspection, and flow tracing generated via Archify.

<div style="margin: 1.25rem 0 2rem; text-align: center;">
  <a href="../assets/secrets-management.html" class="only-dark" target="_blank" rel="noopener" style="display: block; max-width: 860px; margin: 0 auto; border-radius: 8px; overflow: hidden; border: 1px solid var(--md-default-fg-color--lightest); box-shadow: 0 4px 16px rgba(0,0,0,0.2); transition: transform 0.2s ease, box-shadow 0.2s ease;">
    <img src="../assets/secrets-management.visual-check.1440x900.dark.png" alt="DevOps Platform Secrets Management Architecture" style="width: 100%; max-height: 400px; object-fit: cover; object-position: top center; display: block;" />
  </a>
  <a href="../assets/secrets-management.html" class="only-light" target="_blank" rel="noopener" style="display: block; max-width: 860px; margin: 0 auto; border-radius: 8px; overflow: hidden; border: 1px solid var(--md-default-fg-color--lightest); box-shadow: 0 4px 16px rgba(0,0,0,0.08); transition: transform 0.2s ease, box-shadow 0.2s ease;">
    <img src="../assets/secrets-management.visual-check.1440x900.light.png" alt="DevOps Platform Secrets Management Architecture" style="width: 100%; max-height: 400px; object-fit: cover; object-position: top center; display: block;" />
  </a>
  <div style="margin-top: 1rem;">
    <a href="../assets/secrets-management.html" target="_blank" rel="noopener" class="md-button md-button--primary">
      Open Interactive Secrets Architecture →
    </a>
  </div>
</div>

---

## Decision

Use the Infisical Cloud free tier. Do not self-host Infisical as part of the
baseline.

Both deployment models provide the same core secrets-management platform, but
their operational responsibilities differ:

| Concern | Infisical Cloud free tier | Self-hosted Infisical |
| --- | --- | --- |
| Setup | Create an account and project | Deploy Infisical, PostgreSQL and Redis |
| Operations | Infisical manages availability and upgrades | We manage uptime, TLS, upgrades, monitoring and recovery |
| Data location | Infisical-managed infrastructure | Infrastructure we control |
| Cost | No charge within current free-tier limits | Compute, storage, backups and operational time |
| Capacity | Currently five human or machine identities, unlimited projects | Determined by the deployment and licence |
| Failure ownership | Managed-service dependency | Our service, database or cache can fail |
| Best fit | Single-operator project with a small identity count | Compliance or control requirements that justify operating another platform |

Self-hosting would add a new critical service whose Docker Compose deployment
requires at least three containers: Infisical, PostgreSQL and Redis. It also
creates a second set of bootstrap secrets, including the Infisical encryption
key, authentication secret and database credentials. That work does not improve
this project's AWS, Ansible, application or monitoring path.

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
| Grafana scoped viewer password | Infisical, then share outside the public repository |
| Application signing key or external API token | Infisical |
| Database password, if a database is added | Infisical |
| AWS credentials for GitHub Actions | Do not create; use GitHub OIDC to assume an AWS role |
| AWS credentials on EC2 | Do not create; use EC2 instance profiles |
| GitHub workflow token | Use the job's temporary `GITHUB_TOKEN` |
| Region, account ID, domains, IP addresses and repository names | Normal configuration |
| Infisical project and machine-identity IDs | Normal configuration; these are identifiers, not credentials |

## Secret Layout

Use one Infisical project named `devops-bootcamp-project` and its `dev`
environment. Secrets are organized strictly by functional path:

```text
/ansible
  CLOUDFLARE_TUNNEL_TOKEN
  GRAFANA_ADMIN_PASSWORD

/terraform-cloudflare
  CLOUDFLARE_API_TOKEN
```

Do not add placeholder secrets merely to fill this layout. Empty folders and
unused credentials create maintenance work without protecting anything.

## Identity And Delivery

### Secrets Architecture Diagram

The end-to-end secrets flow—spanning human administration, GitHub OIDC authentication, EC2 IAM machine identity, and ephemeral playbook injection—is modeled in the <a href="../assets/secrets-management.html" target="_blank" rel="noopener">Interactive Secrets Architecture Canvas</a> (source: <a href="../assets/secrets-management.architecture.json">secrets-management.architecture.json</a>).

### Human administrator

Use the normal Infisical account with two-factor authentication for setup and
emergency administration. Do not share the administrator account. Issue a
separate scoped credential for anyone else who needs access.

### GitHub Actions

Create a machine identity when the CI/CD workflow first needs an Infisical
secret. Authenticate it using GitHub OIDC, not an Infisical client secret. The
workflow receives a short-lived token and injects only the selected environment
and path for the lifetime of the job.

See [Infisical's GitHub Actions OIDC guide](https://infisical.com/docs/integrations/cicd/githubactions).

### Ansible controller

The durable target path is for the Ansible Controller to authenticate to Infisical Cloud via Infisical AWS Auth, using its EC2 IAM instance profile. Until that machine identity is configured, the documented interactive/controller login path remains the manual fallback.

Once configured, the Infisical machine identity trusts the controller EC2 instance's IAM role, allowing authentication without an Infisical client secret:

```bash
export INFISICAL_TOKEN="$(infisical login \
  --method=aws-iam \
  --machine-identity-id="$INFISICAL_MACHINE_IDENTITY_ID" \
  --silent \
  --plain)"

infisical run \
  --projectId="$INFISICAL_PROJECT_ID" \
  --env=dev \
  --path=/ansible \
  -- ansible-playbook playbook.yml

unset INFISICAL_TOKEN
```

The final secret paths will be chosen with the playbook structure. This command
documents the authentication flow, not a command to run before those IDs and
paths exist.

See [Infisical CLI AWS IAM login](https://infisical.com/docs/cli/commands/login)
and [AWS Auth](https://infisical.com/docs/documentation/platform/identities/aws-auth).

## Automated Credential Lifecycle & Day-2 Container Synchronization

Containerized stateful applications often behave differently on Day 0 (empty volume initialization) versus Day 2 (routine secret rotation on an existing volume):

* **The Day-2 Volume Quirk**: When Grafana starts with an empty SQLite volume (`grafana-data`), it initializes its admin account from `GF_SECURITY_ADMIN_PASSWORD`. However, when secrets are rotated in Infisical and the stack is restarted, Grafana intentionally preserves the password stored in its internal SQLite database (`/var/lib/grafana/grafana.db`) to avoid overwriting web UI configurations.
* **Automated Playbook Synchronization**: Rather than requiring manual container shell resets or exposing passwords in SSM command parameters, `ansible/playbook.yml` Play 3 implements automated, idempotent Day-2 credential synchronization:
  1. **Authentication Probe**: Tests live basic auth against `/api/user/preferences` using `grafana_admin_password`. If authentication succeeds (`HTTP 200`), the synchronization step is skipped (`changed=0`).
  2. **In-Container Password Reset**: If authentication returns `HTTP 401 Unauthorized`, the playbook executes `docker exec -i grafana grafana-cli admin reset-admin-password --password-from-stdin` via standard input (`stdin`). This updates SQLite directly inside the container without restarting the service (`changed=1`).
  3. **Verification Assertion**: Verifies that subsequent authentication requests succeed (`HTTP 200`).
* **Zero-Exposure Guarantees**:
  - `no_log: true` suppresses credential printing in Ansible task output and log files.
  - `--password-from-stdin` prevents passwords from appearing in `/proc`, `ps aux`, or process tables.
  - In Ansible over SSM transport, tasks execute via the S3 relay bucket directly to Python on the target host; zero plain-text secrets enter AWS SSM command history or CloudTrail audit logs.

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
  where the current plan supports that restriction. See `Plan Constraints`.
- Rotate a secret immediately if it appears in Git history, logs, screenshots or
  published documentation. Removing the visible text is not sufficient.
- Keep externally shared credentials separate from administrator credentials and
  revoke them when the access period ends.

## Plan Constraints

The free tier allows five human or machine identities and unlimited projects.
Access Controls are a paid feature, currently 20 USD per identity per month on
Pro. Two consequences follow on the free tier:

- Per-path scoping of a machine identity is not enforceable. An identity that
  can read the project can read every path in it. Treat path separation as
  organisation, not as an access boundary.
- The five-identity budget covers the human administrator and every machine
  identity. Create an identity only when its consumer exists, and remove
  identities that no longer have one.

Revisit this section if the plan changes, because the scoping rule above becomes
enforceable as soon as Access Controls are available.

## Setup Checklist

Complete these items before the first real secret is stored:

- [ ] Create the Infisical Cloud account and enable two-factor authentication.
- [ ] Store the account recovery codes outside Infisical.
- [ ] Create project `devops-bootcamp-project` with environment `dev`.
- [ ] Confirm the current free-tier identity and access-control limits.
- [ ] Record only the non-secret project identifier in local planning notes.
- [ ] Keep all real values out of Git and Terraform state.

Complete these when their consumer exists, not before. Each one depends on
something that must be created first:

- [ ] Add Cloudflare secrets once the tunnel or API integration exists.
- [ ] Add Grafana credentials once the monitoring deployment exists.
- [ ] Create the controller machine identity after its EC2 IAM role exists,
  because the identity trusts that role.
- [ ] Create the GitHub OIDC machine identity once a workflow needs a secret.
- [ ] In the GitHub Actions workflow, put non-secret values (AWS region, role ARN
  to assume, bucket names) in GitHub Actions variables, not hardcoded in YAML or
  stored as GitHub secrets.
- [ ] Verify each identity can read its required path, and record which
  restrictions the current plan cannot enforce.
