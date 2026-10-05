"""Approve only the five explicit D/6 candidate resources in development state."""
import ipaddress
import json
import re
import sys

CANDIDATE = {
    'azurerm_mssql_server.database_candidate[0]': 'azurerm_mssql_server',
    'azurerm_mssql_firewall_rule.database_candidate[0]': 'azurerm_mssql_firewall_rule',
    'azapi_resource.sql_candidate[0]': 'azapi_resource',
    'azapi_resource.mongo_candidate[0]': 'azapi_resource',
    'azurerm_mongo_cluster_firewall_rule.database_candidate[0]': 'azurerm_mongo_cluster_firewall_rule',
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
        if kind in ('azurerm_mssql_server', 'azurerm_mongo_cluster'):
            require(after['resource_group_name'] == 'rg-ecommerce-dev' and after['location'] == 'northeurope')
        if kind == 'azurerm_mssql_server':
            require(after['minimum_tls_version'] == '1.2' and after['version'] == '12.0')
            require(after['public_network_access_enabled'] is True)
        if address == 'azapi_resource.sql_candidate[0]':
            require(after['type'] == 'Microsoft.Sql/servers/databases@2023-08-01' and after['name'] == 'products-gate')
            require(after['location'] == 'northeurope')
            sql_free(after['body'])
            require('azurerm_mssql_server.database_candidate' in resources[address.removesuffix('[0]')]['expressions']['parent_id']['references'])
        if address == 'azapi_resource.mongo_candidate[0]':
            require(after['type'] == 'Microsoft.DocumentDB/mongoClusters@2026-06-01' and after['location'] == 'northeurope')
            require(re.fullmatch(r'/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/rg-ecommerce-dev', after['parent_id']))
            p = after['body']['properties']
            require(p['compute']['tier'] == 'Free' and p['storage'] == {'sizeGb': 32, 'type': 'PremiumSSD'})
            require(p['sharding']['shardCount'] == 1 and p['highAvailability']['targetMode'] == 'Disabled')
            require(p['serverVersion'] == '8.0' and p['publicNetworkAccess'] == 'Enabled' and p['createMode'] == 'Default')
            require(p['authConfig']['allowedModes'] == ['NativeAuth'] and 'userName' not in p['administrator'])
        if kind.endswith('firewall_rule'):
            start = ipaddress.IPv4Address(after['start_ip_address'])
            require(start.is_global and after['end_ip_address'] == str(start))
            parent = 'server_id' if kind == 'azurerm_mssql_firewall_rule' else 'mongo_cluster_id'
            target = 'azurerm_mssql_server.database_candidate' if parent == 'server_id' else 'azapi_resource.mongo_candidate'
            require(target in resources[address.removesuffix('[0]')]['expressions'][parent]['references'])
        if change['actions'] != ['no-op']:
            counts[change['actions'][0]] += 1
    require(seen == set(CANDIDATE))
    return counts


if __name__ == '__main__':
    try:
        with open(sys.argv[1]) as file:
            result = validate(json.load(file))
        print(f"D/6 candidate plan verified: {result['create']} creates, {result['update']} updates; Free tiers, one operator IPv4, no app mutations.")
    except Exception:
        raise SystemExit('D/6 plan rejected; inspect raw diagnostics only in a secure session.')
