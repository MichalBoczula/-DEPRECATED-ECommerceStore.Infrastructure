"""Exercise local ARM readback through the platform's real process launcher."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidate_cli', ROOT / 'scripts/validate-database-candidate.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ReadbackCliTests(unittest.TestCase):
    names = dict(sql_server='sql-ecommerce-dev-d6-example', sql_database='products-gate',
                 mongo_cluster='mongo-ecommerce-dev-d6-example', sql_location='francecentral')
    subscription = '11111111-1111-1111-1111-111111111111'

    def test_missing_cli_fails_before_any_arm_request(self):
        with patch.object(policy.shutil, 'which', return_value=None), patch.object(policy.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                policy.readback(self.names, self.subscription)
            run.assert_not_called()

    def test_native_or_windows_cmd_launcher_with_spaces_and_region_split(self):
        with tempfile.TemporaryDirectory() as directory:
            cli_dir = Path(directory) / 'cli with spaces'
            cli_dir.mkdir()
            helper = cli_dir / 'fake_azure.py'
            helper.write_text('''import json, sys
assert sys.argv[1:4] == ['rest', '--method', 'get']
assert sys.argv[-2:] == ['--output', 'json']
url = sys.argv[5]
if '/mongoClusters/' in url:
    result = {'location':'northeurope', 'properties':{'compute':{'tier':'Free'}, 'storage':{'sizeGb':32}, 'sharding':{'shardCount':1}, 'highAvailability':{'targetMode':'Disabled'}, 'publicNetworkAccess':'Disabled'}}
elif '/databases/' in url:
    result = {'location':'francecentral', 'sku':{'name':'GP_S_Gen5_2','tier':'GeneralPurpose','family':'Gen5','capacity':2}, 'properties':{'useFreeLimit':True,'freeLimitExhaustionBehavior':'AutoPause','maxSizeBytes':34359738368,'requestedBackupStorageRedundancy':'Local','autoPauseDelay':60,'minCapacity':0.5,'zoneRedundant':False}}
else:
    result = {'location':'francecentral','properties':{'publicNetworkAccess':'Disabled'}}
print(json.dumps(result))
''', encoding='utf-8')
            if os.name == 'nt':
                launcher = cli_dir / 'az.cmd'
                launcher.write_text(f'@"{sys.executable}" "{helper}" %*\n', encoding='utf-8')
            else:
                launcher = cli_dir / 'az'
                launcher.write_text(f'#!{sys.executable}\n' + helper.read_text(encoding='utf-8'), encoding='utf-8')
                launcher.chmod(0o700)
            with patch.dict(os.environ, PATH=str(cli_dir) + os.pathsep + os.environ['PATH']):
                policy.readback(self.names, self.subscription)


if __name__ == '__main__':
    unittest.main()
