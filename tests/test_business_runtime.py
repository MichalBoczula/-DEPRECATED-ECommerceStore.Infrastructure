"""D/9 boundaries, complete Azure evidence and execution-bound private log collection."""
import base64
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_data_services as data
import test_database_gate_report as reports

ROOT = Path(__file__).resolve().parents[1]
policy = data.network.policy.business
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

verify = load('verify_d9_test', 'verify-business-runtime.py')
secrets = load('configure_d9_test', 'configure-development-database-secrets.py')
SUB = data.SUB
IMAGE = 'mb0101/ecommerce-store-database-gate@sha256:' + 'a' * 64
DOMAIN = 'mock-domain.northeurope.azurecontainerapps.io'
RELEASE = json.loads((ROOT / 'releases/development.json').read_text())
URLS = {key: 'https://ca-ecommerce-dev-' + key + ('' if key == 'bff' else '.internal') + '.' + DOMAIN for key in policy.APPS}

def identity(key):
    return data.EXPECTED['root'] + 'Microsoft.ManagedIdentity/userAssignedIdentities/id-ecommerce-dev-' + key

def change(base, key, after):
    return dict(address=base + '[' + json.dumps(key) + ']', type=policy.BASES[base], mode='managed', change=dict(actions=['create'], after=after))

def plan(apps=True):
    p = data.plan(True)
    p['variables'].update({name: {'value': value} for name, value in dict(enable_business_runtime=True, enable_business_apps=apps, database_gate_image=IMAGE).items()})
    next(x for x in p['resource_changes'] if x['type'] == 'azurerm_container_app_environment')['change']['after']['default_domain'] = DOMAIN
    changes = []
    for key in policy.APPS | {'gate'}:
        changes.append(change('azurerm_user_assigned_identity.business', key, dict(name='id-ecommerce-dev-' + key, location='northeurope', resource_group_name='rg-ecommerce-dev', principal_id='principal-' + key, client_id='client-' + key)))
    for key in set(policy.SECRETS) | {'gate_sql', 'gate_mongo'}:
        app = 'gate' if key.startswith('gate_') else key
        secret = policy.SECRETS['products' if key == 'gate_sql' else 'users' if key == 'gate_mongo' else key]
        changes.append(change('azurerm_role_assignment.business_secret', key, dict(scope=data.VAULT + '/secrets/' + secret, role_definition_name='Key Vault Secrets User', principal_id='principal-' + app, principal_type='ServicePrincipal', skip_service_principal_aad_check=True)))
    for key, container in [('products', 'photos'), ('invoice', 'invoices')]:
        changes.append(change('azurerm_role_assignment.business_blob', key, dict(scope=data.STORAGE + '/blobServices/default/containers/' + container, role_definition_name='Storage Blob Data Contributor', principal_id='principal-' + key, principal_type='ServicePrincipal', skip_service_principal_aad_check=True)))
    def reference(name, secret, app):
        return dict(name=name, identity=identity(app), key_vault_secret_id='https://' + data.EXPECTED['vault'] + '.vault.azure.net/secrets/' + secret)
    common = dict(resource_group_name='rg-ecommerce-dev', workload_profile_name='Consumption', container_app_environment_id=data.network.ENVIRONMENT)
    if apps:
        for key in policy.APPS:
            env = [dict(name=name, value=value) for name, value in dict(policy.plain_env(key, URLS), AZURE_CLIENT_ID='client-' + key).items()]
            if key != 'bff': env.append(dict(name=policy.SECRET_ENV[key], secret_name='connection'))
            container = dict(name=key, image=RELEASE['applications'][key]['image'], cpu=policy.ALLOCATIONS[key][0], memory=policy.ALLOCATIONS[key][1], env=env)
            for field, contract, interval, timeout, failures in [('startup_probe', 'startup', 5, 5, 120), ('liveness_probe', 'liveness', 10, 5, 3), ('readiness_probe', 'readiness', 10, 10, 3)]:
                container[field] = [dict(path=RELEASE['applications'][key]['runtime'][contract], port=8080, transport='HTTP', interval_seconds=interval, timeout=timeout, failure_count_threshold=failures)]
            after = dict(common, name='ca-ecommerce-dev-' + key, revision_mode='Single', max_inactive_revisions=2,
                identity=[dict(type='UserAssigned', identity_ids=[identity(key)])], secret=[reference('connection', policy.SECRETS[key], key)] if key != 'bff' else [],
                ingress=[dict(external_enabled=key == 'bff', allow_insecure_connections=False, target_port=8080, transport='http', traffic_weight=[dict(latest_revision=True, percentage=100)])],
                template=[dict(min_replicas=0, max_replicas=1, http_scale_rule=[dict(name='http', concurrent_requests=10)], container=[container])])
            changes.append(change('azurerm_container_app.business', key, after))
    for key in ('gate', 'invoice'):
        container = dict(name='gate' if key == 'gate' else 'invoice-probe', image=IMAGE if key == 'gate' else RELEASE['applications']['invoice']['image'], cpu=1.0, memory='2Gi', env=[dict(name='D9_RUN_ID', value='manual-unbound')])
        if key == 'gate':
            container['env'] += [dict(name='D6_SQL_CONNECTION_STRING', secret_name='sql'), dict(name='D6_MONGO_CONNECTION_STRING', secret_name='mongo'), dict(name='D6_SQL_HOST', value='sql-ecommerce-dev-d6-reviewd7.database.windows.net'), dict(name='D6_MONGO_HOST', value='mongo-ecommerce-dev-d6-reviewd7.mongocluster.cosmos.azure.com'), dict(name='D9_MODE', value='database'), dict(name='D9_APPS', value=json.dumps(URLS))]
        else:
            container['command'] = policy.invoice_command()
        after = dict(common, name='job-ecommerce-dev-' + ('database-gate' if key == 'gate' else 'invoice-probe'), location='northeurope', replica_retry_limit=0, replica_timeout_in_seconds=1800 if key == 'gate' else 300, manual_trigger_config=[dict(parallelism=1, replica_completion_count=1)], template=[dict(container=[container])])
        if key == 'gate': after.update(identity=[dict(type='UserAssigned', identity_ids=[identity('gate')])], secret=[reference('sql', policy.SECRETS['products'], 'gate'), reference('mongo', policy.SECRETS['users'], 'gate')])
        changes.append(change('azurerm_container_app_job.' + ('database_gate' if key == 'gate' else 'invoice_probe'), 0, after))
    for base in policy.BASES:
        expressions = {'container_app_environment_id': {'references': ['module.consumption']}} if base.startswith('azurerm_container_app') else {}
        if base.startswith('azurerm_role_assignment'):
            expressions = {'principal_id': {'references': ['azurerm_user_assigned_identity.business']}, 'scope': {'references': ['module.data_services']}}
        p['configuration']['root_module']['resources'].append(dict(address=base, expressions=expressions))
    p['resource_changes'] += changes
    return p, changes

