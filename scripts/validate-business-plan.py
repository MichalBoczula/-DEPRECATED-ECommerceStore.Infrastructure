"""D/9 fixed app/identity/job scope; reject broad grants, raw secrets and mutable images."""
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APPS = {'products', 'users', 'invoice', 'payments', 'bff'}
ALLOCATIONS = {key: (1.0, '2Gi') if key == 'invoice' else (0.25, '0.5Gi') for key in APPS}
SECRETS = {'products': 'products-sql-connection', 'users': 'users-mongo-connection',
           'invoice': 'invoice-mongo-connection', 'payments': 'payments-mongo-connection'}
SECRET_ENV = {'products': 'ConnectionStrings__ProductCatalogDb', 'users': 'MongoDbSettings__ConnectionString',
              'invoice': 'MongoDbSettings__ConnectionString', 'payments': 'PAYMENTS_MONGODB_CONNECTION_STRING'}
BASES = {'azurerm_user_assigned_identity.business': 'azurerm_user_assigned_identity',
         'azurerm_role_assignment.business_secret': 'azurerm_role_assignment',
         'azurerm_role_assignment.business_blob': 'azurerm_role_assignment',
         'azurerm_container_app.business': 'azurerm_container_app',
         'azurerm_container_app_job.database_gate': 'azurerm_container_app_job',
         'azurerm_container_app_job.invoice_probe': 'azurerm_container_app_job'}


def require(value):
    if not value:
        raise ValueError('D/9 runtime policy rejected configuration')


def belongs(address):
    return address.split('[', 1)[0] in BASES


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plain_env(key, urls):
    dotnet = {} if key == 'payments' else dict(ASPNETCORE_URLS='http://+:8080', ASPNETCORE_ENVIRONMENT='Production', ASPNETCORE_FORWARDEDHEADERS_ENABLED='true')
    values = {
        'products': {'Database__ApplyMigrations': 'false'},
        'users': {'MongoDbSettings__DatabaseName': 'ecommerce-store-users-db'},
        'invoice': {'MongoDbSettings__DatabaseName': 'ecommerce-store-invoice-db', 'ExternalServices__ProductCatalog__BaseUrl': urls['products'] + '/' if urls['products'] else None},
        'payments': {'PAYMENTS_ENVIRONMENT': 'development', 'PAYMENTS_MONGODB_DATABASE_NAME': 'ecommerce_store_payments',
                     'PAYMENTS_ORDERS_API_BASE_URL': urls['invoice'] + '/' if urls['invoice'] else None, 'PAYMENTS_STRIPE_ENABLED': 'false'},
        'bff': {'GatewaySettings__BaseUrl': urls['bff'], **{
            'ReverseProxy__Clusters__' + cluster + '__Destinations__destination1__Address': urls[app] + '/' if urls[app] else None
            for cluster, app in [('products-cluster', 'products'), ('users-cluster', 'users'), ('orders-cluster', 'invoice'), ('payments-cluster', 'payments')]}}
    }
    return {**dotnet, **values[key]}


def invoice_command():
    # Match Terraform file() exactly, including CRLF in Windows checkouts.
    script = (ROOT / 'verification/database-gate/invoice-probe.ps1').read_bytes().decode('utf-8')
    return ['pwsh', '-NoProfile', '-Command', script]


