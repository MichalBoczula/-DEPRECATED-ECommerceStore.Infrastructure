"""Exercise D/7 policy with genuine credential-free Terraform mock plans."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import traceback

spec = importlib.util.spec_from_file_location('network_policy', Path(__file__).with_name('validate-network-plan.py'))
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

# Terraform's test renderer omits variables/configuration (unlike show -json).
# Pair genuine resource changes with explicit case inputs; keep production
# validation strict and verify parent expressions against the checked-out source.
def envelope(name):
    variables = dict(enable_shared_environment=True, enable_livedocs=False,
                     enable_database_candidate=False, enable_database_access=False,
                     database_aca_ipv4=[], name_prefix='ecommerce', location='northeurope',
                     candidate_suffix='', candidate_sql_location='northeurope', enable_data_services=False)
    if name == 'aca_database_access':
        variables.update(enable_livedocs=True, enable_database_candidate=True,
                         enable_database_access=True, candidate_suffix='reviewd7',
                         candidate_sql_location='francecentral', database_aca_ipv4=['20.40.60.80', '20.40.60.81'])
    elif name == 'livedocs_uses_shared_environment':
        variables.update(enable_shared_environment=False, enable_livedocs=True)
    elif name in ('data_services_without_docs', 'data_services_with_databases'):
        variables.update(enable_data_services=True)
        if name == 'data_services_with_databases':
            variables.update(enable_livedocs=True, enable_database_candidate=True, candidate_suffix='reviewd7', candidate_sql_location='francecentral')
    root = Path(__file__).resolve().parents[1] / 'environments/development'
    source = '\n'.join((root / path).read_text() for path in ('database-candidate.tf', 'network-access.tf'))
    blocks = {kind + '.' + resource: body for kind, resource, body in
              re.findall(r'^resource "([^"]+)" "([^"]+)"\s*\{(.*?)^\}', source, re.M | re.S)}
    parents = {'azapi_resource.sql_candidate': ('parent_id', 'azurerm_mssql_server.database_candidate'),
               'azurerm_mssql_firewall_rule.aca': ('server_id', 'azurerm_mssql_server.database_candidate'),
               'azapi_resource.mongo_aca_firewall': ('parent_id', 'azapi_resource.mongo_candidate')}
    resources = []
    for address, (field, parent) in parents.items():
        match = re.search(r'^\s*' + field + r'\s*=\s*([a-zA-Z0-9_.]+)\[0\]\.id\s*$', blocks[address], re.M)
        if not match or match.group(1) != parent:
            raise ValueError('Unexpected source parent expression')
        resources.append(dict(address=address, expressions={field: {'references': [parent]}}))
    configuration = {'root_module': {'resources': resources}}
    if variables['enable_data_services']:
        # Verify the real source bindings before reconstructing omitted test metadata.
        source = (root / 'data-services.tf').read_text()
        for field, reference in (('subnet_id', 'module.consumption[0].subnet_id'),
                                 ('tenant_id', 'data.azurerm_client_config.data_services[0].tenant_id')):
            if not re.search(r'^\s*' + field + r'\s*=\s*' + re.escape(reference) + r'\s*$', source, re.M):
                raise ValueError('Unexpected D/8 parent source')
        module_source = (root.parents[1] / 'modules/data-services/main.tf').read_text()
        if not re.search(r'^\s*storage_account_id\s*=\s*azurerm_storage_account.business.id\s*$', module_source, re.M):
            raise ValueError('Unexpected business container parent')
        configuration['root_module']['module_calls'] = {'data_services': {
            'expressions': {'subnet_id': {'references': ['module.consumption[0].subnet_id']},
                            'tenant_id': {'references': ['data.azurerm_client_config.data_services[0].tenant_id']}},
            'module': {'resources': [{'address': 'azurerm_storage_container.files', 'expressions': {'storage_account_id': {'references': ['azurerm_storage_account.business']}}}]}}}
    return dict(variables={key: {'value': value} for key, value in variables.items()}, configuration=configuration)

if __name__ == '__main__':
    try:
        expected = {'shared_environment_without_docs', 'aca_database_access', 'livedocs_uses_shared_environment', 'data_services_without_docs', 'data_services_with_databases'}
        seen = set()
        for line in Path(sys.argv[1]).read_text().splitlines():
            message = json.loads(line)
            name = message.get('@testrun')
            if message.get('type') == 'test_plan' and name in expected:
                policy.validate({**message['test_plan'], **envelope(name)}, subscription='11111111-1111-1111-1111-111111111111')
                seen.add(name)
                print('D/7 mock-plan policy passed: ' + name)
        if seen != expected:
            raise ValueError('Required plans missing')
        print('D/7 policy accepts actual Terraform resource values with reviewed test inputs and checked source parents; no Azure access.')
    except Exception as error:
        # Source locations identify policy/schema mismatches without plan values.
        for frame in traceback.extract_tb(error.__traceback__):
            filename = Path(frame.filename).name
            if filename in ('check-network-test-plans.py', 'validate-network-plan.py', 'validate-database-candidate.py', 'validate-livedocs-plan.py'):
                print(f'{filename}:{frame.lineno}: D/7 mock-plan policy diagnostic', file=sys.stderr)
        raise SystemExit('D/7 mock-plan policy failed; raw plan values and diagnostics withheld.')
