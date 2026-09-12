.PHONY: status health park unpark help

help:
	@echo "DevOps Bootcamp Platform Lifecycle Management"
	@echo ""
	@echo "Available commands:"
	@echo "  make status    - Read-only status report of EC2, 5 network resources, and endpoints"
	@echo "  make health    - Probe web.hasb.dev and monitoring.hasb.dev endpoints"
	@echo "  make park      - Gracefully stop compute fleet and clean up 5-resource network stack"
	@echo "  make unpark    - Restore network stack via guarded plan/apply, start compute, assert health"
	@echo ""

status:
	python3 scripts/platform.py status

health:
	python3 scripts/platform.py health

park:
	python3 scripts/platform.py park

unpark:
	python3 scripts/platform.py unpark
