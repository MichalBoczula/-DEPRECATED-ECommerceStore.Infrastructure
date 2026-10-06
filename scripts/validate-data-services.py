"""D/8 disposable file/secret infrastructure scope and management readback."""
import hashlib
import re

ADDRESSES = {
    'module.data_services[0].azurerm_storage_account.business': 'azurerm_storage_account',
    'module.data_services[0].azurerm_storage_container.files["invoices"]': 'azurerm_storage_container',
    'module.data_services[0].azurerm_storage_container.files["photos"]': 'azurerm_storage_container',
    'module.data_services[0].azurerm_key_vault.business': 'azurerm_key_vault',
}
SECRET_NAMES = {
    'products_connection': 'products-sql-connection', 'users_connection': 'users-mongo-connection',
    'invoice_connection': 'invoice-mongo-connection', 'payments_connection': 'payments-mongo-connection',
    'stripe_key': 'stripe-secret-key', 'stripe_webhook': 'stripe-webhook-secret',
}
MONGO_DATABASES = {'users': 'ecommerce-store-users-db', 'invoice': 'ecommerce-store-invoice-db', 'payments': 'ecommerce_store_payments'}


def require(condition):
    if not condition:
        raise ValueError('D/8 file or secret infrastructure rejected')


def names(subscription):
    require(isinstance(subscription, str) and re.fullmatch(r'[0-9a-f-]{36}', subscription))
    token = hashlib.sha256((subscription + '/rg-ecommerce-dev').encode()).hexdigest()
    root = f'/subscriptions/{subscription}/resourceGroups/rg-ecommerce-dev/providers/'
    return dict(storage='stecommercedev' + token[:10], vault='kv-ecom-dev-' + token[:12], root=root,
                subnet=root + 'Microsoft.Network/virtualNetworks/vnet-ecommerce-dev/subnets/aca')


def validate(plan, changes, subscription):
    expected = names(subscription)
    call = plan['configuration']['root_module']['module_calls']['data_services']
    require('module.consumption[0].subnet_id' in call['expressions']['subnet_id']['references'])
    require('data.azurerm_client_config.data_services[0].tenant_id' in call['expressions']['tenant_id']['references'])
    config = {item['address']: item for item in call['module']['resources']}
    require('azurerm_storage_account.business' in config['azurerm_storage_container.files']['expressions']['storage_account_id']['references'])
    seen = set()
    for item in changes:
        address, kind, change = item['address'], item['type'], item['change']
        require(ADDRESSES.get(address) == kind and address not in seen)
        seen.add(address)
        require(change['actions'] in (['create'], ['update'], ['no-op']))
        after = change['after']
        if kind == 'azurerm_storage_container':
            container = 'invoices' if address.endswith('["invoices"]') else 'photos'
            require(after['name'] == container and after['container_access_type'] == 'private')
            if after.get('storage_account_id'):
                require(after['storage_account_id'].lower() == (expected['root'] + 'Microsoft.Storage/storageAccounts/' + expected['storage']).lower())
            continue
        require(after['resource_group_name'] == 'rg-ecommerce-dev' and after['location'] == 'northeurope')
        if kind == 'azurerm_storage_account':
            require(after['name'] == expected['storage'] and after['account_kind'] == 'StorageV2')
            require(after['account_tier'] == 'Standard' and after['account_replication_type'] == 'LRS' and after['access_tier'] == 'Hot')
            require(after['shared_access_key_enabled'] is False and after['allow_nested_items_to_be_public'] is False)
            require(after['default_to_oauth_authentication'] is True and after['https_traffic_only_enabled'] is True)
            require(after['min_tls_version'] == 'TLS1_2' and after['public_network_access'] == 'Enabled')
            acl = after['network_rules'][0]
            require(len(after['network_rules']) == 1 and acl['bypass'] == ['None'])
            blob = after['blob_properties'][0]
            require(len(after['blob_properties']) == 1 and blob['versioning_enabled'] is False)
            require(not blob.get('delete_retention_policy') and not blob.get('container_delete_retention_policy') and not blob.get('restore_policy'))
        else:
            require(after['name'] == expected['vault'] and after['sku_name'] == 'standard')
            require(after['rbac_authorization_enabled'] is True and after['public_network_access_enabled'] is True)
            require(after['purge_protection_enabled'] is False and after['soft_delete_retention_days'] == 7)
            require(all(after[field] is False for field in ('enabled_for_deployment', 'enabled_for_disk_encryption', 'enabled_for_template_deployment')))
            require(not after.get('access_policy') and re.fullmatch(r'[0-9a-f-]{36}', after['tenant_id']))
            acl = after['network_acls'][0]
            require(len(after['network_acls']) == 1 and acl['bypass'] == 'None')
        require(acl['default_action'] == 'Deny' and acl['ip_rules'] == [])
        # The one subnet ID may still be unknown on the first create. Its source
        # reference is verified above; known readback must match the exact subnet.
        ids = acl.get('virtual_network_subnet_ids')
        require(ids is None or (len(ids) == 1 and (ids[0] is None or ids[0].lower() == expected['subnet'].lower())))
    require(seen == set(ADDRESSES))


