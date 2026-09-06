# devops-bootcamp-project

Capstone repository for the DevOps Bootcamp 2026 final project.

## Directory Structure

```text
devops-bootcamp-project/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── secrets-management.md
│   ├── documentation-conventions.md
│   ├── git-workflow.md
│   ├── terraform.md
│   ├── docker.md
│   ├── ansible.md
│   ├── cicd.md
│   ├── runbook.md
│   ├── monitoring.md
│   ├── cloudflare.md
│   └── submission.md
├── app/
│   ├── Dockerfile
│   ├── compose.yaml
│   └── src/
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── providers.tf
│   └── terraform.tfvars.example
├── ansible/
│   ├── inventory.ini.example
│   ├── playbook.yml
│   ├── roles/
│   │   ├── docker/
│   │   ├── web/
│   │   └── monitoring/
│   └── group_vars/
├── monitoring/
│   ├── prometheus.yml
│   └── grafana/
│       └── dashboards/
└── scripts/
    ├── deploy.sh
    └── smoke-test.sh
```
