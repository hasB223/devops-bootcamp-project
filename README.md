# devops-bootcamp-project

Capstone repository for the DevOps Bootcamp 2026 final project.

## Directory Structure

```text
devops-bootcamp-project/
├── README.md
├── implementation_plan.md
├── docs/
│   ├── architecture.md
│   ├── runbook.md
│   ├── monitoring.md
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

## Notes

`implementation_plan.md` is a working document for planning and tracking the
build. Keep it in git so the project decisions are preserved, but do not include
it in the published GitHub Pages submission unless useful parts are promoted into
the formal docs.
