"""Unit tests for the platform lifecycle engine (scripts/platform.py).

Run:  python3 -m unittest discover -s tests -v
      (or `make test-platform` from the repository root)

The module is loaded via importlib from its file path because its name,
`platform`, collides with the Python standard library module.

All external boundaries are mocked: no AWS CLI calls, no Terraform runs,
no HTTP requests, no IMDS access. These tests exercise the guard logic
and state classification only.
"""

import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORM_PATH = os.path.join(REPO_ROOT, "scripts", "platform.py")


def load_platform_module():
    """Load scripts/platform.py under a non-colliding module name."""
    spec = importlib.util.spec_from_file_location("platform_lifecycle_engine", PLATFORM_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


platform_mod = load_platform_module()


def ec2_aws_response(payload):
    """Build a canned AWS-CLI JSON response for run_aws_cli mocking."""
    return (0, json.dumps(payload), "")


# ---------------------------------------------------------------------------
# Fixtures: network discovery payloads keyed by the CLI call sequence used by
# discover_network_resources: addresses, nat-gateways, route-tables (lookup),
# subnets, route-tables (association), vpc-endpoints.
# ---------------------------------------------------------------------------

ACTIVE_NET = [
    ec2_aws_response({"Addresses": [{"AllocationId": "eipalloc-1", "PublicIp": "1.2.3.4"}]}),
    ec2_aws_response({"NatGateways": [{"NatGatewayId": "nat-1", "State": "available"}]}),
    ec2_aws_response({"RouteTables": [{"RouteTableId": "rtb-1"}]}),
    ec2_aws_response({"Subnets": [{"SubnetId": "subnet-1"}]}),
    ec2_aws_response({"RouteTables": [{"RouteTableId": "rtb-1", "Associations": [{"SubnetId": "subnet-1", "RouteTableAssociationId": "rtbassoc-1"}]}]}),
    ec2_aws_response({"VpcEndpoints": [{"VpcEndpointId": "vpce-1", "RouteTableIds": ["rtb-1"]}]}),
]

PARKED_NET = [
    ec2_aws_response({"Addresses": []}),
    ec2_aws_response({"NatGateways": []}),
    ec2_aws_response({"RouteTables": []}),
    ec2_aws_response({"Subnets": [{"SubnetId": "subnet-1"}]}),
    ec2_aws_response({"RouteTables": []}),
    ec2_aws_response({"VpcEndpoints": []}),
]

# NAT gone but everything else present: 4/5 active -> PARTIAL_DRIFT
PARTIAL_DRIFT_NET = [
    ec2_aws_response({"Addresses": [{"AllocationId": "eipalloc-1", "PublicIp": "1.2.3.4"}]}),
    ec2_aws_response({"NatGateways": []}),
    ec2_aws_response({"RouteTables": [{"RouteTableId": "rtb-1"}]}),
    ec2_aws_response({"Subnets": [{"SubnetId": "subnet-1"}]}),
    ec2_aws_response({"RouteTables": [{"RouteTableId": "rtb-1", "Associations": [{"SubnetId": "subnet-1", "RouteTableAssociationId": "rtbassoc-1"}]}]}),
    ec2_aws_response({"VpcEndpoints": [{"VpcEndpointId": "vpce-1", "RouteTableIds": ["rtb-1"]}]}),
]


class TestNetworkStateClassification(unittest.TestCase):
    """discover_network_resources classifies 5-resource stack state."""

    def _discover(self, responses):
        with mock.patch.object(platform_mod, "run_aws_cli", side_effect=responses):
            return platform_mod.discover_network_resources(region="ap-southeast-1")

    def test_all_active_evaluates_to_active(self):
        net = self._discover(ACTIVE_NET)
        self.assertEqual(net["overall_state"], "ACTIVE")
        self.assertEqual(net["active_count"], 5)

    def test_all_absent_evaluates_to_parked(self):
        net = self._discover(PARKED_NET)
        self.assertEqual(net["overall_state"], "PARKED")
        self.assertEqual(net["active_count"], 0)

    def test_missing_nat_evaluates_to_partial_drift(self):
        net = self._discover(PARTIAL_DRIFT_NET)
        self.assertEqual(net["overall_state"], "PARTIAL_DRIFT")
        self.assertEqual(net["active_count"], 4)
        self.assertFalse(net["nat"]["active"])

    def test_active_states_are_booleans_not_status_strings(self):
        net = self._discover(ACTIVE_NET)
        for key in ("eip", "nat", "route_table", "route_association", "s3_endpoint"):
            self.assertIsInstance(net[key]["active"], bool, key)


class TestUnparkAllowlist(unittest.TestCase):
    """The unpark plan guard only tolerates the five approved resources."""

    def test_allowlist_contains_exactly_the_five_network_resources(self):
        self.assertEqual(
            platform_mod.ALLOWED_UNPARK_RESOURCES,
            {
                "aws_eip.nat",
                "aws_nat_gateway.gw",
                "aws_route_table.private",
                "aws_route_table_association.private",
                "aws_vpc_endpoint.s3",
            },
        )


def plan_json(resource_changes):
    """Build a terraform show -json payload with the given resource_changes."""
    return (0, json.dumps({"resource_changes": resource_changes}), "")


def rc(address, actions):
    return {"address": address, "change": {"actions": actions}}


class TestUnparkPlanGuard(unittest.TestCase):
    """Gate 1 of unpark inspects the speculative plan before applying."""

    def _run_guard(self, resource_changes, allow_unrelated=False, allow_replacements=False):
        """Drive cmd_unpark's plan-guard section with canned discovery+plan data.

        Patches: network discovery (non-ACTIVE state), terraform plan/show/apply
        subprocess calls, the Gate-2 NAT availability poll, post-apply discovery,
        endpoint probes, and sleep so the guard verdict is observable via
        SystemExit or lack thereof.
        """
        with mock.patch.object(platform_mod, "discover_network_resources") as disc, \
             mock.patch.object(platform_mod, "discover_compute_fleet") as fleet, \
             mock.patch.object(platform_mod, "probe_endpoints") as probe, \
             mock.patch.object(platform_mod, "run_aws_cli") as aws_cli, \
             mock.patch.object(platform_mod.time, "sleep"), \
             mock.patch(platform_mod.subprocess.__name__ + ".run") as sub_run, \
             mock.patch("os.path.exists", return_value=False):
            # Network is PARTIAL_DRIFT so the plan/apply path is taken.
            disc.return_value = dict(PARTIAL_DRIFT_NET_STATE, active_count=4)
            fleet.return_value = []
            probe.return_value = []
            # Gate 2 NAT availability poll: gateway already available.
            aws_cli.return_value = ec2_aws_response(
                {"NatGateways": [{"NatGatewayId": "nat-1", "State": "available"}]}
            )
            # plan -> ok; show -json -> canned payload; apply -> ok
            sub_run.side_effect = [
                mock.Mock(returncode=0),
                mock.Mock(returncode=0, stdout=plan_json(resource_changes)[1]),
                mock.Mock(returncode=0),
            ]
            platform_mod.cmd_unpark(
                region="ap-southeast-1",
                dry_run=False,
                allow_unrelated_changes=allow_unrelated,
                allow_replacements=allow_replacements,
            )
            return terraform_invocations(sub_run)

    def test_foreign_resource_blocks_unpark(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run_guard([rc("aws_instance.web", ["create"])])
        self.assertEqual(ctx.exception.code, 1)

    def test_create_delete_on_allowed_resource_blocks_unpark(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run_guard([rc("aws_eip.nat", ["create", "delete"])])
        self.assertEqual(ctx.exception.code, 1)

    def test_read_on_foreign_resource_is_not_a_change(self):
        # no-op actions are skipped entirely; guard passes without exit
        self._run_guard([rc("aws_instance.web", ["no-op"]), rc("aws_eip.nat", ["create"])])

    def test_allowed_creates_pass_the_guard(self):
        self._run_guard([
            rc("aws_eip.nat", ["create"]),
            rc("aws_nat_gateway.gw", ["create"]),
            rc("aws_route_table.private", ["create"]),
            rc("aws_route_table_association.private", ["create"]),
            rc("aws_vpc_endpoint.s3", ["create"]),
        ])

    def test_plan_command_carries_exact_hardcoded_arguments(self):
        cmds = self._run_guard([rc("aws_eip.nat", ["create"])])
        plan_cmds = [c for c in cmds if " plan " in f" {c} " or c.split(" ")[2] == "plan"]
        self.assertEqual(len(plan_cmds), 1)
        plan = plan_cmds[0]
        self.assertTrue(plan.startswith("terraform -chdir=terraform plan"))
        self.assertIn("-out=unpark.tfplan", plan)
        self.assertIn("-var=instance_type=t3.small", plan)
        self.assertIn("-var=key_name=devops-bootcamp-macbook-ed25519", plan)


# Partial-drift discovery state for cmd_unpark/plan-guard tests (dict form
# returned by discover_network_resources, not the raw CLI payloads above).
PARTIAL_DRIFT_NET_STATE = {
    "eip": {"status": "ALLOCATED", "id": "eipalloc-1", "ip": "1.2.3.4", "active": True},
    "nat": {"status": "ABSENT (Parked)", "id": None, "active": False},
    "route_table": {"status": "PRESENT", "id": "rtb-1", "active": True},
    "route_association": {"status": "ASSOCIATED", "id": "rtbassoc-1", "active": True},
    "s3_endpoint": {"status": "ATTACHED", "id": "vpce-1", "active": True},
    "overall_state": "PARTIAL_DRIFT",
    "active_count": 4,
}

# Fully-active discovery state (dict form) for park-path tests.
ACTIVE_NET_STATE = {
    "eip": {"status": "ALLOCATED", "id": "eipalloc-1", "ip": "1.2.3.4", "active": True},
    "nat": {"status": "AVAILABLE", "id": "nat-1", "active": True},
    "route_table": {"status": "PRESENT", "id": "rtb-1", "active": True},
    "route_association": {"status": "ASSOCIATED", "id": "rtbassoc-1", "active": True},
    "s3_endpoint": {"status": "ATTACHED", "id": "vpce-1", "active": True},
    "overall_state": "ACTIVE",
    "active_count": 5,
}

# Fleet fixture used by park tests: two running instances.
RUNNING_FLEET = [
    {"id": "i-web", "name": "web-server", "role": "web", "auto_park": True, "state": "running", "private_ip": "10.0.0.5", "public_ip": "1.2.3.4"},
    {"id": "i-mon", "name": "monitoring-server", "role": "monitoring", "auto_park": True, "state": "running", "private_ip": "10.0.0.136", "public_ip": "None"},
]


def terraform_invocations(sub_run_mock):
    """Extract the terraform commands a mocked subprocess.run received."""
    return [
        " ".join(call.args[0])
        for call in sub_run_mock.call_args_list
        if call.args and call.args[0] and call.args[0][0] == "terraform"
    ]


class TestParkTargetSelection(unittest.TestCase):
    """Gate 2 of park picks Terraform destroy targets from NAT presence."""

    def _run_park(self, net_state):
        """Run a real (non-dry-run) park with every boundary mocked; return
        the terraform commands subprocess.run received."""
        with mock.patch.object(platform_mod, "discover_compute_fleet") as fleet, \
             mock.patch.object(platform_mod, "discover_network_resources") as disc, \
             mock.patch.object(platform_mod, "check_self_termination_guard"), \
             mock.patch.object(platform_mod, "run_aws_cli") as aws_cli, \
             mock.patch.object(platform_mod.time, "sleep"), \
             mock.patch(platform_mod.subprocess.__name__ + ".run") as sub_run:
            fleet.return_value = [dict(i) for i in RUNNING_FLEET]
            # Gate 1 stop + wait, then post-park verification discovery.
            aws_cli.return_value = ec2_aws_response({})
            disc.side_effect = [dict(net_state), dict(net_state), dict(net_state)]
            sub_run.return_value = mock.Mock(returncode=0)
            platform_mod.cmd_park(region="ap-southeast-1")
            return terraform_invocations(sub_run)

    def test_nat_present_targets_nat_gateway_and_eip_only(self):
        cmds = self._run_park(ACTIVE_NET_STATE)
        self.assertEqual(len(cmds), 1)
        self.assertIn("-target=aws_nat_gateway.gw", cmds[0])
        self.assertIn("-target=aws_eip.nat", cmds[0])
        self.assertNotIn("-target=aws_route_table.private", cmds[0])
        self.assertNotIn("-target=aws_route_table_association.private", cmds[0])
        self.assertNotIn("-target=aws_vpc_endpoint.s3", cmds[0])

    def test_nat_absent_targets_remaining_four_resources(self):
        cmds = self._run_park(PARTIAL_DRIFT_NET_STATE)
        self.assertEqual(len(cmds), 1)
        self.assertNotIn("-target=aws_nat_gateway.gw", cmds[0])
        for target in (
            "-target=aws_eip.nat",
            "-target=aws_route_table_association.private",
            "-target=aws_route_table.private",
            "-target=aws_vpc_endpoint.s3",
        ):
            self.assertIn(target, cmds[0])

    def test_both_paths_preserve_hardcoded_var_overrides(self):
        for net_state in (ACTIVE_NET_STATE, PARTIAL_DRIFT_NET_STATE):
            with self.subTest(state=net_state["overall_state"]):
                cmds = self._run_park(net_state)
                self.assertEqual(len(cmds), 1)
                self.assertIn("-var=instance_type=t3.small", cmds[0])
                self.assertIn("-var=key_name=devops-bootcamp-macbook-ed25519", cmds[0])
                self.assertIn("-auto-approve", cmds[0])
                self.assertTrue(cmds[0].startswith("terraform -chdir=terraform destroy"))


class TestSelfTerminationGuard(unittest.TestCase):
    """Park aborts when executed on a targeted EC2 instance (IMDS match)."""

    def _imds_responses(self, instance_id):
        # urlopen is called twice: token request, then instance-id request.
        token_resp = mock.Mock()
        token_resp.read.return_value = b"imds-token"
        token_resp.__enter__ = mock.Mock(return_value=token_resp)
        token_resp.__exit__ = mock.Mock(return_value=False)
        id_resp = mock.Mock()
        id_resp.read.return_value = instance_id.encode()
        id_resp.__enter__ = mock.Mock(return_value=id_resp)
        id_resp.__exit__ = mock.Mock(return_value=False)
        return [token_resp, id_resp]

    def test_imds_match_aborts_park(self):
        responses = self._imds_responses("i-abc123")
        with mock.patch.object(platform_mod.urllib.request, "urlopen", side_effect=responses), \
             mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                platform_mod.check_self_termination_guard({"i-abc123", "i-other"})
            self.assertEqual(ctx.exception.code, 1)

    def test_non_ec2_host_passes_guard(self):
        # urlopen raising (non-EC2 host) is caught and the guard passes.
        with mock.patch.object(
            platform_mod.urllib.request, "urlopen",
            side_effect=OSError("no route to 169.254.169.254"),
        ):
            platform_mod.check_self_termination_guard({"i-abc123"})

    def test_force_bypasses_guard(self):
        platform_mod.check_self_termination_guard({"i-abc123"}, force=True)


class TestEndpointHealthProbing(unittest.TestCase):
    """probe_endpoints maps HTTP outcomes to ok/not-ok records."""

    def _probe_with(self, urlopen_side_effect):
        # Reduce the endpoint list to a single probe so each test exercises
        # exactly one HTTP outcome.
        with mock.patch.object(platform_mod, "WEB_ENDPOINTS", [("Test Endpoint", "https://test.example")]), \
             mock.patch.object(platform_mod.urllib.request, "urlopen", side_effect=urlopen_side_effect):
            return platform_mod.probe_endpoints()

    def test_http_500_reports_unhealthy(self):
        err = platform_mod.urllib.error.HTTPError(
            "https://web.hasb.dev", 500, "Internal Server Error", hdrs=None, fp=None
        )
        results = self._probe_with([err])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["code"], 500)

    def test_timeout_reports_unreachable(self):
        results = self._probe_with([OSError("timed out")])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["code"], 0)

    def test_http_200_reports_healthy(self):
        resp = mock.Mock()
        resp.status = 200
        resp.__enter__ = mock.Mock(return_value=resp)
        resp.__exit__ = mock.Mock(return_value=False)
        results = self._probe_with([resp])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["code"], 200)

    def test_health_command_exits_nonzero_when_any_endpoint_down(self):
        err = platform_mod.urllib.error.HTTPError(
            "https://web.hasb.dev", 503, "Service Unavailable", hdrs=None, fp=None
        )
        with mock.patch.object(platform_mod, "probe_endpoints", return_value=[
            {"name": "Web Application", "url": "https://web.hasb.dev", "code": 200, "latency_ms": 10, "ok": True},
            {"name": "Grafana Monitoring", "url": "https://monitoring.hasb.dev", "code": 503, "latency_ms": 10, "error": "HTTP 503", "ok": False},
        ]), mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                platform_mod.cmd_health()
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
