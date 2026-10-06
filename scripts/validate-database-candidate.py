"""Approve only the three explicit D/6 candidate resources in development state."""
import json
import re
import shutil
import sys
import subprocess

CANDIDATE = {
    'azurerm_mssql_server.database_candidate[0]': 'azurerm_mssql_server',
    'azapi_resource.sql_candidate[0]': 'azapi_resource',
    'azapi_resource.mongo_candidate[0]': 'azapi_resource',
}
LIVEDOCS = {
    'module.consumption[0].azurerm_virtual_network.host': 'azurerm_virtual_network',
    'module.consumption[0].azurerm_subnet.host': 'azurerm_subnet',
    'module.consumption[0].azurerm_container_app_environment.host': 'azurerm_container_app_environment',
    'module.livedocs[0].azurerm_container_app.host': 'azurerm_container_app',
}


def require(value):
    if not value:
        raise ValueError('D/6 candidate policy rejected the plan')


def sql_free(body):
    require(body['sku'] == {'name': 'GP_S_Gen5_2', 'tier': 'GeneralPurpose', 'family': 'Gen5', 'capacity': 2})
    p = body['properties']
    require(p['useFreeLimit'] is True and p['freeLimitExhaustionBehavior'] == 'AutoPause')
    require(p['maxSizeBytes'] == 34359738368 and p['requestedBackupStorageRedundancy'] == 'Local')
    require(p['autoPauseDelay'] == 60 and p['minCapacity'] == 0.5 and p['zoneRedundant'] is False)


def validate(plan):
    require(not plan.get('errored') and plan.get('complete') is not False)
    sql_location = plan['variables']['candidate_sql_location']['value']
    require(re.fullmatch(r'[a-z][a-z0-9]+', sql_location))
    seen = set()
    counts = {'create': 0, 'update': 0}
    resources = {r['address']: r for r in plan.get('configuration', {}).get('root_module', {}).get('resources', [])}
    for item in plan.get('resource_changes', []):
        if item.get('mode') != 'managed':
            continue
        address, kind, change = item['address'], item['type'], item['change']
        if address in LIVEDOCS:
            require(LIVEDOCS[address] == kind and change['actions'] == ['no-op'])
            require(change['after']['resource_group_name'] == 'rg-ecommerce-dev')
            continue
        require(CANDIDATE.get(address) == kind and address not in seen)
        require(change['actions'] in (['create'], ['update'], ['no-op']))
        seen.add(address)
        after = change['after']
        if kind == 'azurerm_mssql_server':
            require(after['resource_group_name'] == 'rg-ecommerce-dev' and after['location'] == sql_location)
            require(after['minimum_tls_version'] == '1.2' and after['version'] == '12.0')
            require(after['public_network_access_enabled'] is False)
        if address == 'azapi_resource.sql_candidate[0]':
            require(after['type'] == 'Microsoft.Sql/servers/databases@2023-08-01' and after['name'] == 'products-gate')
            require(after['location'] == sql_location)
            sql_free(after['body'])
            require('azurerm_mssql_server.database_candidate' in resources[address.removesuffix('[0]')]['expressions']['parent_id']['references'])
        if address == 'azapi_resource.mongo_candidate[0]':
            require(after['type'] == 'Microsoft.DocumentDB/mongoClusters@2026-06-01' and after['location'] == 'northeurope')
            require(re.fullmatch(r'/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/rg-ecommerce-dev', after['parent_id']))
            p = after['body']['properties']
            require(p['compute']['tier'] == 'Free' and p['storage'] == {'sizeGb': 32, 'type': 'PremiumSSD'})
            require(p['sharding']['shardCount'] == 1 and p['highAvailability']['targetMode'] == 'Disabled')
            require(p['serverVersion'] == '8.0' and p['publicNetworkAccess'] == 'Disabled' and p['createMode'] == 'Default')
            require(p['authConfig']['allowedModes'] == ['NativeAuth'] and p['administrator'].get('userName') == 'd6operator')
        if change['actions'] != ['no-op']:
            counts[change['actions'][0]] += 1
    require(seen == set(CANDIDATE))
    return counts


def validate_readback(server, database, mongo, sql_location):
    """Check service-reported offer and network settings without a data connection."""
    require(server['properties']['publicNetworkAccess'] == 'Disabled')
    sql_free({
        'sku': {key: database['sku'][key] for key in ('name', 'tier', 'family', 'capacity')},
        'properties': database['properties'],
    })
    p = mongo['properties']
    require(p['compute']['tier'] == 'Free' and p['storage']['sizeGb'] == 32)
    require(p['sharding']['shardCount'] == 1 and p['highAvailability']['targetMode'] == 'Disabled')
    require(p['publicNetworkAccess'] == 'Disabled')
    require(re.fullmatch(r'[a-z][a-z0-9]+', sql_location))
    require(all(item['location'].replace(' ', '').lower() == sql_location for item in (server, database)))
    require(mongo['location'].replace(' ', '').lower() == 'northeurope')


def readback(names, subscription):
    require(re.fullmatch(r'[0-9a-fA-F-]{36}', subscription))
    require(re.fullmatch(r'sql-[a-z0-9-]+', names['sql_server']))
    require(re.fullmatch(r'mongo-[a-z0-9-]+', names['mongo_cluster']))
    require(names['sql_database'] == 'products-gate')
    root = f'https://management.azure.com/subscriptions/{subscription}/resourceGroups/rg-ecommerce-dev/providers/'
    sql = root + 'Microsoft.Sql/servers/' + names['sql_server']
    urls = [sql + '?api-version=2023-08-01',
            sql + '/databases/products-gate?api-version=2023-08-01',
            root + 'Microsoft.DocumentDB/mongoClusters/' + names['mongo_cluster'] + '?api-version=2026-06-01']
    # Windows installs Azure CLI as az.cmd; resolve PATH/PATHEXT explicitly.
    azure_cli = shutil.which('az')
    require(azure_cli is not None)
    responses = [json.loads(subprocess.run(
        [azure_cli, 'rest', '--method', 'get', '--url', url, '--output', 'json'],
        capture_output=True, text=True, check=True, timeout=120).stdout) for url in urls]
    validate_readback(*responses, names['sql_location'])


if __name__ == '__main__':
    try:
        with open(sys.argv[1]) as file:
            payload = json.load(file)
        if len(sys.argv) == 4 and sys.argv[2] == '--readback':
            readback(payload, sys.argv[3])
            print('D/6 Azure readback verified: Free settings and public database access disabled. Application compatibility remains pending D/9.')
        else:
            result = validate(payload)
            print(f"D/6 candidate plan verified: {result['create']} creates, {result['update']} updates; Free tiers, public database access disabled, no app mutations.")
    except Exception:
        raise SystemExit('D/6 verification failed; inspect raw diagnostics only in a secure session.')
