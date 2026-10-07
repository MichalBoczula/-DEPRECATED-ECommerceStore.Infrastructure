"""Bounded Azure-side compatibility/routing runner; prints validated reports only."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gate_report', ROOT / 'scripts/report-database-gate.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def runtime_checks(apps):
    checks = {}
    opener = urllib.request.build_opener(NoRedirect)
    for key in ('products', 'users', 'invoice', 'payments', 'bff'):
        for kind, path in (('live', '/health' if key == 'bff' else '/health/live'),
                           ('ready', '/health' if key == 'bff' else '/health/ready')):
            label = key + '_' + kind
            checks[label] = False
            # Cold start and SQL resume are bounded; do not turn readiness into liveness.
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    with opener.open(apps[key] + path, timeout=15) as response:
                        checks[label] = response.status == 200
                    if checks[label]:
                        break
                except Exception:
                    pass
                time.sleep(3)
    for key, path in (('products', '/api/products/swagger/v1/swagger.json'),
                      ('users', '/api/users/swagger/v1/swagger.json'),
                      ('invoice', '/api/orders/swagger/v1/swagger.json'),
                      ('payments', '/api/payments/openapi.json')):
        label = 'bff_' + key + '_routing'
        checks[label] = False
        try:
            with opener.open(apps['bff'] + path, timeout=60) as response:
                contract = json.loads(response.read(2 * 1024 * 1024))
                checks[label] = response.status == 200 and isinstance(contract.get('paths'), dict) and bool(contract['paths'])
        except Exception:
            pass
    return checks


def run():
    mode = os.environ.get('D9_MODE', 'database')
    run_id = os.environ.get('D9_RUN_ID', '')
    if mode not in ('database', 'runtime') or not re.fullmatch('[a-f0-9]{32}', run_id):
        raise ValueError()
    backend = os.environ.get('D9_BACKEND', 'azure-candidate')
    if backend not in ('azure-candidate', 'native-baseline'):
        raise ValueError()
    result = dict(schema=1, mode=mode, run_id=run_id, passed=False)
    if mode == 'database':
        with tempfile.TemporaryDirectory(prefix='d9-') as directory:
            files = [str(Path(directory) / name) for name in ('dotnet.json', 'payments.json')]
            commands = [(['dotnet', '/gate/dotnet/DatabaseGate.dll', backend, files[0]], 600),
                        (['/payments/.venv/bin/python', str(ROOT / 'verification/database-gate/payments-gate.py'),
                          backend, '/payments', files[1]], 900)]
            statuses = []
            for command, timeout in commands:
                try:
                    statuses.append(subprocess.run(command, capture_output=True, timeout=timeout, check=False).returncode == 0)
                except Exception:
                    statuses.append(False)
            # The retained parser rejects shortened success, unknown checks and driver drift.
            suites = [json.loads(Path(path).read_text()) for path in files]
            for index, suite in enumerate(suites):
                policy.validate_suite(suite, backend, index)
            _, passed = policy.report(backend, files)
            result.update(suites=suites, passed=passed and all(statuses))
    else:
        apps = json.loads(os.environ['D9_APPS'])
        if set(apps) != {'products', 'users', 'invoice', 'payments', 'bff'}:
            raise ValueError()
        checks = runtime_checks(apps)
        result.update(checks=checks, passed=all(checks.values()))
    return result


if __name__ == '__main__':
    try:
        result = run()
    except BaseException:
        result = dict(schema=1, mode=os.environ.get('D9_MODE', 'database'),
                      run_id=os.environ.get('D9_RUN_ID', ''), passed=False, checks={'runner_completed': False})
    print('D9_REPORT:' + base64.b64encode(json.dumps(result, separators=(',', ':')).encode()).decode(), flush=True)
    if os.environ.get('D9_BACKEND') != 'native-baseline':
        time.sleep(90)  # Job remains bounded; operator collects this report while replica exists.
    raise SystemExit(0 if result['passed'] else 1)