def readback(metadata, subscription, arm_get):
    expected = names(subscription)
    storage_id = expected['root'] + 'Microsoft.Storage/storageAccounts/' + expected['storage']
    vault_id = expected['root'] + 'Microsoft.KeyVault/vaults/' + expected['vault']
    require(metadata['storage_account_id'].lower() == storage_id.lower() and metadata['key_vault_id'].lower() == vault_id.lower())
    require(metadata['subnet_id'].lower() == expected['subnet'].lower())
    require(metadata['mongo_databases'] == MONGO_DATABASES and metadata['secret_names'] == SECRET_NAMES)
    storage = arm_get(storage_id, '2025-06-01')
    require(storage['sku']['name'] == 'Standard_LRS' and storage['kind'] == 'StorageV2')
    p = storage['properties']
    require(p['allowBlobPublicAccess'] is False and p['allowSharedKeyAccess'] is False)
    require(p['defaultToOAuthAuthentication'] is True and p['supportsHttpsTrafficOnly'] is True and p['minimumTlsVersion'] == 'TLS1_2')
    require(p['publicNetworkAccess'] == 'Enabled')
    vault = arm_get(vault_id, '2023-07-01')
    v = vault['properties']
    require(v['sku']['name'].lower() == 'standard' and v['enableRbacAuthorization'] is True)
    require(v.get('enablePurgeProtection', False) is False and v['softDeleteRetentionInDays'] == 7)
    require(v.get('publicNetworkAccess', 'Enabled') == 'Enabled' and not v.get('accessPolicies'))
    require(all(v.get(field, False) is False for field in ('enabledForDeployment', 'enabledForDiskEncryption', 'enabledForTemplateDeployment')))
    for resource in (storage, vault):
        require(resource['location'].replace(' ', '').lower() == 'northeurope')
        acl = resource['properties']['networkAcls']
        require(acl['defaultAction'] == 'Deny' and acl['bypass'] == 'None' and not acl.get('ipRules'))
        require([item['id'].lower() for item in acl['virtualNetworkRules']] == [expected['subnet'].lower()])
    blob = arm_get(storage_id + '/blobServices/default', '2025-06-01')['properties']
    require(blob.get('isVersioningEnabled', False) is False)
    require(all(blob.get(key, {}).get('enabled', False) is False for key in ('deleteRetentionPolicy', 'containerDeleteRetentionPolicy', 'restorePolicy')))
    for container in ('invoices', 'photos'):
        response = arm_get(storage_id + '/blobServices/default/containers/' + container, '2025-06-01')
        require(response['properties'].get('publicAccess', 'None') == 'None')
