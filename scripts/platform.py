#!/usr/bin/env python3
"""
Platform Lifecycle Automation Engine
DevOps Bootcamp Project - hasb.dev

Provides automated, guarded lifecycle operations:
  - status: Read-only inspection of compute, 5-resource network stack, and endpoints.
  - health: Read-only probe of web and monitoring endpoints.
  - park:   Gracefully stops compute fleet and cleans up hourly cost drivers (NAT & private routing).
  - unpark: Validated restore of 5-resource network stack via guarded plan/apply, starts compute, and verifies health.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ANSI Colors for rich terminal diagnostics
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_CYAN = "\033[96m"
COLOR_GRAY = "\033[90m"

# Project Constants
DEFAULT_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-southeast-1"
PROJECT_TAG = "devops-bootcamp-project"
ALLOWED_UNPARK_RESOURCES = {
    "aws_eip.nat",
    "aws_nat_gateway.gw",
    "aws_route_table.private",
    "aws_route_table_association.private",
    "aws_vpc_endpoint.s3",
}

WEB_ENDPOINTS = [
    ("Web Application", "https://web.hasb.dev"),
    ("Grafana Monitoring", "https://monitoring.hasb.dev"),
]


def log_info(msg: str) -> None:
    print(f"{COLOR_CYAN}==>{COLOR_RESET} {COLOR_BOLD}{msg}{COLOR_RESET}", flush=True)


def log_success(msg: str) -> None:
    print(f"{COLOR_GREEN}[OK]{COLOR_RESET} {msg}", flush=True)


def log_warn(msg: str) -> None:
    print(f"{COLOR_YELLOW}[WARN]{COLOR_RESET} {msg}", flush=True)


def log_error(msg: str) -> None:
    print(f"{COLOR_RED}[ERROR]{COLOR_RESET} {msg}", flush=True)


def run_aws_cli(args: list[str], region: str = DEFAULT_REGION, check: bool = True) -> tuple[int, str, str]:
    """Execute AWS CLI with pagination disabled and return (exit_code, stdout, stderr)."""
    cmd = ["aws", "--region", region, "--output", "json"] + args
    env = os.environ.copy()
    env["AWS_PAGER"] = ""
    env["AWS_DEFAULT_REGION"] = region
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if check and res.returncode != 0:
        raise RuntimeError(f"AWS CLI command failed ({' '.join(cmd)}):\n{res.stderr.strip()}")
    return res.returncode, res.stdout, res.stderr


def check_self_termination_guard(target_instance_ids: set[str], force: bool = False) -> None:
    """Safety Guard: Prevent self-termination if executing on an EC2 target node (e.g. ansible-controller)."""
    if force:
        return
    try:
        # Request IMDSv2 token with 1s timeout
        req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            token = resp.read().decode().strip()

        req2 = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req2, timeout=1.0) as resp:
            current_id = resp.read().decode().strip()

        if current_id in target_instance_ids:
            log_error("Self-Termination Guard Blocked Execution!")
            print(
                f"\nYou are executing this script directly on target node: {COLOR_BOLD}{current_id}{COLOR_RESET}."
            )
            print("Stopping this instance would abort execution mid-flight and cause partial infrastructure drift.")
            print("Please execute 'park' from an external runner (local Mac/workstation or GitHub Actions).")
            print("To override this safeguard, pass --force-self-park.\n")
            sys.exit(1)
    except Exception:
        # Non-EC2 host (Mac, developer workstation, or GitHub Actions runner)
        pass


def discover_compute_fleet(region: str = DEFAULT_REGION) -> list[dict]:
    """Discover project EC2 compute instances tagged with AutoPark=true."""
    code, stdout, _ = run_aws_cli(
        [
            "ec2",
            "describe-instances",
            "--filters",
            f"Name=tag:Project,Values={PROJECT_TAG}",
            "Name=tag:AutoPark,Values=true",
        ],
        region=region,
    )
    data = json.loads(stdout)
    instances = []
    for res in data.get("Reservations", []):
        for inst in res.get("Instances", []):
            tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
            instances.append(
                {
                    "id": inst.get("InstanceId"),
                    "name": tags.get("Name", "unknown"),
                    "role": tags.get("Role", "unknown"),
                    "auto_park": tags.get("AutoPark", "false").lower() == "true",
                    "state": inst.get("State", {}).get("Name", "unknown"),
                    "private_ip": inst.get("PrivateIpAddress", "N/A"),
                    "public_ip": inst.get("PublicIpAddress", "None"),
                }
            )
    instances.sort(key=lambda x: x["name"])
    return instances


def discover_network_resources(region: str = DEFAULT_REGION) -> dict:
    """
    Mixed discovery rules for the 5-resource parked network stack:
      1. aws_eip.nat: Name tag lookup -> ALLOCATED (Active) or RELEASED (Parked)
      2. aws_nat_gateway.gw: Name tag + state -> AVAILABLE (Active) or ABSENT (Parked)
      3. aws_route_table.private: Name tag lookup -> PRESENT (Active) or ABSENT (Parked)
      4. aws_route_table_association.private: Subnet lookup -> ASSOCIATED (Active) or DISSOCIATED (Parked)
      5. aws_vpc_endpoint.s3: Name tag + RouteTableIds -> ATTACHED (Active) or DETACHED/ABSENT (Parked)
    """
    # 1. NAT EIP
    _, eip_out, _ = run_aws_cli(
        ["ec2", "describe-addresses", "--filters", f"Name=tag:Project,Values={PROJECT_TAG}", "Name=tag:Name,Values=devops-nat-eip"],
        region=region,
        check=False,
    )
    eip_data = json.loads(eip_out).get("Addresses", []) if eip_out else []
    if eip_data:
        eip_info = {"status": "ALLOCATED", "id": eip_data[0].get("AllocationId"), "ip": eip_data[0].get("PublicIp"), "active": True}
    else:
        eip_info = {"status": "RELEASED (Parked)", "id": None, "ip": None, "active": False}

    # 2. NAT Gateway
    _, nat_out, _ = run_aws_cli(
        ["ec2", "describe-nat-gateways", "--filter", f"Name=tag:Project,Values={PROJECT_TAG}", "Name=tag:Name,Values=devops-ngw", "Name=state,Values=available,pending,deleting"],
        region=region,
        check=False,
    )
    nat_data = json.loads(nat_out).get("NatGateways", []) if nat_out else []
    if nat_data:
        st = nat_data[0].get("State", "unknown").upper()
        eip_info_gw = nat_data[0].get("NatGatewayId")
        nat_info = {"status": st, "id": eip_info_gw, "active": (st == "AVAILABLE")}
    else:
        nat_info = {"status": "ABSENT (Parked)", "id": None, "active": False}

    # 3. Private Route Table
    _, rt_out, _ = run_aws_cli(
        ["ec2", "describe-route-tables", "--filters", f"Name=tag:Project,Values={PROJECT_TAG}", "Name=tag:Name,Values=devops-private-route"],
        region=region,
        check=False,
    )
    rt_data = json.loads(rt_out).get("RouteTables", []) if rt_out else []
    if rt_data:
        rt_id = rt_data[0].get("RouteTableId")
        rt_info = {"status": "PRESENT", "id": rt_id, "active": True}
    else:
        rt_id = None
        rt_info = {"status": "ABSENT (Parked)", "id": None, "active": False}

    # 4. Route Table Association (lookup by private subnet)
    _, sub_out, _ = run_aws_cli(
        ["ec2", "describe-subnets", "--filters", f"Name=tag:Project,Values={PROJECT_TAG}", "Name=tag:Name,Values=devops-private-subnet"],
        region=region,
        check=False,
    )
    sub_data = json.loads(sub_out).get("Subnets", []) if sub_out else []
    sub_id = sub_data[0].get("SubnetId") if sub_data else None

    assoc_info = {"status": "DISSOCIATED (Parked)", "id": None, "active": False}
    if sub_id and rt_id:
        _, sub_rt_out, _ = run_aws_cli(
            ["ec2", "describe-route-tables", "--filters", f"Name=association.subnet-id,Values={sub_id}"],
            region=region,
            check=False,
        )
        sub_rt_data = json.loads(sub_rt_out).get("RouteTables", []) if sub_rt_out else []
        for rtb in sub_rt_data:
            if rtb.get("RouteTableId") == rt_id:
                for a in rtb.get("Associations", []):
                    if a.get("SubnetId") == sub_id:
                        assoc_info = {"status": "ASSOCIATED", "id": a.get("RouteTableAssociationId"), "active": True}
                        break

    # 5. S3 VPC Gateway Endpoint
    _, vpce_out, _ = run_aws_cli(
        ["ec2", "describe-vpc-endpoints", "--filters", f"Name=tag:Project,Values={PROJECT_TAG}", "Name=tag:Name,Values=devops-s3-endpoint"],
        region=region,
        check=False,
    )
    vpce_data = json.loads(vpce_out).get("VpcEndpoints", []) if vpce_out else []
    if vpce_data:
        vpce_id = vpce_data[0].get("VpcEndpointId")
        attached_rts = vpce_data[0].get("RouteTableIds", [])
        if rt_id and rt_id in attached_rts:
            vpce_info = {"status": "ATTACHED", "id": vpce_id, "active": True}
        else:
            vpce_info = {"status": "DETACHED (Parked)", "id": vpce_id, "active": False}
    else:
        vpce_info = {"status": "ABSENT (Parked)", "id": None, "active": False}

    active_count = sum([eip_info["active"], nat_info["active"], rt_info["active"], assoc_info["active"], vpce_info["active"]])
    if active_count == 5:
        overall_state = "ACTIVE"
    elif active_count == 0:
        overall_state = "PARKED"
    else:
        overall_state = "PARTIAL_DRIFT"

    return {
        "eip": eip_info,
        "nat": nat_info,
        "route_table": rt_info,
        "route_association": assoc_info,
        "s3_endpoint": vpce_info,
        "overall_state": overall_state,
        "active_count": active_count,
    }


def probe_endpoints() -> list[dict]:
    """Probe public web and monitoring endpoints with HTTP status and latency."""
    results = []
    for name, url in WEB_ENDPOINTS:
        t0 = time.time()
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "devops-platform-healthcheck/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                status_code = resp.status
                duration_ms = int((time.time() - t0) * 1000)
                results.append({"name": name, "url": url, "code": status_code, "latency_ms": duration_ms, "ok": (status_code == 200)})
        except urllib.error.HTTPError as e:
            duration_ms = int((time.time() - t0) * 1000)
            results.append({"name": name, "url": url, "code": e.code, "latency_ms": duration_ms, "ok": (e.code == 200)})
        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            results.append({"name": name, "url": url, "code": 0, "latency_ms": duration_ms, "error": str(e), "ok": False})
    return results


def cmd_status(region: str = DEFAULT_REGION, as_json: bool = False) -> None:
    """Read-only inspection of compute fleet, 5-resource network stack, and live endpoints."""
    instances = discover_compute_fleet(region=region)
    net = discover_network_resources(region=region)
    endpoints = probe_endpoints()

    if as_json:
        print(json.dumps({"compute": instances, "network": net, "endpoints": endpoints}, indent=2))
        return

    print("\n" + "=" * 80)
    print(f"{COLOR_BOLD}DevOps Bootcamp Platform - Live Status Report{COLOR_RESET}")
    print(f"Region: {COLOR_CYAN}{region}{COLOR_RESET} | Project: {COLOR_CYAN}{PROJECT_TAG}{COLOR_RESET} | Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 80)

    # 1. Compute Fleet
    print(f"\n{COLOR_BOLD}1. Compute Fleet (EC2 Instances){COLOR_RESET}")
    print(f"{'Instance ID':<21} {'Name':<20} {'Role':<12} {'State':<12} {'Private IP':<14} {'Public IP':<15}")
    print("-" * 94)
    for inst in instances:
        st = inst["state"]
        color = COLOR_GREEN if st == "running" else (COLOR_YELLOW if st in ["pending", "stopping"] else COLOR_GRAY)
        print(f"{inst['id']:<21} {inst['name']:<20} {inst['role']:<12} {color}{st:<12}{COLOR_RESET} {inst['private_ip']:<14} {inst['public_ip']:<15}")

    # 2. 5-Resource Network Stack
    print(f"\n{COLOR_BOLD}2. Parked-Network Stack (5 Dependency Resources){COLOR_RESET}")
    print(f"{'Resource':<32} {'AWS Resource ID':<24} {'Status':<22}")
    print("-" * 78)

    net_rows = [
        ("1. aws_eip.nat", net["eip"]["id"] or "N/A", net["eip"]["status"], net["eip"]["active"]),
        ("2. aws_nat_gateway.gw", net["nat"]["id"] or "N/A", net["nat"]["status"], net["nat"]["active"]),
        ("3. aws_route_table.private", net["route_table"]["id"] or "N/A", net["route_table"]["status"], net["route_table"]["active"]),
        ("4. aws_route_table_association", net["route_association"]["id"] or "N/A", net["route_association"]["status"], net["route_association"]["active"]),
        ("5. aws_vpc_endpoint.s3", net["s3_endpoint"]["id"] or "N/A", net["s3_endpoint"]["status"], net["s3_endpoint"]["active"]),
    ]
    for name, res_id, status, is_active in net_rows:
        color = COLOR_GREEN if is_active else (COLOR_GRAY if "Parked" in status or "ABSENT" in status else COLOR_YELLOW)
        print(f"{name:<32} {res_id:<24} {color}{status:<22}{COLOR_RESET}")

    overall_color = COLOR_GREEN if net["overall_state"] == "ACTIVE" else (COLOR_GRAY if net["overall_state"] == "PARKED" else COLOR_RED)
    print(f"\nNetwork Status Classification: {overall_color}{COLOR_BOLD}{net['overall_state']}{COLOR_RESET} ({net['active_count']}/5 active)")

    # 3. HTTP Endpoints
    print(f"\n{COLOR_BOLD}3. Web & Telemetry Endpoints{COLOR_RESET}")
    print(f"{'Endpoint':<24} {'URL':<35} {'HTTP Status':<15} {'Latency':<10}")
    print("-" * 84)
    for ep in endpoints:
        code_str = f"HTTP {ep['code']}" if ep['code'] > 0 else "UNREACHABLE"
        code_color = COLOR_GREEN if ep["ok"] else COLOR_RED
        lat_str = f"{ep['latency_ms']} ms" if ep['code'] > 0 else "N/A"
        print(f"{ep['name']:<24} {ep['url']:<35} {code_color}{code_str:<15}{COLOR_RESET} {lat_str:<10}")

    print("=" * 80 + "\n")


def cmd_health() -> None:
    """Read-only probe of web and monitoring endpoints."""
    endpoints = probe_endpoints()
    all_ok = True
    for ep in endpoints:
        if ep["ok"]:
            log_success(f"{ep['name']} ({ep['url']}) -> HTTP {ep['code']} ({ep['latency_ms']} ms)")
        else:
            all_ok = False
            err = ep.get("error", f"HTTP {ep['code']}")
            log_error(f"{ep['name']} ({ep['url']}) -> {err}")
    if not all_ok:
        sys.exit(1)


def cmd_park(region: str = DEFAULT_REGION, dry_run: bool = False, force_self_park: bool = False) -> None:
    """Gracefully stop compute fleet and clean up the 5-resource network stack to halt hourly costs."""
    log_info("Starting Platform Parking Procedure...")

    # Gate 0: Discover Fleet & Verify Self-Termination Guard
    instances = discover_compute_fleet(region=region)
    target_ids = {inst["id"] for inst in instances}
    check_self_termination_guard(target_ids, force=force_self_park)

    # Gate 1: Inspect Compute Fleet
    running_instances = [inst for inst in instances if inst["state"] in ["running", "pending"]]
    if not running_instances:
        log_success("Gate 1: All compute instances are already stopped.")
    else:
        ids_to_stop = [inst["id"] for inst in running_instances]
        names_to_stop = ", ".join([f"{inst['name']} ({inst['id']})" for inst in running_instances])
        if dry_run:
            log_warn(f"[DRY-RUN] Gate 1: Would stop {len(ids_to_stop)} running instance(s): {names_to_stop}")
        else:
            log_info(f"Gate 1: Stopping {len(ids_to_stop)} instance(s): {names_to_stop}...")
            run_aws_cli(["ec2", "stop-instances", "--instance-ids"] + ids_to_stop, region=region)
            log_info("Waiting for instances to reach 'stopped' state...")
            run_aws_cli(["ec2", "wait", "instance-stopped", "--instance-ids"] + ids_to_stop, region=region)
            log_success("Gate 1: Compute fleet successfully stopped.")

    # Gate 2: Inspect 5-Resource Network Stack for Partial Drift
    net = discover_network_resources(region=region)
    if net["overall_state"] == "PARKED":
        log_success("Gate 2: All 5 network resources are already absent / parked.")
    else:
        if dry_run:
            log_warn(f"[DRY-RUN] Gate 2: Network state is '{net['overall_state']}' ({net['active_count']}/5 active).")
            log_warn("[DRY-RUN] Would execute targeted Terraform destroy to cascade 5-resource network cleanup.")
        else:
            log_info(f"Gate 2: Network state is '{net['overall_state']}'. Cleaning up hourly cost drivers via Terraform...")
            # If NAT Gateway exists, destroy NAT + EIP (Terraform cascade reliably tears down dependent routing)
            # If NAT Gateway is already absent (partial drift), target remaining route table & EIP resources
            if net["nat"]["active"] or net["nat"]["status"] in ["PENDING", "DELETING"]:
                targets = ["-target=aws_nat_gateway.gw", "-target=aws_eip.nat"]
            else:
                targets = [
                    "-target=aws_eip.nat",
                    "-target=aws_route_table_association.private",
                    "-target=aws_route_table.private",
                    "-target=aws_vpc_endpoint.s3",
                ]

            destroy_cmd = [
                "terraform",
                "-chdir=terraform",
                "destroy",
                "-var=instance_type=t3.small",
                "-var=key_name=devops-bootcamp-macbook-ed25519",
            ] + targets + ["-auto-approve"]
            log_info(f"Executing: {' '.join(destroy_cmd)}")
            res = subprocess.run(destroy_cmd)
            if res.returncode != 0:
                log_error("Terraform destroy encountered an error.")
                sys.exit(res.returncode)
            log_success("Gate 2: Terraform network destruction completed.")

    # Gate 3: Post-Park Verification
    if not dry_run:
        post_net = discover_network_resources(region=region)
        post_instances = discover_compute_fleet(region=region)
        active_inst = [i for i in post_instances if i["state"] != "stopped"]
        if post_net["overall_state"] == "PARKED" and not active_inst:
            log_success("Gate 3: Verified all 5 network resources are absent and all compute nodes are stopped.")
            print("\n" + "=" * 70)
            print(f"{COLOR_GREEN}{COLOR_BOLD}PLATFORM SUCCESSFULLY PARKED{COLOR_RESET}")
            print("Hourly charges halted: NAT Gateway ($0.045/hr) + EC2 compute ($0.00/hr).")
            print("Preserved assets: EBS volumes (~$4.80/mo) + Web EIP ($3.60/mo) + S3/ECR (~$0.15/mo).")
            print("Total parked cost posture: ~$8.55 / month.")
            print("=" * 70 + "\n")
        else:
            log_warn("Post-park check detected non-parked resources:")
            if active_inst:
                log_warn(f"Instances not stopped: {[i['name'] for i in active_inst]}")
            if post_net["overall_state"] != "PARKED":
                log_warn(f"Network state: {post_net['overall_state']} ({post_net['active_count']}/5 active)")


def cmd_unpark(
    region: str = DEFAULT_REGION,
    dry_run: bool = False,
    allow_unrelated_changes: bool = False,
    allow_replacements: bool = False,
) -> None:
    """Validated restore of 5-resource network stack via plan guard, starts compute, and asserts health."""
    log_info("Starting Platform Unparking Procedure...")

    # Gate 1: Network Stack Restore via Guarded Terraform Plan
    net = discover_network_resources(region=region)
    plan_file = "terraform/unpark.tfplan"

    if net["overall_state"] == "ACTIVE":
        log_success("Gate 1: Network infrastructure is already fully active. Skipping Terraform apply.")
    else:
        if dry_run:
            log_warn(f"[DRY-RUN] Gate 1: Network state is '{net['overall_state']}'. Would run guarded Terraform plan/apply.")
        else:
            log_info(f"Gate 1: Network state is '{net['overall_state']}'. Generating speculative unpark plan...")
            plan_cmd = [
                "terraform",
                "-chdir=terraform",
                "plan",
                "-out=unpark.tfplan",
                '-var=instance_type=t3.small',
                '-var=key_name=devops-bootcamp-macbook-ed25519',
            ]
            res = subprocess.run(plan_cmd)
            if res.returncode != 0:
                log_error("Terraform plan generation failed.")
                sys.exit(res.returncode)

            # Inspect plan JSON
            log_info("Inspecting generated plan against unpark allowlist...")
            show_cmd = ["terraform", "-chdir=terraform", "show", "-json", "unpark.tfplan"]
            show_res = subprocess.run(show_cmd, capture_output=True, text=True)
            if show_res.returncode != 0:
                log_error("Failed to parse plan JSON.")
                sys.exit(show_res.returncode)

            plan_data = json.loads(show_res.stdout)
            resource_changes = plan_data.get("resource_changes", [])

            foreign_changes = []
            replacement_changes = []

            for rc in resource_changes:
                addr = rc.get("address", "")
                actions = rc.get("change", {}).get("actions", [])
                if actions == ["no-op"] or not actions:
                    continue

                if addr not in ALLOWED_UNPARK_RESOURCES:
                    foreign_changes.append((addr, actions))

                # If an allowed resource requires deletion or replacement
                if "delete" in actions:
                    replacement_changes.append((addr, actions))

            if foreign_changes and not allow_unrelated_changes:
                if os.path.exists(plan_file):
                    os.remove(plan_file)
                log_error("Unpark Plan Guard Blocked Execution!")
                print("\nPlan contains unexpected changes outside the approved unpark allowlist:")
                for addr, acts in foreign_changes:
                    print(f"  - {COLOR_BOLD}{addr}{COLOR_RESET} -> {acts}")
                print("\nAborting unpark to prevent applying unrelated infrastructure changes.")
                print("To override this safeguard, pass --allow-unrelated-changes.\n")
                sys.exit(1)

            if replacement_changes and not allow_replacements:
                if os.path.exists(plan_file):
                    os.remove(plan_file)
                log_error("Unpark Plan Guard: Manual Review Required!")
                print("\nAllowed unpark resource requires destructive replacement or deletion:")
                for addr, acts in replacement_changes:
                    print(f"  - {COLOR_BOLD}{addr}{COLOR_RESET} -> {acts}")
                print("\nAuto-applying replacements during unpark is prohibited to avoid accidental data loss.")
                print("Review the plan manually. To force apply replacements, pass --allow-replacements.\n")
                sys.exit(1)

            log_success("Unpark Plan Guard Passed: Only approved 5-resource additions detected.")
            log_info("Applying unpark plan...")
            apply_cmd = ["terraform", "-chdir=terraform", "apply", "unpark.tfplan"]
            apply_res = subprocess.run(apply_cmd)
            if os.path.exists(plan_file):
                os.remove(plan_file)

            if apply_res.returncode != 0:
                log_error("Terraform apply failed.")
                sys.exit(apply_res.returncode)
            log_success("Gate 1: Network resources restored successfully.")

    # Gate 2: Await NAT Gateway 'available'
    if not dry_run:
        log_info("Gate 2: Verifying NAT Gateway availability...")
        for i in range(36):  # Up to 3 minutes
            _, nat_out, _ = run_aws_cli(
                ["ec2", "describe-nat-gateways", "--filter", f"Name=tag:Project,Values={PROJECT_TAG}", "Name=tag:Name,Values=devops-ngw"],
                region=region,
                check=False,
            )
            gws = json.loads(nat_out).get("NatGateways", []) if nat_out else []
            if gws and gws[0].get("State") == "available":
                log_success(f"Gate 2: NAT Gateway {gws[0].get('NatGatewayId')} is available.")
                break
            time.sleep(5)

    # Gate 3: Start Compute Fleet
    instances = discover_compute_fleet(region=region)
    stopped_instances = [inst for inst in instances if inst["state"] in ["stopped", "stopping"]]
    if not stopped_instances:
        log_success("Gate 3: All compute instances are already running.")
    else:
        ids_to_start = [inst["id"] for inst in stopped_instances]
        names_to_start = ", ".join([f"{inst['name']} ({inst['id']})" for inst in stopped_instances])
        if dry_run:
            log_warn(f"[DRY-RUN] Gate 3: Would start {len(ids_to_start)} instance(s): {names_to_start}")
        else:
            log_info(f"Gate 3: Starting {len(ids_to_start)} instance(s): {names_to_start}...")
            run_aws_cli(["ec2", "start-instances", "--instance-ids"] + ids_to_start, region=region)
            log_info("Waiting for compute instances to reach 'running' state...")
            run_aws_cli(["ec2", "wait", "instance-running", "--instance-ids"] + ids_to_start, region=region)
            log_success("Gate 3: Compute fleet successfully started.")

    # Gate 4: HTTP Health Verification Loop
    if dry_run:
        log_warn("[DRY-RUN] Gate 4: Would poll web.hasb.dev and monitoring.hasb.dev until HTTP 200.")
        return

    log_info("Gate 4: Polling web endpoints for service readiness (up to 45s)...")
    time.sleep(5)  # Initial grace period for container startup
    healthy = False
    for attempt in range(1, 11):
        eps = probe_endpoints()
        if all(ep["ok"] for ep in eps):
            healthy = True
            log_success(f"Gate 4: All endpoints healthy on attempt {attempt}/10!")
            break
        statuses = [f"{ep['name']}: {ep.get('code') or 'down'}" for ep in eps]
        log_warn(f"Attempt {attempt}/10: Services initializing ({', '.join(statuses)}). Retrying in 4s...")
        time.sleep(4)

    print("\n" + "=" * 70)
    if healthy:
        print(f"{COLOR_GREEN}{COLOR_BOLD}PLATFORM SUCCESSFULLY UNPARKED & VERIFIED{COLOR_RESET}")
        print("  - Web App:    https://web.hasb.dev [HTTP 200]")
        print("  - Monitoring: https://monitoring.hasb.dev [HTTP 200]")
    else:
        print(f"{COLOR_YELLOW}{COLOR_BOLD}PLATFORM UNPARKED WITH WARNINGS{COLOR_RESET}")
        print("Instances are running, but one or more endpoints did not return HTTP 200.")
        print("Run 'make status' or check Docker containers via SSM if startup is delayed.")
    print("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DevOps Bootcamp Platform Lifecycle Automation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: status
    parser_status = subparsers.add_parser("status", help="Read-only status of compute, network stack, and endpoints")
    parser_status.add_argument("--json", action="store_true", help="Output status as structured JSON")
    parser_status.add_argument("--region", default=DEFAULT_REGION, help=f"AWS Region (default: {DEFAULT_REGION})")

    # Subcommand: health
    subparsers.add_parser("health", help="Probe web and monitoring endpoints")

    # Subcommand: park
    parser_park = subparsers.add_parser("park", help="Gracefully stop compute and clean up 5-resource network stack")
    parser_park.add_argument("--dry-run", action="store_true", help="Simulate park actions without modifying AWS")
    parser_park.add_argument("--force-self-park", action="store_true", help="Bypass self-termination safety guard")
    parser_park.add_argument("--region", default=DEFAULT_REGION, help=f"AWS Region (default: {DEFAULT_REGION})")

    # Subcommand: unpark
    parser_unpark = subparsers.add_parser("unpark", help="Restore network stack via guarded plan/apply and start compute")
    parser_unpark.add_argument("--dry-run", action="store_true", help="Simulate unpark actions without modifying AWS")
    parser_unpark.add_argument("--allow-unrelated-changes", action="store_true", help="Bypass plan allowlist guard for non-network resources")
    parser_unpark.add_argument("--allow-replacements", action="store_true", help="Force apply destructive replacements on allowed resources (requires manual review)")
    parser_unpark.add_argument("--region", default=DEFAULT_REGION, help=f"AWS Region (default: {DEFAULT_REGION})")

    args = parser.parse_args()

    try:
        if args.command == "status":
            cmd_status(region=args.region, as_json=args.json)
        elif args.command == "health":
            cmd_health()
        elif args.command == "park":
            cmd_park(region=args.region, dry_run=args.dry_run, force_self_park=args.force_self_park)
        elif args.command == "unpark":
            cmd_unpark(
                region=args.region,
                dry_run=args.dry_run,
                allow_unrelated_changes=args.allow_unrelated_changes,
                allow_replacements=args.allow_replacements,
            )
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)
    except Exception as e:
        log_error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
