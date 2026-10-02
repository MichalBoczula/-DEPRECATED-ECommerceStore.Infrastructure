import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

FAKE_TOOL = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as out:
    out.write(json.dumps([tool, *args]) + "\n")
operation = args[0] if args else ""
if os.environ.get("FAIL_OPERATION") == tool + ":" + operation:
    print("SENSITIVE-RAW-DIAGNOSTIC", file=sys.stderr)
    sys.exit(1)
if tool == "terraform":
    if operation == "plan":
        target = next(arg[5:] for arg in args if arg.startswith("-out="))
        pathlib.Path(target).write_text("saved complete destroy plan")
    elif operation == "show":
        print(os.environ["PLAN_JSON"])
    elif operation == "state" and args[1:] == ["pull"]:
        print(json.dumps({"lineage": "verified-test-lineage", "resources": []}))
    elif operation == "state" and os.environ.get("RESIDUAL_STATE"):
        print("azurerm_resource_group.remaining")
elif tool == "az" and args[:2] == ["group", "exists"]:
    print(os.environ.get("GROUP_EXISTS", "true"))
elif tool == "az" and args[:2] == ["resource", "list"]:
    print(os.environ.get("CHILD_COUNT", "0"))
'''


class DestroyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        for name in ("terraform", "az"):
            target = self.directory / name
            target.write_text(FAKE_TOOL)
            target.chmod(0o700)
        self.env = dict(os.environ)
        self.env.update(
            PATH=str(self.directory) + os.pathsep + self.env["PATH"],
            GITHUB_REPOSITORY="MichalBoczula/ECommerceStore.Infrastructure",
            GITHUB_REF="refs/heads/main",
            ARM_CLIENT_ID="11111111-1111-1111-1111-111111111111",
            ARM_TENANT_ID="22222222-2222-2222-2222-222222222222",
            ARM_SUBSCRIPTION_ID="33333333-3333-3333-3333-333333333333",
            TFSTATE_RESOURCE_GROUP="rg-independent-state",
            TFSTATE_STORAGE_ACCOUNT="ecomtfstatetest",
            TFSTATE_CONTAINER="development-state",
            TF_WORKSPACE="default",
            CALLS=str(self.directory / "calls.jsonl"),
            GITHUB_STEP_SUMMARY=str(self.directory / "summary.md"),
        )
        self.set_plan(["delete"])

    def tearDown(self):
        self.temp.cleanup()

    def set_plan(self, actions, resource_id=None):
        resource_id = resource_id or "/subscriptions/test/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/containerApps/bff"
        self.env["PLAN_JSON"] = json.dumps({"resource_changes": [{
            "mode": "managed", "change": {
                "actions": actions, "before": {"id": resource_id}
            }
        }]})

    def run_destroy(self):
        return subprocess.run(
            ["bash", str(ROOT / "scripts/destroy-development.sh")],
            env=self.env, capture_output=True, text=True,
        )

    def calls(self):
        target = self.directory / "calls.jsonl"
        return [json.loads(line) for line in target.read_text().splitlines()] if target.exists() else []

    def test_exact_plan_and_fixed_remote_backend(self):
        result = self.run_destroy()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        init = next(call for call in calls if call[:2] == ["terraform", "init"])
        self.assertIn("-backend-config=key=ecommerce/development.tfstate", init)
        self.assertIn("-lockfile=readonly", init)
        plan = next(call for call in calls if call[:2] == ["terraform", "plan"])
        apply = next(call for call in calls if call[:2] == ["terraform", "apply"])
        self.assertIn("-destroy", plan)
        self.assertIn("-lock=true", plan)
        self.assertIn("-lock=true", apply)
        saved_path = next(arg[5:] for arg in plan if arg.startswith("-out="))
        self.assertEqual(apply[-1], saved_path)
        self.assertFalse(Path(saved_path).parent.exists(), "Private plan directory must be removed")
        self.assertFalse(any(arg.startswith("-target") for call in calls for arg in call))
        self.assertIn("state: empty", (self.directory / "summary.md").read_text())

    def test_missing_bootstrap_configuration_stops_before_tools(self):
        del self.env["ARM_CLIENT_ID"]
        self.assertNotEqual(self.run_destroy().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_wrong_repo_branch_workspace_and_shared_group_are_rejected(self):
        for key, value in (
            ("GITHUB_REPOSITORY", "MichalBoczula/ECommerceStore.Infrastructure.Production"),
            ("GITHUB_REF", "refs/heads/feature"),
            ("TF_WORKSPACE", "production"),
            ("TFSTATE_RESOURCE_GROUP", "RG-ECOMMERCE-DEV"),
            ("TFSTATE_CONTAINER", "portfolio-state"),
        ):
            with self.subTest(key=key):
                original = self.env[key]
                self.env[key] = value
                self.assertNotEqual(self.run_destroy().returncode, 0)
                self.assertEqual(self.calls(), [])
                self.env[key] = original

    def test_create_update_and_replace_cannot_be_applied(self):
        for actions in (["create"], ["update"], ["delete", "create"]):
            with self.subTest(actions=actions):
                self.set_plan(actions)
                self.assertNotEqual(self.run_destroy().returncode, 0)
                self.assertFalse(any(call[:2] == ["terraform", "apply"] for call in self.calls()))

    def test_bootstrap_group_and_child_resources_are_protected(self):
        for suffix in ("", "/providers/Microsoft.Storage/storageAccounts/state"):
            with self.subTest(suffix=suffix):
                self.set_plan(["delete"], "/subscriptions/test/resourceGroups/RG-INDEPENDENT-STATE" + suffix)
                self.assertNotEqual(self.run_destroy().returncode, 0)
                self.assertFalse(any(call[:2] == ["terraform", "apply"] for call in self.calls()))

    def test_noop_and_empty_state_reruns_are_allowed(self):
        for plan in ({"resource_changes": []}, {"resource_changes": [{
            "mode": "managed", "change": {"actions": ["no-op"], "before": None}
        }]}):
            with self.subTest(plan=plan):
                self.env["PLAN_JSON"] = json.dumps(plan)
                self.assertEqual(self.run_destroy().returncode, 0)

    def test_tool_failures_propagate_without_printing_sensitive_logs(self):
        for operation in ("terraform:init", "terraform:validate", "terraform:plan",
                          "terraform:show", "terraform:apply", "terraform:state",
                          "az:group", "az:resource", "az:storage"):
            with self.subTest(operation=operation):
                self.env["FAIL_OPERATION"] = operation
                result = self.run_destroy()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("SENSITIVE-RAW-DIAGNOSTIC", result.stdout + result.stderr)

    def test_remaining_state_children_or_missing_group_fails_verification(self):
        for key, value in (("RESIDUAL_STATE", "1"), ("GROUP_EXISTS", "false"), ("CHILD_COUNT", "1")):
            with self.subTest(key=key):
                self.env[key] = value
                result = self.run_destroy()
                self.assertNotEqual(result.returncode, 0)
                self.env.pop(key)

    def test_retained_development_group_cannot_be_deleted(self):
        self.set_plan(["delete"], "/subscriptions/test/resourceGroups/rg-ecommerce-dev")
        result = self.run_destroy()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[:2] == ["terraform", "apply"] for call in self.calls()))

    def run_verify(self):
        return subprocess.run(["bash", str(ROOT / "scripts/verify-development-backend.sh")],
                              env=self.env, capture_output=True, text=True)

    def test_backend_verification_persists_empty_state_without_resource_changes(self):
        self.env["PLAN_JSON"] = json.dumps({"resource_changes": []})
        result = self.run_verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["terraform", "state", "pull"], self.calls())
        self.assertFalse(any("-destroy" in call for call in self.calls()))

    def test_backend_verification_rejects_resource_changes_before_apply(self):
        for actions in (["create"], ["delete"], ["update"]):
            with self.subTest(actions=actions):
                self.set_plan(actions)
                result = self.run_verify()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call[:2] == ["terraform", "apply"] for call in self.calls()))

    def test_backend_verification_failure_is_reported_without_sensitive_log(self):
        self.env["PLAN_JSON"] = json.dumps({"resource_changes": []})
        self.env["FAIL_OPERATION"] = "terraform:apply"
        result = self.run_verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("SENSITIVE-RAW-DIAGNOSTIC", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
