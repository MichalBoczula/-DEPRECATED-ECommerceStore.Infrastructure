"""Exercise D/7 policy with genuine credential-free Terraform mock plans."""
import importlib.util
import json
from pathlib import Path
import sys

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
        if seen != expected:
            raise ValueError('Required plans missing')
        print('D/7 policy accepts actual Terraform shared-environment, LiveDocs and exact-IP mock plans; no Azure access.')
    except Exception:
        raise SystemExit('D/7 mock-plan policy failed; raw plan values and diagnostics withheld.')