def validate(plan, changes, subscription):
    require(re.fullmatch(r'[0-9a-fA-F-]{36}', subscription or ''))
    vars = {key: value['value'] for key, value in plan['variables'].items()}
    apps_enabled = vars['enable_business_apps'] in (True, 'true')
    image = vars['database_gate_image']
    require(re.fullmatch(r'mb0101/ecommerce-store-database-gate@sha256:[a-f0-9]{64}', image))
    release = json.loads((ROOT / 'releases/development.json').read_text())
    names = load('d9_data', 'validate-data-services.py').names(subscription)
    vault_id = names['root'] + 'Microsoft.KeyVault/vaults/' + names['vault']
    vault_uri = 'https://' + names['vault'] + '.vault.azure.net/secrets/'
    environment = names['root'] + 'Microsoft.App/managedEnvironments/cae-ecommerce-dev'
    parent = next(r for r in plan['resource_changes'] if r['address'] == 'module.consumption[0].azurerm_container_app_environment.host')
    domain = parent['change']['after'].get('default_domain')
    if domain:
        require(re.fullmatch(r'[a-z0-9-]+\.northeurope\.azurecontainerapps\.io', domain))
    urls = {key: 'https://ca-ecommerce-dev-' + key + ('' if key == 'bff' else '.internal') + '.' + domain if domain else None for key in APPS}
    # Terraform omits expressions for data sources with no arguments, such as
    # azurerm_client_config. Required runtime references remain checked by refs.
    config = {r['address']: r.get('expressions', {}) for r in plan['configuration']['root_module']['resources']}
    resources = {r['address']: r for r in changes}
    expected = {'azurerm_user_assigned_identity.business["' + key + '"]' for key in APPS | {'gate'}}
    expected |= {'azurerm_role_assignment.business_secret["' + key + '"]' for key in set(SECRETS) | {'gate_sql', 'gate_mongo'}}
    expected |= {'azurerm_role_assignment.business_blob["' + key + '"]' for key in ('products', 'invoice')}
    expected |= {'azurerm_container_app_job.database_gate[0]', 'azurerm_container_app_job.invoice_probe[0]'}
    if apps_enabled:
        expected |= {'azurerm_container_app.business["' + key + '"]' for key in APPS}
    require(set(resources) == expected and len(resources) == len(changes))

    def refs(base, field, required):
        actual = config[base][field].get('references', [])
        require(any(value == required or value.startswith(required + '[') or value.startswith(required + '.') for value in actual))

    def known_or_unknown(resource, field, expected_value):
        value = resource['change']['after'].get(field)
        if value is None:
            require(resource['change'].get('after_unknown', {}).get(field) is True)
        else:
            require(value == expected_value)

    def nested_unknown(resource, *path):
        value = resource['change'].get('after_unknown', {})
        for item in path:
            if value is True:
                return True
            try:
                value = value[item]
            except (KeyError, IndexError, TypeError):
                return False
        return value is True

    for address, resource in resources.items():
        base = address.split('[', 1)[0]
        require(resource['type'] == BASES[base])
        require(resource['change']['actions'] in (['create'], ['update'], ['no-op']))
        after = resource['change']['after']
        key = json.loads(address[len(base) + 1:-1])
        if resource['type'] != 'azurerm_role_assignment':
            require(after['resource_group_name'] == 'rg-ecommerce-dev')
        if resource['type'] == 'azurerm_user_assigned_identity':
            require(after['name'] == 'id-ecommerce-dev-' + key and after['location'] == 'northeurope')
            continue
        if resource['type'] == 'azurerm_role_assignment':
            require(after['principal_type'] == 'ServicePrincipal' and after['skip_service_principal_aad_check'] is True)
            require(after.get('condition') in (None, '') and after.get('delegated_managed_identity_resource_id') in (None, ''))
            refs(base, 'principal_id', 'azurerm_user_assigned_identity.business')
            refs(base, 'scope', 'module.data_services')
            if base.endswith('business_secret'):
                app = 'gate' if key.startswith('gate_') else key
                secret = SECRETS['products' if key == 'gate_sql' else 'users' if key == 'gate_mongo' else key]
                scope = vault_id + '/secrets/' + secret
                require(after['role_definition_name'] == 'Key Vault Secrets User')
            else:
                app = key
                scope = names['root'] + 'Microsoft.Storage/storageAccounts/' + names['storage'] + '/blobServices/default/containers/' + ('photos' if key == 'products' else 'invoices')
                require(after['role_definition_name'] == 'Storage Blob Data Contributor')
            known_or_unknown(resource, 'scope', scope)
            principal = resources['azurerm_user_assigned_identity.business["' + app + '"]']['change']['after'].get('principal_id')
            known_or_unknown(resource, 'principal_id', principal)
            continue
        refs(base, 'container_app_environment_id', 'module.consumption')
        known_or_unknown(resource, 'container_app_environment_id', environment)
        require(after['workload_profile_name'] == 'Consumption' and not after.get('registry'))
        template = after['template'][0]
        require(not template.get('init_container') and not template.get('volume') and len(template['container']) == 1)
        container = template['container'][0]
        require(not container.get('volume_mounts'))
        env = {e['name']: e for e in container.get('env', [])}
        require(len(env) == len(container.get('env', [])))
        secret = {s['name']: s for s in after.get('secret', [])}
        require(len(secret) == len(after.get('secret', [])))
        identity = after.get('identity', [])
        if resource['type'] == 'azurerm_container_app':
            require(after['name'] == 'ca-ecommerce-dev-' + key and after['revision_mode'] == 'Single' and after['max_inactive_revisions'] == 2)
            require(len(after['ingress']) == 1)
            ingress = after['ingress'][0]
            require(ingress['external_enabled'] is (key == 'bff') and ingress['allow_insecure_connections'] is False)
            require(ingress['target_port'] == 8080 and ingress['transport'] == 'http')
            require(ingress['traffic_weight'][0]['latest_revision'] is True and ingress['traffic_weight'][0]['percentage'] == 100)
            require(template['min_replicas'] == 0 and template['max_replicas'] == 1)
            require(template['http_scale_rule'][0]['name'] == 'http' and str(template['http_scale_rule'][0]['concurrent_requests']) == '10')
            require(not template.get('custom_scale_rule') and not template.get('tcp_scale_rule') and not template.get('azure_queue_scale_rule'))
            require((container['cpu'], container['memory']) == ALLOCATIONS[key] and container['image'] == release['applications'][key]['image'])
            require(not container.get('command') and not container.get('args'))
            for probe, contract, interval, timeout, failures in [('startup_probe', 'startup', 5, 5, 120), ('liveness_probe', 'liveness', 10, 5, 3), ('readiness_probe', 'readiness', 10, 10, 3)]:
                value = container[probe][0]
                require(value['path'] == release['applications'][key]['runtime'][contract] and value['port'] == 8080 and value['transport'] == 'HTTP')
                require(value['interval_seconds'] == interval and value['timeout'] == timeout and value['failure_count_threshold'] == failures and not value.get('header'))
            plain = plain_env(key, urls)
            require(set(env) == set(plain) | {'AZURE_CLIENT_ID'} | ({SECRET_ENV[key]} if key != 'bff' else set()))
            for name, value in plain.items():
                require(not env[name].get('secret_name') and env[name].get('value') == value)
                if value is None:
                    index = next(i for i, item in enumerate(container['env']) if item['name'] == name)
                    require(nested_unknown(resource, 'template', 0, 'container', 0, 'env', index, 'value'))
            client = resources['azurerm_user_assigned_identity.business["' + key + '"]']['change']['after'].get('client_id')
            require(env['AZURE_CLIENT_ID'].get('value') == client and not env['AZURE_CLIENT_ID'].get('secret_name'))
            if client is None:
                index = next(i for i, item in enumerate(container['env']) if item['name'] == 'AZURE_CLIENT_ID')
                require(nested_unknown(resource, 'template', 0, 'container', 0, 'env', index, 'value'))
            if key != 'bff':
                require(env[SECRET_ENV[key]].get('secret_name') == 'connection' and env[SECRET_ENV[key]].get('value') in (None, ''))
            require(set(secret) == ({'connection'} if key != 'bff' else set()))
            app_identity = 'id-ecommerce-dev-' + key
        else:
            require(after['location'] == 'northeurope' and after['replica_retry_limit'] == 0)
            require(after.get('manual_trigger_config') == [{'parallelism': 1, 'replica_completion_count': 1}])
            require(not after.get('schedule_trigger_config') and not after.get('event_trigger_config'))
            if base.endswith('database_gate'):
                require(after['name'] == 'job-ecommerce-dev-database-gate' and after['replica_timeout_in_seconds'] == 1800)
                require(container['image'] == image and (container['cpu'], container['memory']) == (1.0, '2Gi'))
                require(not container.get('command') and not container.get('args') and set(secret) == {'sql', 'mongo'})
                require(set(env) == {'D6_SQL_CONNECTION_STRING', 'D6_MONGO_CONNECTION_STRING', 'D6_SQL_HOST', 'D6_MONGO_HOST', 'D9_MODE', 'D9_APPS', 'D9_RUN_ID'})
                for name, ref in [('D6_SQL_CONNECTION_STRING', 'sql'), ('D6_MONGO_CONNECTION_STRING', 'mongo')]:
                    require(env[name].get('secret_name') == ref and env[name].get('value') in (None, ''))
                require(env['D9_MODE']['value'] == 'database' and env['D9_RUN_ID']['value'] == 'manual-unbound')
                require(env['D6_MONGO_HOST']['value'] == 'mongo-ecommerce-dev-d6-' + vars['candidate_suffix'] + '.mongocluster.cosmos.azure.com')
                sql_host = env['D6_SQL_HOST'].get('value')
                require(sql_host in (None, 'sql-ecommerce-dev-d6-' + vars['candidate_suffix'] + '.database.windows.net'))
                if sql_host is None:
                    index = next(i for i, item in enumerate(container['env']) if item['name'] == 'D6_SQL_HOST')
                    require(nested_unknown(resource, 'template', 0, 'container', 0, 'env', index, 'value'))
                if domain:
                    require(json.loads(env['D9_APPS']['value']) == urls)
                else:
                    require(env['D9_APPS'].get('value') is None)
                    index = next(i for i, item in enumerate(container['env']) if item['name'] == 'D9_APPS')
                    require(nested_unknown(resource, 'template', 0, 'container', 0, 'env', index, 'value'))
                app_identity = 'id-ecommerce-dev-gate'
            else:
                require(after['name'] == 'job-ecommerce-dev-invoice-probe' and after['replica_timeout_in_seconds'] == 300)
                require(container['image'] == release['applications']['invoice']['image'] and (container['cpu'], container['memory']) == ALLOCATIONS['invoice'])
                require(container['command'] == invoice_command())
                require(not container.get('args') and not secret and not identity and set(env) == {'D9_RUN_ID'})
                require(env['D9_RUN_ID']['value'] == 'manual-unbound')
                continue
        require(len(identity) == 1 and identity[0]['type'] == 'UserAssigned')
        expected_identity = names['root'] + 'Microsoft.ManagedIdentity/userAssignedIdentities/' + app_identity
        ids = identity[0].get('identity_ids')
        require(ids == [expected_identity]
                or (ids is None and nested_unknown(resource, 'identity', 0, 'identity_ids'))
                or (ids == [None] and nested_unknown(resource, 'identity', 0, 'identity_ids', 0)))
        refs(base, 'identity', 'azurerm_user_assigned_identity.business') if 'identity' in config[base] and isinstance(config[base]['identity'], dict) else None
        if resource['type'] == 'azurerm_container_app':
            expected_secrets = {'connection': SECRETS[key]} if key != 'bff' else {}
        else:
            expected_secrets = {'sql': SECRETS['products'], 'mongo': SECRETS['users']}
        for name, secret_name in expected_secrets.items():
            require(secret[name].get('value') in (None, ''))
            index = next(i for i, item in enumerate(after['secret']) if item['name'] == name)
            for field, expected_value in [('key_vault_secret_id', vault_uri + secret_name), ('identity', expected_identity)]:
                value = secret[name].get(field)
                require(value == expected_value or (value is None and nested_unknown(resource, 'secret', index, field)))
    return urls
