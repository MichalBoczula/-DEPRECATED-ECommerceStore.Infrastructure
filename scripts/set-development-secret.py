"""Inject one business secret through ARM; no value enters Terraform or CLI arguments."""
import argparse
import getpass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('data_policy', ROOT / 'scripts/validate-data-services.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def write_secret(metadata, account, name, value):
    require = policy.require
    require(name in policy.SECRET_NAMES.values() and isinstance(value, str) and 0 < len(value.encode()) <= 25 * 1024)
    expected = policy.names(account['id'])
    vault_id = expected['root'] + 'Microsoft.KeyVault/vaults/' + expected['vault']
    require(metadata['key_vault_id'].lower() == vault_id.lower() and metadata['secret_names'] == policy.SECRET_NAMES)
    cli = shutil.which('az')
    require(cli is not None)
    # File permissions are private on Unix; Windows inherits the user's private TEMP ACL.
    with tempfile.TemporaryDirectory(prefix='ecommerce-secret-') as directory:
        path = Path(directory) / 'request.json'
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump({'properties': {'value': value, 'attributes': {'enabled': True}}}, stream)
        subprocess.run([cli, 'rest', '--method', 'put', '--url',
                        'https://management.azure.com' + vault_id + '/secrets/' + name + '?api-version=2023-07-01',
                        '--body', '@' + str(path), '--output', 'none'],
                       capture_output=True, text=True, check=True, timeout=120)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', choices=sorted(policy.SECRET_NAMES.values()), required=True)
    args = parser.parse_args()
    try:
        policy.require(sys.stdin.isatty())
        cli, terraform = shutil.which('az'), shutil.which('terraform')
        policy.require(cli is not None and terraform is not None)
        account = json.loads(subprocess.run([cli, 'account', 'show', '--output', 'json'], capture_output=True, text=True, check=True, timeout=120).stdout)
        metadata = json.loads(subprocess.run([terraform, '-chdir=' + str(ROOT / 'environments/development'), 'output', '-json', 'data_services'],
                                             capture_output=True, text=True, check=True, timeout=120).stdout)
        value = getpass.getpass('Secret value (hidden): ')
        write_secret(metadata, account, args.name, value)
        print('Business secret written through ARM. No value printed or added to Terraform; runtime identity references are configured in D/9/D/13.')
    except Exception:
        raise SystemExit('Secret injection failed. Check Azure login, the deployed business vault and vaults/secrets/write permission; private values and diagnostics withheld.')
