"""Publish known check names and booleans, never endpoint/credential details."""
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
PAYMENTS = runpy.run_path(str(ROOT / 'verification/database-gate/payments-gate.py'))
DOTNET_CHECKS = {
    'endpoint_identity_and_tls', 'mongo_suite_setup', 'sql_suite_setup',
    'users_readiness_unchanged', 'invoice_readiness_unchanged',
    'application_index_shapes', 'unique_indexes_and_standard_uuid',
    'multi_collection_commit', 'multi_collection_history_failure_rollback',
    'optimistic_concurrency_and_history', 'dotnet_mongo_cleanup',
    'sql_ef_commit_and_dapper_readback', 'sql_transaction_rollback',
    'sql_unique_constraint', 'sql_ef_optimistic_concurrency', 'sql_cleanup',
}
PAYMENTS_CASES = {
    function + (f'_{variant}' if variant is not None else '')
    for functions in PAYMENTS['CASES'].values()
    for function in functions
    for variant in ([True, False] if function == 'test_concurrent_deliveries_confirm_logically_once' else [None])
}
PAYMENTS_CHECKS = {'source_driver_and_endpoint'} | PAYMENTS_CASES | {
    name + '_cleanup' for name in PAYMENTS_CASES
}


def validate_suite(item, mode, index):
    fields = {'backend', 'passed', 'backendSelected', 'checks'} | (
        {'drivers'} if index == 0 else {'repository', 'commitSha', 'pymongo'})
    if set(item) != fields:
        raise ValueError()
    if item['backend'] != mode or item['backendSelected'] is not False or type(item['passed']) is not bool:
        raise ValueError()
    expected = DOTNET_CHECKS if index == 0 else PAYMENTS_CHECKS
    if index == 0:
        if item['drivers'] != {'mongo': '3.7.1', 'efSqlServer': '10.0.1', 'dapper': '2.1.66'}:
            raise ValueError()
    elif (item['repository'] != 'MichalBoczula/ECommerceStorePayments' or
          item['commitSha'] != PAYMENTS['COMMIT'] or item['pymongo'] != '4.18.1'):
        raise ValueError()
    checks = item['checks']
    allowed = expected | ({'suite_completed'} if index == 1 else set())
    if (not isinstance(checks, dict) or not checks or not set(checks) <= allowed or
            any(type(value) is not bool for value in checks.values())):
        raise ValueError()
    # A shortened success report must never be treated as database acceptance.
    if item['passed'] and (set(checks) != expected or not all(checks.values())):
        raise ValueError()
    return expected, checks


def report(mode, files):
    if mode not in ('native-baseline', 'azure-candidate') or len(files) != 2:
        raise ValueError()
    lines = [f'### Database gate: {mode}', '',
        'Native baseline checks the harness. Azure candidate results require offer readback and lifecycle evidence before selection.', '',
        '| Suite | Check | Result |', '| --- | --- | --- |']
    passed = True
    for index, filename in enumerate(files):
        item = json.loads(Path(filename).read_text())
        expected, checks = validate_suite(item, mode, index)
        for key in sorted(expected):
            value = checks.get(key, False)
            lines.append(f"| {'.NET' if index == 0 else 'Payments'} | {key} | {'PASS' if value else 'FAIL'} |")
        passed = passed and item['passed'] and all(checks.values())
    lines.extend(['', 'No backend has been selected.', ''])
    return '\n'.join(lines), passed


if __name__ == '__main__':
    try:
        output, passed = report(sys.argv[1], sys.argv[2:])
        print(output)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as file: file.write(output)
        raise SystemExit(0 if passed else 1)
    except (ValueError, KeyError, TypeError, OSError):
        raise SystemExit('Cannot produce a successful redacted database-gate report.')
