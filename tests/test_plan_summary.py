import importlib.util
from pathlib import Path
import unittest
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("plan_summary", ROOT / "scripts/render-test-plans.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class PlanSummaryTests(unittest.TestCase):
    def test_failure_report_prints_only_location_and_allowlisted_category(self):
        secret = "SENSITIVE-RAW-DIAGNOSTIC"
        with tempfile.NamedTemporaryFile(mode="w") as target:
            for summary in ("Test assertion failed", secret):
                target.write(json.dumps({"type":"diagnostic","diagnostic":{
                    "summary":summary,"detail":secret,"range":{
                        "filename":"tests/archive.tftest.hcl","start":{"line":12}},
                    "snippet":{"values":[secret]}}}) + "\n")
            target.flush()
            result = subprocess.run(["python3",str(ROOT / "scripts/report-test-failure.py"),target.name],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertNotIn(secret,result.stdout + result.stderr)
        self.assertIn("tests/archive.tftest.hcl:12: Test assertion failed",result.stderr)
    def test_values_ids_addresses_and_diagnostics_are_not_disclosed(self):
        secret = "private-subscription-and-password"
        messages = [
            {"type": "diagnostic", "diagnostic": {"detail": secret}},
            {"type": "test_plan", "@testrun": "configuration", "test_plan": {
                "resource_changes": [{"type": "azurerm_storage_account", "address": secret,
                                      "change": {"actions": ["create"], "after": {"id": secret}}}],
                "output_changes": {"deployment_context": {"after": secret, "after_sensitive": True}},
            }},
            {"type": "test_summary", "test_summary": {"status": "pass", "passed": 1}},
        ]
        result = renderer.render(messages, "environments/development")
        self.assertNotIn(secret, result)
        self.assertIn("azurerm_storage_account | create | 1", result)
        self.assertIn("deployment_context", result)

    def test_failed_or_missing_test_summary_cannot_report_success(self):
        for messages in ([], [{"type": "test_summary", "test_summary": {"status": "fail", "passed": 1}}]):
            with self.subTest(messages=messages), self.assertRaises(ValueError):
                renderer.render(messages, "environments/development")

    def test_skipped_tests_cannot_report_success(self):
        with self.assertRaises(ValueError):
            renderer.render([{"type": "test_summary", "test_summary": {"status": "pass", "passed": 1, "skipped": 1}}], "environments/development")
