"""Start bounded D/9 jobs and accept only execution-bound, fully validated safe reports."""
import argparse
import base64
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


network = load('d9_network', 'validate-network-plan.py')
report_policy = load('d9_report', 'report-database-gate.py')
public = load('d9_public', 'verify-development-release.py')
source = load('d9_hash', 'gate-source-hash.py')
require = network.require
RUNTIME_CHECKS = {key + '_' + kind for key in network.business.APPS for kind in ('live', 'ready')} | {
    'bff_' + key + '_routing' for key in ('products', 'users', 'invoice', 'payments')}
OUTSIDE_CHECKS = {'public_bff_health'} | {'private_' + key for key in ('products', 'users', 'invoice', 'payments')}


def validate_payload(payload, mode, run_id, backend='azure-candidate'):
    require(payload['schema'] == 1 and payload['mode'] == mode and payload['run_id'] == run_id and payload['passed'] is True)
    require(re.fullmatch('[a-f0-9]{32}', run_id))
    if mode == 'database':
        require(set(payload) == {'schema', 'mode', 'run_id', 'passed', 'suites'} and len(payload['suites']) == 2)
        for index, suite in enumerate(payload['suites']):
            report_policy.validate_suite(suite, backend, index)
            require(suite['passed'] is True)
    else:
        expected = RUNTIME_CHECKS if mode == 'runtime' else {'chromium_pdf'}
        require(mode in ('runtime', 'invoice') and set(payload) == {'schema', 'mode', 'run_id', 'passed', 'checks'})
        require(set(payload['checks']) == expected and all(value is True for value in payload['checks'].values()))


def payloads(logs):
    # CLI wraps lines in JSON with a Log field. Never display unrecognized lines.
    items = []
    for line in logs.splitlines():
        try:
            parsed = json.loads(line)
            line = parsed.get('Log', '') if isinstance(parsed, dict) else ''
        except (ValueError, TypeError):
            pass
        if line.startswith('D9_REPORT:') and len(line) <= 65536:
            try:
                data = base64.b64decode(line.removeprefix('D9_REPORT:'), validate=True)
                items.append(json.loads(data))
            except (ValueError, TypeError):
                pass
    return items


def binding(metadata, subscription, access):
    return dict(subscription=subscription, release_id=metadata['release_id'],
                gate_image=metadata['gate']['image'], images={key: value['image'] for key, value in metadata['apps'].items()},
                candidate=metadata['candidate'], aca_ipv4=network.egress.public_ipv4(access['aca_ipv4']))


def validate_proof(proof, expected, *, mode='database'):
    require(set(proof) == {'schema', 'mode', 'created_at', 'binding', 'executions', 'reports', 'outside_checks'})
    require(proof['schema'] == 1 and proof['mode'] == mode and proof['binding'] == expected)
    created = datetime.datetime.fromisoformat(proof['created_at'])
    require(created.tzinfo is not None and datetime.timedelta(0) <= datetime.datetime.now(datetime.timezone.utc) - created < datetime.timedelta(hours=24))
    modes = ['database'] if mode == 'database' else ['runtime', 'invoice']
    require(set(proof['reports']) == set(modes) and set(proof['executions']) == set(modes))
    for key in modes:
        execution = proof['executions'][key]
        require(set(execution) == {'name', 'status'} and execution['status'] == 'Succeeded')
        prefix = 'job-ecommerce-dev-invoice-probe-' if key == 'invoice' else 'job-ecommerce-dev-database-gate-'
        require(isinstance(execution['name'], str) and execution['name'].startswith(prefix) and re.fullmatch('[a-z0-9-]+', execution['name']))
        payload = proof['reports'][key]
        validate_payload(payload, key, payload['run_id'])
    require(len({item['run_id'] for item in proof['reports'].values()}) == len(modes))
    require(proof['outside_checks'] == ({} if mode == 'database' else {key: True for key in OUTSIDE_CHECKS}))