def payload(mode='database', run_id='1' * 32):
    result = dict(schema=1, mode=mode, run_id=run_id, passed=True)
    if mode == 'database': result['suites'] = reports.reports('azure-candidate')
    else: result['checks'] = dict.fromkeys(verify.RUNTIME_CHECKS if mode == 'runtime' else {'chromium_pdf'}, True)
    return result

def marker(value):
    return 'D9_REPORT:' + base64.b64encode(json.dumps(value).encode()).decode()

def proof():
    expected = dict(subscription=SUB, release_id='fixture', gate_image=IMAGE, images={key: RELEASE['applications'][key]['image'] for key in policy.APPS}, candidate=dict(sql_server='sql-ecommerce-dev-d6-reviewd7'), aca_ipv4=['20.40.60.80'])
    value = dict(schema=1, mode='database', created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), binding=expected, executions={'database': dict(name='job-ecommerce-dev-database-gate-run123', status='Succeeded')}, reports={'database': payload()}, outside_checks={})
    return value, expected

class BusinessPlanTests(unittest.TestCase):
    def test_invoice_probe_command_preserves_terraform_file_line_endings(self):
        raw = b"$ErrorActionPreference = 'Stop'\r\nWrite-Host 'fixture'\r\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'verification/database-gate/invoice-probe.ps1'
            file.parent.mkdir(parents=True)
            file.write_bytes(raw)
            with patch.object(policy, 'ROOT', root):
                command = policy.invoice_command()
            self.assertEqual(command, ['pwsh', '-NoProfile', '-Command', raw.decode('utf-8')])
        for apps in (False, True):
            p, changes = plan(apps)
            probe = next(r for r in changes if r['address'] == 'azurerm_container_app_job.invoice_probe[0]')
            container = probe['change']['after']['template'][0]['container'][0]
            container['command'] = command.copy()
            with self.subTest(apps=apps), patch.object(policy, 'invoice_command', return_value=command):
                self.assertEqual(policy.validate(p, changes, SUB), URLS)
                container['command'][-1] += "Write-Host 'unexpected'\r\n"
                with self.assertRaises(ValueError):
                    policy.validate(p, changes, SUB)

    def test_argument_free_data_sources_can_omit_configuration_expressions(self):
        for apps in (False, True):
            p, changes = plan(apps)
            for name in ('database_candidate', 'data_services'):
                p['configuration']['root_module']['resources'].append({
                    'address': 'data.azurerm_client_config.' + name,
                    'mode': 'data', 'type': 'azurerm_client_config', 'name': name,
                    'provider_config_key': 'azurerm', 'schema_version': 0,
                })
            with self.subTest(apps=apps):
                self.assertEqual(policy.validate(p, changes, SUB), URLS)

    def test_missing_required_runtime_reference_expressions_still_rejected(self):
        for base in ('azurerm_role_assignment.business_secret',
                     'azurerm_role_assignment.business_blob',
                     'azurerm_container_app_job.database_gate'):
            p, changes = plan(False)
            config = next(r for r in p['configuration']['root_module']['resources'] if r['address'] == base)
            del config['expressions']
            with self.subTest(base=base), self.assertRaises((KeyError, ValueError)):
                policy.validate(p, changes, SUB)

    def test_staged_and_app_plans(self):
        for apps, count in ((False, 16), (True, 21)):
            p, changes = plan(apps)
            self.assertEqual(len(changes), count)
            self.assertEqual(policy.validate(p, changes, SUB), URLS)

    def test_exposure_mutable_images_paid_profiles_and_probe_changes_rejected(self):
        changes_to_try = [('workload_profile_name', 'Dedicated'), ('template', 'image'), ('template', 'memory'), ('ingress', 'external_enabled'), ('secret', 'value'), ('secret', 'identity'), ('template', 'readiness_probe')]
        for field, attribute in changes_to_try:
            p, changes = plan()
            app = next(r for r in changes if r['address'] == 'azurerm_container_app.business["products"]')['change']['after']
            if field == 'workload_profile_name': app[field] = attribute
            elif field == 'ingress': app[field][0][attribute] = True
            elif field == 'secret': app[field][0][attribute] = 'forbidden'
            elif attribute == 'readiness_probe': app['template'][0]['container'][0][attribute][0]['path'] = '/health/live'
            else: app['template'][0]['container'][0][attribute] = 'forbidden'
            with self.subTest(field=field, attribute=attribute), self.assertRaises(ValueError): policy.validate(p, changes, SUB)

    def test_broad_grants_changed_principals_schedules_and_extra_resources_rejected(self):
        for mutation in ('scope', 'principal', 'role', 'schedule', 'retry', 'extra', 'delete'):
            p, changes = plan(False)
            role = next(r for r in changes if r['type'] == 'azurerm_role_assignment')
            job = next(r for r in changes if r['type'] == 'azurerm_container_app_job')
            if mutation == 'scope': role['change']['after']['scope'] = data.VAULT
            if mutation == 'principal': role['change']['after']['principal_id'] = 'other'
            if mutation == 'role': role['change']['after']['role_definition_name'] = 'Owner'
            if mutation == 'schedule': job['change']['after']['schedule_trigger_config'] = [{'cron_expression': '* * * * *'}]
            if mutation == 'retry': job['change']['after']['replica_retry_limit'] = 10
            if mutation == 'extra': changes.append(copy.deepcopy(changes[0]))
            if mutation == 'delete': job['change']['actions'] = ['delete']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): policy.validate(p, changes, SUB)

    def test_unknown_ids_require_unknown_markers(self):
        p, changes = plan()
        app = next(r for r in changes if r['address'] == 'azurerm_container_app.business["products"]')
        app['change']['after']['identity'][0]['identity_ids'] = None
        with self.assertRaises(ValueError): policy.validate(p, changes, SUB)
        app['change']['after_unknown'] = {'identity': [{'identity_ids': True}]}
        policy.validate(p, changes, SUB)
        app['change']['after']['secret'][0]['identity'] = None
        with self.assertRaises(ValueError): policy.validate(p, changes, SUB)
        app['change']['after_unknown']['secret'] = [{'identity': True}]
        policy.validate(p, changes, SUB)
        app['change']['after']['identity'][0]['identity_ids'] = [None]
        app['change']['after_unknown']['identity'] = [{'identity_ids': [True]}]
        policy.validate(p, changes, SUB)
        app['change']['after_unknown']['identity'] = [{'identity_ids': [False]}]
        with self.assertRaises(ValueError): policy.validate(p, changes, SUB)

    def test_yarp_hyphenated_keys_no_localhost_and_secret_env_contract(self):
        p, changes = plan()
        bff = next(r for r in changes if r['address'] == 'azurerm_container_app.business["bff"]')['change']['after']
        env = bff['template'][0]['container'][0]['env']
        name = next(x for x in env if 'orders-cluster' in x['name'])
        self.assertEqual(name['value'], URLS['invoice'] + '/')
        name['value'] = 'http://localhost:5000/'
        with self.assertRaises(ValueError): policy.validate(p, changes, SUB)

