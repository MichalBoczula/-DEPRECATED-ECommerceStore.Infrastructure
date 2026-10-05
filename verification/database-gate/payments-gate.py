"""Call the pinned Payments integration tests against ONLY the supplied backend.

No pytest fixture discovery: repository conftest would start a local testcontainer.
Reports contain check names/booleans only; raw errors and credentials stay private.
"""
import asyncio
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

COMMIT = '9663df14cb10886a32fa7850d1ca51537a3da009'
CASES = {
    'test_mongo_payment_repository': [
        'test_create_reads_back_domain_and_bson_values',
        'test_unique_order_index_rejects_second_payment',
        'test_competing_updates_leave_one_winner',
        'test_competing_creates_for_order_leave_one_payment',
        'test_first_update_of_versionless_document_migrates_it_atomically',
        'test_failed_archive_rolls_back_current_update',
    ],
    'test_mongo_webhooks': [
        'test_atomic_confirmation_receipt_history_and_durable_fulfillment_marker',
        'test_receipt_only_interruption_is_recovered_by_new_process_without_provider_credentials',
        'test_failure_after_payment_and_archive_rolls_back_and_redelivery_recovers',
        'test_concurrent_deliveries_confirm_logically_once',
    ],
    'test_mongo_fulfillment': [
        'test_atomic_claim_concurrent_workers_and_fenced_expired_lease',
        'test_retry_due_progress_and_manual_resume_survive_new_repository',
        'test_crash_after_invoice_commit_recovers_with_one_logical_invoice',
        'test_many_workers_and_webhook_replay_produce_one_completed_work',
    ],
}


def require(value):
    if not value:
        raise ValueError('gate precondition failed')


def verify_source(source):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.DEVNULL, text=True).strip()
    require(git('rev-parse', 'HEAD') == COMMIT)
    require(not git('status', '--porcelain', '--untracked-files=no'))
    require(sys.version_info[:2] == (3, 14))
    require(importlib.metadata.version('pymongo') == '4.18.1')


def verify_endpoint(mode, uri):
    parts = urlsplit(uri)
    require(parts.scheme in ('mongodb', 'mongodb+srv') and parts.hostname)
    query = {k.lower(): v[0].lower() for k, v in parse_qs(parts.query).items()}
    if mode == 'azure-candidate':
        require(parts.hostname == os.environ['D6_MONGO_HOST'])
        require(parts.scheme == 'mongodb+srv' or query.get('tls', query.get('ssl')) == 'true')
        for key in ('tlsallowinvalidcertificates', 'tlsallowinvalidhostnames', 'tlsinsecure'):
            require(query.get(key, 'false') == 'false')
        require(query.get('tls', 'true') != 'false' and query.get('ssl', 'true') != 'false')
    else:
        require(mode == 'native-baseline' and parts.hostname == '127.0.0.1' and parts.port == 27017)


async def run(mode, source, checks):
    verify_source(source)
    uri = os.environ['D6_MONGO_CONNECTION_STRING']
    verify_endpoint(mode, uri)
    sys.path[:0] = [str(source), str(source / 'src')]
    import pytest
    from ecommerce_store_payments.infrastructure.config.settings import Settings
    from ecommerce_store_payments.infrastructure.persistence.mongodb.mongo_database import MongoDatabase
    checks['source_driver_and_endpoint'] = True
    for module_name, functions in CASES.items():
        module = importlib.import_module('tests.integration.infrastructure.' + module_name)
        for function in functions:
            variants = [True, False] if function == 'test_concurrent_deliveries_confirm_logically_once' else [None]
            for variant in variants:
                label = function + (f'_{variant}' if variant is not None else '')
                name = 'd6_gate_' + uuid4().hex
                db = MongoDatabase(Settings(_env_file=None, environment='test', mongodb_connection_string=uri,
                    mongodb_database_name=name, mongodb_server_selection_timeout_ms=30000))
                checks[label] = False
                try:
                    await db.probe()
                    await db.ensure_indexes()
                    arguments = [db]
                    if function == 'test_receipt_only_interruption_is_recovered_by_new_process_without_provider_credentials':
                        arguments.append(uri)
                    if variant is not None:
                        arguments.append(variant)
                    with pytest.MonkeyPatch.context() as monkeypatch:
                        if function == 'test_failure_after_payment_and_archive_rolls_back_and_redelivery_recovers':
                            arguments.append(monkeypatch)
                        await asyncio.wait_for(getattr(module, function)(*arguments), timeout=180)
                    checks[label] = True
                except (KeyboardInterrupt, SystemExit):
                    raise
                except BaseException:
                    pass # pytest assertion/failure may derive from BaseException; never print backend errors.
                finally:
                    try:
                        await asyncio.wait_for(db.client.drop_database(name), timeout=60)
                        checks[label + '_cleanup'] = True
                    except Exception:
                        checks[label + '_cleanup'] = False
                    finally:
                        await db.close()


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ('azure-candidate', 'native-baseline'):
        raise SystemExit('Usage: payments-gate.py azure-candidate|native-baseline payments-checkout report.json')
    mode, source, report = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    checks = {'source_driver_and_endpoint': False}
    try:
        # Test helper Settings must not inherit operator Stripe credentials or .env.
        for key in list(os.environ):
            if key.startswith('PAYMENTS_'):
                del os.environ[key]
        with tempfile.TemporaryDirectory(prefix='d6-gate-') as directory:
            os.chdir(directory)
            asyncio.run(run(mode, source, checks))
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        checks['suite_completed'] = False
    passed = len(checks) >= 31 and all(checks.values())
    report.write_text(json.dumps(dict(backend=mode, passed=passed, backendSelected=False,
        repository='MichalBoczula/ECommerceStorePayments', commitSha=COMMIT,
        pymongo='4.18.1', checks=checks), indent=2) + '\n')
    print(f"Payments database gate: {'PASS' if passed else 'FAIL'}; redacted report written.")
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