def verify_image(image):
    require(re.fullmatch(r'mb0101/ecommerce-store-database-gate@sha256:[a-f0-9]{64}', image))
    repository, digest = image.split('@')
    token = json.loads(public.get('https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + repository + ':pull'))['token']
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json'}
    prefix = 'https://registry-1.docker.io/v2/' + repository
    raw = public.get(prefix + '/manifests/' + digest, headers)
    require('sha256:' + hashlib.sha256(raw).hexdigest() == digest)
    manifest = json.loads(raw)
    # Publication uses docker push of the tested single-platform image, without rebuild.
    config_raw = public.get(prefix + '/blobs/' + manifest['config']['digest'], headers)
    require('sha256:' + hashlib.sha256(config_raw).hexdigest() == manifest['config']['digest'])
    config = json.loads(config_raw)
    labels = config['config']['Labels']
    require(config['architecture'] == 'amd64' and config['os'] == 'linux')
    require(labels['org.opencontainers.image.source'] == 'https://github.com/MichalBoczula/ECommerceStore.Infrastructure')
    require(re.fullmatch('[a-f0-9]{40}', labels['org.opencontainers.image.revision']))
    require(labels['ecommerce.gate-source-sha256'] == source.source_hash())
    require(labels['ecommerce.payments-commit'] == '9663df14cb10886a32fa7850d1ca51537a3da009')
    require(config['config']['Entrypoint'] == ['python', '/gate/verification/database-gate/azure-runner.py'])


def read_output(name):
    terraform = network.egress.shutil.which('terraform')
    require(terraform is not None)
    return json.loads(network.egress.subprocess.run([terraform, '-chdir=' + str(ROOT / 'environments/development'), 'output', '-json', name],
        capture_output=True, text=True, check=True, timeout=120).stdout)


def verify_arm(metadata, subscription):
    root = f'/subscriptions/{subscription}/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/'
    require(metadata['environment_id'].lower() == (root + 'managedEnvironments/cae-ecommerce-dev').lower())
    expected_names = {key: 'ca-ecommerce-dev-' + key for key in network.business.APPS}
    require(set(metadata['apps']) == set(expected_names))
    release = json.loads((ROOT / 'releases/development.json').read_text())
    names = network.data_services.names(subscription)
    for key, app in metadata['apps'].items():
        require(app['name'] == expected_names[key] and app['image'] == release['applications'][key]['image'])
        require(app['identity_id'].lower() == (names['root'] + 'Microsoft.ManagedIdentity/userAssignedIdentities/id-ecommerce-dev-' + key).lower())
        require(re.fullmatch(r'https://ca-ecommerce-dev-' + key + (r'\.internal' if key != 'bff' else '') + r'\.[a-z0-9-]+\.northeurope\.azurecontainerapps\.io', app['url']))
        if metadata['apps_enabled']:
            resource = network.egress.arm_get(root + 'containerApps/' + app['name'], '2025-07-01')
            p = resource['properties']
            require(p['provisioningState'] == 'Succeeded' and p['workloadProfileName'] == 'Consumption')
            require((p.get('environmentId') or p.get('managedEnvironmentId', '')).lower() == metadata['environment_id'].lower())
            cfg, template = p['configuration'], p['template']
            require(cfg['ingress']['external'] is (key == 'bff') and cfg['ingress'].get('allowInsecure') is not True and cfg['ingress']['targetPort'] == 8080)
            require(cfg['ingress']['fqdn'] == app['url'].removeprefix('https://'))
            require(template['scale']['minReplicas'] == 0 and template['scale']['maxReplicas'] == 1 and len(template['containers']) == 1)
            container = template['containers'][0]
            require(container['image'] == app['image'] and container['resources']['cpu'] == network.business.ALLOCATIONS[key][0] and container['resources']['memory'] == network.business.ALLOCATIONS[key][1])
            require(set(resource['identity']['userAssignedIdentities']) == {app['identity_id']})
            env = {item['name']: item for item in container['env']}
            for name, value in network.business.plain_env(key, {k: v['url'] for k, v in metadata['apps'].items()}).items():
                require(env[name]['value'] == value and not env[name].get('secretRef'))
            if key != 'bff':
                require(env[network.business.SECRET_ENV[key]]['secretRef'] == 'connection')
                secrets = cfg['secrets']
                require(len(secrets) == 1 and secrets[0]['name'] == 'connection')
                require(secrets[0]['keyVaultUrl'] == 'https://' + names['vault'] + '.vault.azure.net/secrets/' + network.business.SECRETS[key])
                require(secrets[0]['identity'].lower() == app['identity_id'].lower() and not secrets[0].get('value'))
            else:
                require(not cfg.get('secrets'))
    jobs = {}
    for key, name, container_name, image, timeout in [('gate', 'job-ecommerce-dev-database-gate', 'gate', metadata['gate']['image'], 1800),
             ('invoice_probe', 'job-ecommerce-dev-invoice-probe', 'invoice-probe', release['applications']['invoice']['image'], 300)]:
        require(metadata[key]['name'] == name and metadata[key]['image'] == image)
        job = network.egress.arm_get(root + 'jobs/' + name, '2025-07-01')
        p = job['properties']
        require(p['provisioningState'] == 'Succeeded' and p['environmentId'].lower() == metadata['environment_id'].lower() and p['workloadProfileName'] == 'Consumption')
        cfg = p['configuration']
        require(cfg['triggerType'] == 'Manual' and cfg['replicaRetryLimit'] == 0 and cfg['replicaTimeout'] == timeout)
        require(cfg['manualTriggerConfig'] == {'parallelism': 1, 'replicaCompletionCount': 1})
        require(len(p['template']['containers']) == 1)
        container = p['template']['containers'][0]
        require(container['name'] == container_name and container['image'] == image and container['resources']['cpu'] == 1 and container['resources']['memory'] == '2Gi')
        if key == 'gate':
            require(not container.get('command') and not container.get('args'))
            env = {item['name']: item for item in container['env']}
            require(env['D6_SQL_HOST']['value'] == metadata['candidate']['sql_server'] + '.database.windows.net')
            require(env['D6_MONGO_HOST']['value'] == metadata['candidate']['mongo_cluster'] + '.mongocluster.cosmos.azure.com')
            require(json.loads(env['D9_APPS']['value']) == {k: v['url'] for k, v in metadata['apps'].items()})
            identity = names['root'] + 'Microsoft.ManagedIdentity/userAssignedIdentities/id-ecommerce-dev-gate'
            require(set(job['identity']['userAssignedIdentities']) == {identity})
            secrets = {item['name']: item for item in cfg['secrets']}
            require(set(secrets) == {'sql', 'mongo'})
            for secret, field, key_name in [('sql', 'D6_SQL_CONNECTION_STRING', 'products'), ('mongo', 'D6_MONGO_CONNECTION_STRING', 'users')]:
                require(env[field]['secretRef'] == secret and not env[field].get('value'))
                require(secrets[secret]['identity'].lower() == identity.lower() and secrets[secret]['keyVaultUrl'] == 'https://' + names['vault'] + '.vault.azure.net/secrets/' + network.business.SECRETS[key_name])
                require(not secrets[secret].get('value'))
        else:
            require(not cfg.get('secrets') and not job.get('identity', {}).get('userAssignedIdentities'))
            require(container['command'] == ['pwsh', '-NoProfile', '-Command', (ROOT / 'verification/database-gate/invoice-probe.ps1').read_text()])
        jobs[key] = job
    return jobs


def run_job(job, mode, subscription):
    require(re.fullmatch('[0-9a-fA-F-]{36}', subscription))
    name = job['name']
    expected = 'job-ecommerce-dev-invoice-probe' if mode == 'invoice' else 'job-ecommerce-dev-database-gate'
    require(name == expected)
    template = copy.deepcopy(job['properties']['template'])
    container = template['containers'][0]
    run_id = uuid4().hex
    env = {item['name']: item for item in container['env']}
    env['D9_RUN_ID'] = {'name': 'D9_RUN_ID', 'value': run_id}
    if mode != 'invoice':
        env['D9_MODE'] = {'name': 'D9_MODE', 'value': mode}
    container['env'] = list(env.values())
    base = f'/subscriptions/{subscription}/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/jobs/{name}'
    with tempfile.TemporaryDirectory(prefix='ecommerce-d9-start-') as directory:
        request = Path(directory) / 'start.json'
        request.write_text(json.dumps(template), encoding='utf-8')  # references only, no secret values
        execution = network.egress.az_json(['rest', '--method', 'post', '--url', 'https://management.azure.com' + base + '/start?api-version=2025-07-01', '--body', '@' + str(request)])
    execution_name = execution['name']
    require(execution_name.startswith(name + '-') and re.fullmatch('[a-z0-9-]+', execution_name))
    payload = None
    deadline = time.monotonic() + (1980 if mode != 'invoice' else 480)
    while time.monotonic() < deadline:
        # Use one specific execution/container; capture and filter all raw logs privately.
        try:
            cli = network.egress.shutil.which('az')
            logs = network.egress.subprocess.run([cli, 'containerapp', 'job', 'logs', 'show', '--subscription', subscription,
                    '--resource-group', 'rg-ecommerce-dev', '--name', name, '--execution', execution_name,
                    '--container', container['name'], '--tail', '300', '--format', 'json', '--only-show-errors'],
                    capture_output=True, text=True, check=True, timeout=30).stdout
            matching = [item for item in payloads(logs) if item.get('mode') == mode and item.get('run_id') == run_id]
            require(len(matching) <= 1)
            if matching:
                validate_payload(matching[0], mode, run_id)
                payload = matching[0]
        except (network.egress.subprocess.SubprocessError, OSError):
            pass  # Replica creation/log streaming may not yet be ready.
        current = network.egress.arm_get(base + '/executions/' + execution_name, '2025-07-01')
        status = current['properties']['status']
        if status == 'Succeeded':
            require(payload is not None)
            return {'name': execution_name, 'status': status}, payload
        require(status not in ('Failed', 'Stopped', 'Canceled'))
        time.sleep(5)
    raise ValueError('Bounded verification did not complete')


def outside_checks(metadata):
    runner_spec = importlib.util.spec_from_file_location('d9_http', ROOT / 'verification/database-gate/azure-runner.py')
    runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(runner)
    opener = urllib.request.build_opener(runner.NoRedirect)
    results = {'public_bff_health': False, **{'private_' + key: False for key in ('products', 'users', 'invoice', 'payments')}}
    with opener.open(metadata['apps']['bff']['url'] + '/health', timeout=60) as response:
        results['public_bff_health'] = response.status == 200
    for key in ('products', 'users', 'invoice', 'payments'):
        try:
            with opener.open(metadata['apps'][key]['url'] + '/health/live', timeout=30):
                pass  # Any public success is a failure, not proof of internal ingress.
        except urllib.error.HTTPError as error:
            results['private_' + key] = error.code in (403, 404)
    require(all(results.values()))
    return results


def main(args):
    if args.verify_image:
        verify_image(args.verify_image)
        print('D/9 published verification image matches the immutable digest, platform and checked harness source hash.')
        return
    if args.native_image_report:
        found = payloads(args.native_image_report.read_text())
        require(len(found) == 1)
        validate_payload(found[0], 'database', '11111111111111111111111111111111', 'native-baseline')
        print('D/9 portable verification image passed both complete native suites. Azure compatibility remains pending.')
        return
    if args.invoice_image_report:
        found = payloads(args.invoice_image_report.read_text())
        require(len(found) == 1)
        validate_payload(found[0], 'invoice', '11111111111111111111111111111111')
        print('Exact Invoice image generated a Chromium PDF at 1 CPU / 2 GiB. Azure execution remains pending.')
        return
    if args.check_report:
        plan = json.loads(args.plan_file.read_text(encoding='utf-8'))
        metadata = plan['planned_values']['outputs']['business_runtime']['value']
        access = plan['planned_values']['outputs']['network_access']['value']
        validate_proof(json.loads(args.check_report.read_text()), binding(metadata, args.subscription, access))
        print('D/9 matching Azure database proof verified before business apply.')
        return
    account = network.egress.az_json(['account', 'show'])
    subscription = account['id']
    metadata, access = read_output('business_runtime'), read_output('network_access')
    require(access['database_access_enabled'] is True)
    network.readback(access, subscription)
    verify_image(metadata['gate']['image'])
    jobs = verify_arm(metadata, subscription)
    expected = binding(metadata, subscription, access)
    if args.mode == 'runtime':
        require(metadata['apps_enabled'] is True and args.database_report)
        validate_proof(json.loads(args.database_report.read_text()), expected)
    executions, reports = {}, {}
    modes = ['database'] if args.mode == 'database' else ['runtime', 'invoice']
    for mode in modes:
        print('Starting bounded Azure verification: ' + mode, flush=True)
        executions[mode], reports[mode] = run_job(jobs['invoice_probe' if mode == 'invoice' else 'gate'], mode, subscription)
    proof = dict(schema=1, mode=args.mode, created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 binding=expected, executions=executions, reports=reports,
                 outside_checks={} if args.mode == 'database' else outside_checks(metadata))
    validate_proof(proof, expected, mode=args.mode)
    if args.output is None:
        args.output = ROOT / ('artifacts/d9/' + args.mode + '-proof.json')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    print('D/9 ' + args.mode + ' verification passed; complete safe report saved. No business-flow or backend-selection claim.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['database', 'runtime'], default='database')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--database-report', type=Path)
    parser.add_argument('--check-report', type=Path)
    parser.add_argument('--plan-file', type=Path)
    parser.add_argument('--subscription')
    parser.add_argument('--native-image-report', type=Path)
    parser.add_argument('--invoice-image-report', type=Path)
    parser.add_argument('--verify-image')
    args = parser.parse_args()
    try:
        require(not args.check_report or (args.plan_file and args.subscription))
        main(args)
    except Exception:
        raise SystemExit('D/9 verification failed; raw Azure/application diagnostics withheld. Keep partial state and existing credentials; do not widen access or roll out apps without the complete matching report.')