class ProofTests(unittest.TestCase):
    def test_source_hash_preserves_linux_order_on_windows(self):
        import hashlib
        from pathlib import PureWindowsPath

        # Include mixed case and a directory/file prefix: both must preserve
        # the original Linux Path order, rather than platform or string order.
        inputs = [
            'scripts/report-database-gate.py',
            'verification/database-gate/Dockerfile',
            'verification/database-gate/azure-runner.py',
            'verification/database-gate/contracts/item.txt',
            'verification/database-gate/contracts.json',
        ]
        expected = hashlib.sha256()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in inputs:
                file = root / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'fixture\n')
                expected.update(relative.encode() + b'\0fixture\n\0')

            def windows_sorted(paths, **kwargs):
                if 'key' not in kwargs:
                    kwargs['key'] = lambda path: PureWindowsPath(str(path))
                return sorted(paths, **kwargs)

            with patch.object(verify.source, 'ROOT', root):
                self.assertEqual(verify.source.source_hash(), expected.hexdigest())
                with patch.object(verify.source, 'sorted', side_effect=windows_sorted, create=True):
                    self.assertEqual(verify.source.source_hash(), expected.hexdigest())

    def test_source_hash_is_identical_for_windows_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath('scripts').mkdir()
            root.joinpath('verification/database-gate').mkdir(parents=True)
            file = root / 'scripts/report-database-gate.py'
            file.write_bytes(b'line one\nline two\n')
            with patch.object(verify.source, 'ROOT', root):
                unix = verify.source.source_hash()
                file.write_bytes(b'line one\r\nline two\r\n')
                self.assertEqual(unix, verify.source.source_hash())

    def test_complete_database_and_runtime_evidence(self):
        value, expected = proof()
        verify.validate_proof(value, expected)
        value['mode'] = 'runtime'
        value['reports'] = {'runtime': payload('runtime'), 'invoice': payload('invoice', '2' * 32)}
        value['executions'] = {'runtime': dict(name='job-ecommerce-dev-database-gate-run123', status='Succeeded'), 'invoice': dict(name='job-ecommerce-dev-invoice-probe-run123', status='Succeeded')}
        value['outside_checks'] = dict.fromkeys(verify.OUTSIDE_CHECKS, True)
        verify.validate_proof(value, expected, mode='runtime')

    def test_every_missing_check_and_unknown_payload_is_rejected(self):
        for index in range(2):
            for name in payload()['suites'][index]['checks']:
                value = payload()
                del value['suites'][index]['checks'][name]
                with self.subTest(index=index, name=name), self.assertRaises(ValueError): verify.validate_payload(value, 'database', '1' * 32)
        for mode in ('database', 'runtime', 'invoice'):
            value = payload(mode); value['private_details'] = 'never publish'
            with self.assertRaises(ValueError): verify.validate_payload(value, mode, '1' * 32)
        value = payload(); value['suites'][0]['raw_connection'] = 'never publish'
        with self.assertRaises(ValueError): verify.validate_payload(value, 'database', '1' * 32)

    def test_failed_native_stale_other_execution_and_binding_rejected(self):
        for mutation in ('failed', 'native', 'stale', 'future', 'subscription', 'images', 'egress', 'execution', 'outside'):
            value, expected = proof()
            if mutation == 'failed': value['reports']['database']['passed'] = False
            if mutation == 'native': value['reports']['database']['suites'] = reports.reports('native-baseline')
            if mutation in ('stale', 'future'):
                value['created_at'] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=-25 if mutation == 'stale' else 1)).isoformat()
            if mutation == 'subscription': value['binding'] = dict(expected, subscription='other')
            if mutation == 'images': value['binding'] = dict(expected, images={})
            if mutation == 'egress': value['binding'] = dict(expected, aca_ipv4=['20.40.60.81'])
            if mutation == 'execution': value['executions']['database']['name'] = 'job-other-run123'
            if mutation == 'outside': value['outside_checks'] = {'private_details': True}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): verify.validate_proof(value, expected)

    def test_log_filter_discards_arbitrary_logs_and_malformed_reports(self):
        lines = ['private application log', 'D9_REPORT:!!!', json.dumps({'Log': marker(payload())}), json.dumps({'Log': 'private error'})]
        self.assertEqual(verify.payloads('\n'.join(lines)), [payload()])

    def test_job_accepts_only_the_started_execution_and_its_run_id(self):
        job = dict(name='job-ecommerce-dev-database-gate', properties={'template': {'containers': [dict(name='gate', image=IMAGE, env=[])]}})
        run_id = '3' * 32
        result = payload(run_id=run_id)
        execution = job['name'] + '-run123'
        requests = []
        def start(args):
            request = Path(args[args.index('--body') + 1][1:])
            requests.append(request)
            self.assertEqual(json.loads(request.read_text())['containers'][0]['env'], [{'name': 'D9_RUN_ID', 'value': run_id}, {'name': 'D9_MODE', 'value': 'database'}])
            return {'name': execution}
        with patch.object(verify, 'uuid4', return_value=type('Id', (), {'hex': run_id})()), patch.object(verify.network.egress, 'az_json', side_effect=start), patch.object(verify.network.egress.shutil, 'which', return_value='az'), patch.object(verify.network.egress.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, marker(result))), patch.object(verify.network.egress, 'arm_get', return_value={'properties': {'status': 'Succeeded'}}) as read:
            self.assertEqual(verify.run_job(job, 'database', SUB), ({'name': execution, 'status': 'Succeeded'}, result))
            self.assertIn('/executions/' + execution, read.call_args.args[0])
        self.assertTrue(all(not path.exists() for path in requests))
        self.assertEqual(job['properties']['template']['containers'][0]['env'], [])

    def test_succeeded_without_matching_report_is_failure(self):
        job = dict(name='job-ecommerce-dev-database-gate', properties={'template': {'containers': [dict(name='gate', env=[])]}})
        with patch.object(verify.network.egress, 'az_json', return_value={'name': job['name'] + '-run123'}), patch.object(verify.network.egress.shutil, 'which', return_value='az'), patch.object(verify.network.egress.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, marker(payload()))), patch.object(verify.network.egress, 'arm_get', return_value={'properties': {'status': 'Succeeded'}}):
            with self.assertRaises(ValueError): verify.run_job(job, 'database', SUB)

