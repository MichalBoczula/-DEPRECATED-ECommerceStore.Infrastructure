"""Exercise D/7 policy with genuine credential-free Terraform mock plans."""
import importlib.util
import json
from pathlib import Path
import sys
import traceback

spec = importlib.util.spec_from_file_location('network_policy', Path(__file__).with_name('validate-network-plan.py'))
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

if __name__ == '__main__':
    try:
        expected = {'shared_environment_without_docs', 'aca_database_access', 'livedocs_uses_shared_environment'}
        seen = set()
        for line in Path(sys.argv[1]).read_text().splitlines():
            message = json.loads(line)
            name = message.get('@testrun')
            if message.get('type') == 'test_plan' and name in expected:
                policy.validate(message['test_plan'])
                seen.add(name)
                print('D/7 mock-plan policy passed: ' + name)
        if seen != expected:
            raise ValueError('Required plans missing')
        print('D/7 policy accepts actual Terraform shared-environment, LiveDocs and exact-IP mock plans; no Azure access.')
    except Exception as error:
        # Source locations identify policy/schema mismatches without plan values.
        for frame in traceback.extract_tb(error.__traceback__):
            filename = Path(frame.filename).name
            if filename in ('check-network-test-plans.py', 'validate-network-plan.py', 'validate-database-candidate.py', 'validate-livedocs-plan.py'):
                print(f'{filename}:{frame.lineno}: D/7 mock-plan policy diagnostic', file=sys.stderr)
        raise SystemExit('D/7 mock-plan policy failed; raw plan values and diagnostics withheld.')
