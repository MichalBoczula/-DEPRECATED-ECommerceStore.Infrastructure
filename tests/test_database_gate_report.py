"""Reject incomplete or misattributed success evidence; retain redacted failures."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate_report', ROOT / 'scripts/report-database-gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def reports(mode):
    common = dict(backend=mode, backendSelected=False, passed=True)
    return [dict(common, drivers=dict(mongo='3.7.1', efSqlServer='10.0.1', dapper='2.1.66'),
                 checks=dict.fromkeys(gate.DOTNET_CHECKS, True)),
            dict(common, repository='MichalBoczula/ECommerceStorePayments',
                 commitSha=gate.PAYMENTS['COMMIT'], pymongo='4.18.1',
                 checks=dict.fromkeys(gate.PAYMENTS_CHECKS, True))]


class DatabaseGateReportTests(unittest.TestCase):
    def render(self, mode, items):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'{i}.json' for i in range(2)]
            for path, item in zip(paths, items):
                path.write_text(json.dumps(item))
            return gate.report(mode, paths)

    def test_complete_native_and_azure_reports(self):
        for mode in ('native-baseline', 'azure-candidate'):
            output, passed = self.render(mode, reports(mode))
            self.assertTrue(passed)
            self.assertEqual(output.count(' | PASS |'), 47)
            self.assertIn('No backend has been selected.', output)

    def test_missing_case_or_cleanup_cannot_claim_success(self):
        for index in range(2):
            for name in reports('azure-candidate')[index]['checks']:
                with self.subTest(suite=index, check=name):
                    items = reports('azure-candidate')
                    del items[index]['checks'][name]
                    with self.assertRaises(ValueError):
                        self.render('azure-candidate', items)

    def test_wrong_mode_source_driver_and_contradictory_success_rejected(self):
        alterations = [(0, 'backend', 'native-baseline'), (1, 'commitSha', '0' * 40),
                       (1, 'repository', 'another/repository'), (1, 'pymongo', 'other'),
                       (0, 'drivers', {'mongo': 'other'}), (0, 'backendSelected', True),
                       (0, 'passed', 1)]
        for index, key, value in alterations:
            with self.subTest(key=key):
                items = reports('azure-candidate')
                items[index][key] = value
                with self.assertRaises(ValueError):
                    self.render('azure-candidate', items)
        items = reports('azure-candidate')
        items[0]['checks']['multi_collection_commit'] = False
        with self.assertRaises(ValueError):
            self.render('azure-candidate', items)

    def test_incomplete_failure_shows_all_missing_checks_as_fail(self):
        items = reports('azure-candidate')
        items[0].update(passed=False, checks={'endpoint_identity_and_tls': False})
        items[1].update(passed=False, checks={'source_driver_and_endpoint': False, 'suite_completed': False})
        output, passed = self.render('azure-candidate', items)
        self.assertFalse(passed)
        self.assertEqual(output.count(' | FAIL |'), 47)

    def test_unknown_check_labels_are_never_published(self):
        items = reports('azure-candidate')
        items[0]['checks']['private_connection_detail'] = True
        with self.assertRaises(ValueError):
            self.render('azure-candidate', items)