class SecretAndEgressTests(unittest.TestCase):
    def test_existing_passwords_are_encoded_and_hosts_match_retained_suite(self):
        candidate = dict(sql_server='sql-ecommerce-dev-d6-reviewd7', mongo_cluster='mongo-ecommerce-dev-d6-reviewd7', sql_database='products-gate')
        password = 'Long!Password;"@/#123'
        values = secrets.connection_values(candidate, password, password)
        self.assertEqual(set(values), set(policy.SECRETS.values()))
        self.assertTrue(values['products-sql-connection'].startswith('Server=sql-ecommerce-dev-d6-reviewd7.database.windows.net;'))
        self.assertIn('Password="Long!Password;""@/#123";', values['products-sql-connection'])
        self.assertIn('%3B%22%40%2F%23', values['users-mongo-connection'])
        with self.assertRaises(ValueError): secrets.connection_values(dict(candidate, sql_database='master'), password, password)

    def test_jobs_and_apps_use_the_union_and_missing_job_addresses_fail(self):
        environment = data.network.ENVIRONMENT
        def response(path, version):
            return {'properties': dict(environmentId=environment, workloadProfileName='Consumption', provisioningState='Succeeded', outboundIpAddresses=['20.40.60.81' if '/jobs/' in path else '20.40.60.80'])}
        egress = verify.network.egress
        with patch.object(egress, 'arm_get', side_effect=response):
            self.assertEqual(egress.discover(SUB, 'cae-ecommerce-dev', ['ca-ecommerce-dev-livedocs'], ['job-ecommerce-dev-database-gate']), ['20.40.60.80', '20.40.60.81'])
        with patch.object(egress, 'arm_get', return_value={'properties': dict(environmentId=environment, workloadProfileName='Consumption', provisioningState='Succeeded', outboundIpAddresses=[])}):
            with self.assertRaises(ValueError): egress.discover(SUB, 'cae-ecommerce-dev', [], ['job-ecommerce-dev-database-gate'])

class LocalLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell required for local lifecycle execution')
    def test_missing_or_failed_database_proof_never_applies_and_cleans_plan(self):
        for failed in (False, True):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                p, _ = plan()
                root.joinpath('plan.json').write_text(json.dumps(p), encoding='utf-8')
                root.joinpath('run.ps1').write_text(r'''param([string]$Repository,[string]$Fixture,[string]$Failed)
$ErrorActionPreference='Stop'
$env:TFSTATE_RESOURCE_GROUP='rg-ecommerce-terraform-state'
$env:TFSTATE_STORAGE_ACCOUNT='stecomtfc3229fd85c06d3'
$env:TFSTATE_CONTAINER='development-state'
$env:LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT='archiveaccount123'
Remove-Item Env:D9_DATABASE_REPORT -ErrorAction SilentlyContinue
if ($Failed -eq 'true') { $env:D9_DATABASE_REPORT='safe-proof.json' }
$global:d9Applies=0
$global:d9Proofs=0
function global:az { $global:LASTEXITCODE=0; '11111111-1111-1111-1111-111111111111' }
function global:terraform {
    $global:LASTEXITCODE=0
    if ($args[0] -eq 'version') { '{"terraform_version":"1.16.5"}' }
    elseif ($args -contains 'show') { Get-Content -LiteralPath $Fixture -Raw }
    elseif ($args -contains 'apply') { $global:d9Applies++ }
}
function global:python {
    $global:LASTEXITCODE=0
    if ($args -contains '--check-report') { $global:d9Proofs++; $global:LASTEXITCODE=1 }
}
try {
    & (Join-Path $Repository 'scripts/deploy-development-network.ps1') -Action apply
    throw 'Missing or failed proof must block apply'
} catch {
    $expected = if ($Failed -eq 'true') { 'D/9 Azure database proof mismatch*' } else { 'Set D9_DATABASE_REPORT*' }
    if ($_.Exception.Message -notlike $expected) { throw }
}
if ($global:d9Applies -ne 0) { throw 'An app was applied without proof' }
if ($global:d9Proofs -ne [int]($Failed -eq 'true')) { throw 'Proof checker was skipped or repeated' }
if (@(Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter 'ecommerce-d7-*').Count -ne 0) { throw 'Private plans left after proof rejection' }
''', encoding='utf-8')
                environment = {name: value for name, value in os.environ.items() if not name.startswith('TF_CLI_ARGS')}
                environment['TEMP'] = directory
                result = subprocess.run(['pwsh', '-NoProfile', '-File', str(root / 'run.ps1'), '-Repository', str(ROOT), '-Fixture', str(root / 'plan.json'), '-Failed', str(failed).lower()], env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
