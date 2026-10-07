"""Copy the existing D/6 credentials into four Key Vault references; never print values."""
import getpass
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('secret_setter', ROOT / 'scripts/set-development-secret.py')
setter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setter)


def connection_values(candidate, sql_password, mongo_password):
    setter.policy.require(re.fullmatch(r'sql-ecommerce-dev-d6-[a-z0-9]{6,16}', candidate['sql_server']))
    setter.policy.require(candidate['mongo_cluster'] == candidate['sql_server'].replace('sql-', 'mongo-', 1))
    setter.policy.require(candidate['sql_database'] == 'products-gate')
    setter.policy.require(all(isinstance(p, str) and 16 <= len(p) <= 128 for p in (sql_password, mongo_password)))
    sql = ('Server=' + candidate['sql_server'] + '.database.windows.net;Database=products-gate;'
           'User ID=d6operator;Password="' + sql_password.replace('"', '""') + '";'
           'Encrypt=True;TrustServerCertificate=False;Connect Timeout=180')
    mongo = ('mongodb+srv://d6operator:' + quote(mongo_password, safe='') + '@' + candidate['mongo_cluster'] +
             '.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000')
    return {'products-sql-connection': sql, **{name + '-mongo-connection': mongo for name in ('users', 'invoice', 'payments')}}


def main():
    setter.policy.require(sys.stdin.isatty())
    cli, terraform = shutil.which('az'), shutil.which('terraform')
    setter.policy.require(cli and terraform)
    def output(*arguments):
        return json.loads(subprocess.run(arguments, capture_output=True, text=True, check=True, timeout=120).stdout)
    account = output(cli, 'account', 'show', '--output', 'json')
    candidate = output(terraform, '-chdir=' + str(ROOT / 'environments/development'), 'output', '-json', 'database_candidate')
    metadata = output(terraform, '-chdir=' + str(ROOT / 'environments/development'), 'output', '-json', 'data_services')
    values = connection_values(candidate,
        os.environ.get('TF_VAR_candidate_sql_password') or getpass.getpass('Existing SQL administrator password (hidden): '),
        os.environ.get('TF_VAR_candidate_mongo_password') or getpass.getpass('Existing Mongo administrator password (hidden): '))
    for name, value in values.items():
        setter.write_secret(metadata, account, name, value)
    print('Four database secrets written through ARM to the deployed business vault. Existing database passwords unchanged; no values printed or added to Terraform.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Database secret configuration failed; private diagnostics withheld. Retain the existing passwords and rerun after checking the deployed vault/account and ARM secret-write permission.')
