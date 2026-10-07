"""D/7 scope, Free-tier, exact-IP plan policy and Azure management readback."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


candidate = load('d7_candidate', 'validate-database-candidate.py')
egress = load('d7_egress', 'discover-aca-egress.py')
data_services = load('d8_data_services', 'validate-data-services.py')
business = load('d9_business', 'validate-business-plan.py')
NETWORK = {address: kind for address, kind in candidate.LIVEDOCS.items() if 'module.consumption' in address}
LIVE = 'module.livedocs[0].azurerm_container_app.host'
RULES = {'azurerm_mssql_firewall_rule.aca': 'azurerm_mssql_firewall_rule',
         'azapi_resource.mongo_aca_firewall': 'azapi_resource'}
ENDPOINTS = {'Microsoft.Storage', 'Microsoft.KeyVault'}


def require(condition):
    if not condition:
        raise ValueError('D/7 scope or network configuration rejected')


def boolean_input(value):
    # Saved plans retain primitive TF_VAR/CLI inputs before Terraform's conversion.
    # Never use bool(value): the string "false" is truthy in Python.
    if type(value) is bool:
        return value
    require(type(value) is str and value in ('true', 'false'))
    return value == 'true'


def validate(plan, subscription=None):
    require(not plan.get('errored') and plan.get('complete') is not False)
    variables = {name: item['value'] for name, item in plan['variables'].items()}
    variables['enable_data_services'] = boolean_input(variables.get('enable_data_services', False))
    for name in ('enable_business_runtime', 'enable_business_apps'):
        variables[name] = boolean_input(variables.get(name, False))
    for name in ('enable_database_access', 'enable_database_candidate', 'enable_livedocs', 'enable_shared_environment'):
        variables[name] = boolean_input(variables[name])
    enabled = variables['enable_database_access']
    databases = variables['enable_database_candidate']
    livedocs = variables['enable_livedocs']
    require(variables['enable_shared_environment'] or livedocs)
    require(variables['name_prefix'] == 'ecommerce')
    require(variables['location'] == 'northeurope')
    ips = egress.public_ipv4(variables['database_aca_ipv4']) if enabled else []
    require(not enabled or databases)
    prefix = variables['name_prefix'] + '-dev'
    config = plan['configuration']['root_module']['resources']
    expressions = {item['address']: item.get('expressions', {}) for item in config}
    seen = set()
    seen_rules = {kind: set() for kind in RULES}
    counts = {'create': 0, 'update': 0, 'delete': 0}
    candidate_changes = []
    data_changes = []
    business_changes = []
    for resource in plan.get('resource_changes', []):
        if resource.get('mode') != 'managed':
            continue
        address, kind, change = resource['address'], resource['type'], resource['change']
        require(address not in seen)
        seen.add(address)
        action = change['actions']
        after = change.get('after') or {}
        rule_base = address.split('[', 1)[0]
        if rule_base in RULES:
            require(kind == RULES[rule_base] and action in (['create'], ['update'], ['delete'], ['no-op']))
            ip = json.loads(address[len(rule_base) + 1:-1])
            egress.public_ipv4([ip])
            values = change['before'] if action == ['delete'] else after
            require(values['name'] == 'aca-' + ip.replace('.', '-'))
            parent_resource = 'azurerm_mssql_server.database_candidate' if kind == 'azurerm_mssql_firewall_rule' else 'azapi_resource.mongo_candidate'
            parent_field = 'server_id' if kind == 'azurerm_mssql_firewall_rule' else 'parent_id'
            require(parent_resource in expressions[rule_base][parent_field]['references'])
            parent_name = ('sql-' if kind == 'azurerm_mssql_firewall_rule' else 'mongo-') + prefix + '-d6-' + variables['candidate_suffix']
            if values.get(parent_field):
                parent_type = 'Microsoft.Sql/servers/' if kind == 'azurerm_mssql_firewall_rule' else 'Microsoft.DocumentDB/mongoClusters/'
                require(values[parent_field].lower().endswith('/resourcegroups/rg-ecommerce-dev/providers/' + parent_type.lower() + parent_name))
            if kind == 'azurerm_mssql_firewall_rule':
                require(values['start_ip_address'] == ip and values['end_ip_address'] == ip)
            else:
                require(values['type'] == 'Microsoft.DocumentDB/mongoClusters/firewallRules@2026-06-01')
                require(values['body']['properties'] == {'startIpAddress': ip, 'endIpAddress': ip})
            if action == ['delete']:
                require(ip not in ips)
            else:
                require(ip in ips)
                seen_rules[rule_base].add(ip)
        elif business.belongs(address):
            require(variables['enable_business_runtime'])
            business_changes.append(resource)
        elif address in data_services.ADDRESSES:
            require(variables['enable_data_services'])
            data_changes.append(resource)
        elif address in candidate.CANDIDATE:
            require(databases)
            candidate_changes.append(resource)
            require(action in (['create'], ['update'], ['no-op']))
        elif address in NETWORK or address == LIVE:
            require((NETWORK.get(address) or candidate.LIVEDOCS.get(address)) == kind)
            require(action in (['create'], ['update'], ['no-op']))
            require(after['resource_group_name'] == 'rg-ecommerce-dev')
            if address == LIVE:
                require(livedocs)
                policy = load('d7_livedocs', 'validate-livedocs-plan.py')
                if after.get('container_app_environment_id'):
                    require(after['container_app_environment_id'].lower().endswith('/resourcegroups/rg-ecommerce-dev/providers/microsoft.app/managedenvironments/cae-' + prefix))
                # Reuse D/4 allocation/HTTPS restrictions with its complete four-resource set below.
            elif kind == 'azurerm_virtual_network':
                require(after['name'] == 'vnet-' + prefix and after['location'] == 'northeurope')
                require(after['address_space'] == ['10.42.0.0/16'])
            elif kind == 'azurerm_subnet':
                require(after['name'] == 'aca' and after['virtual_network_name'] == 'vnet-' + prefix)
                endpoints = after['service_endpoint']
                require(after['address_prefixes'] == ['10.42.0.0/23'] and len(endpoints) == 2)
                require({item['service'] for item in endpoints} == ENDPOINTS and all(item.get('network_identifier') in (None, '') for item in endpoints))
                delegation = after['delegation']
                require(len(delegation) == 1 and delegation[0]['service_delegation'][0]['name'] == 'Microsoft.App/environments')
            else:
                require(after['name'] == 'cae-' + prefix and after['location'] == 'northeurope')
                require(after['infrastructure_resource_group_name'] == 'rg-' + prefix + '-aca-managed')
                profiles = after['workload_profile']
                require(len(profiles) == 1 and profiles[0]['name'] == 'Consumption' and profiles[0]['workload_profile_type'] == 'Consumption')
                require(profiles[0].get('maximum_count') in (None, 0) and profiles[0].get('minimum_count') in (None, 0))
                # AzureRM's disabled destination defaults to ""; mock plans may use null.
                require(after.get('logs_destination') in (None, '') and after.get('log_analytics_workspace_id') in (None, ''))
                require(after['internal_load_balancer_enabled'] is False and after['public_network_access'] == 'Enabled' and after['zone_redundancy_enabled'] is False)
        else:
            require(False)
        if action != ['no-op']:
            counts[action[0]] += 1
    require(set(NETWORK).issubset(seen))
    require((LIVE in seen) == livedocs)
    require(all(values == set(ips) for values in seen_rules.values()))
    if variables['enable_data_services']:
        data_services.validate(plan, data_changes, subscription)
    if variables['enable_business_runtime']:
        require(variables['enable_shared_environment'] and livedocs and databases and variables['enable_data_services'])
        require(not variables['enable_business_apps'] or enabled)
        business.validate(plan, business_changes, subscription)
        variables['discovery_apps'] = ['ca-ecommerce-dev-livedocs'] + [
            r['change']['after']['name'] for r in business_changes
            if r['type'] == 'azurerm_container_app' and r['change']['actions'] != ['create']]
        variables['discovery_jobs'] = [
            r['change']['after']['name'] for r in business_changes
            if r['type'] == 'azurerm_container_app_job' and r['change']['actions'] != ['create']]
    if databases:
        candidate.validate({**plan, 'resource_changes': candidate_changes}, public_access_enabled=enabled)
        resources = {item['address']: item['change']['after'] for item in candidate_changes}
        require(resources['azurerm_mssql_server.database_candidate[0]']['name'] == 'sql-' + prefix + '-d6-' + variables['candidate_suffix'])
        require(resources['azapi_resource.mongo_candidate[0]']['name'] == 'mongo-' + prefix + '-d6-' + variables['candidate_suffix'])
    if livedocs:
        policy.validate({**plan, 'resource_changes': [item for item in plan['resource_changes'] if item['address'] in candidate.LIVEDOCS]})
        live_resource = next(item for item in plan['resource_changes'] if item['address'] == LIVE)
        release = json.loads((ROOT.parent / 'releases/livedocs.json').read_text())
        require(live_resource['change']['after']['template'][0]['container'][0]['image'] == release['image'])
    return counts, variables


def verify_egress(variables, subscription):
    if variables['enable_database_access']:
        # D/7 reuses LiveDocs; D/9 extends discovery to all deployed business apps.
        require(variables['enable_livedocs'])
        prefix = variables['name_prefix'] + '-dev'
        if variables.get('enable_business_runtime', False):
            observed = egress.discover(subscription, 'cae-' + prefix, variables['discovery_apps'], variables['discovery_jobs'])
        else:
            observed = egress.discover(subscription, 'cae-' + prefix, ['ca-' + prefix + '-livedocs'])
        require(observed == egress.public_ipv4(variables['database_aca_ipv4']))


def readback(names, subscription):
    require(names['database_access_enabled'] is True)
    ips = egress.public_ipv4(names['aca_ipv4'])
    if names.get('discovery_jobs'):
        observed = egress.discover(subscription, names['environment_name'], names['discovery_apps'], names['discovery_jobs'])
    else:
        observed = egress.discover(subscription, names['environment_name'], [names['discovery_app']])
    require(observed == ips)
    candidate.readback(names['candidate'], subscription, public_access_enabled=True)
    base = f'/subscriptions/{subscription}/resourceGroups/rg-ecommerce-dev/providers/'
    sql = egress.arm_get(base + 'Microsoft.Sql/servers/' + names['candidate']['sql_server'] + '/firewallRules', '2023-08-01')
    mongo = egress.arm_get(base + 'Microsoft.DocumentDB/mongoClusters/' + names['candidate']['mongo_cluster'] + '/firewallRules', '2026-06-01')
    expected = {('aca-' + ip.replace('.', '-'), ip, ip) for ip in ips}
    for response in (sql, mongo):
        actual = [(item['name'], item['properties']['startIpAddress'], item['properties']['endIpAddress']) for item in response['value']]
        require(len(actual) == len(expected) and set(actual) == expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json_file', type=Path)
    parser.add_argument('--verify-egress', metavar='SUBSCRIPTION')
    parser.add_argument('--readback', metavar='SUBSCRIPTION')
    parser.add_argument('--data-readback', metavar='SUBSCRIPTION')
    args = parser.parse_args()
    try:
        payload = json.loads(args.json_file.read_text(encoding='utf-8'))
        if args.data_readback:
            require(not args.verify_egress and not args.readback)
            data_services.readback(payload, args.data_readback, egress.arm_get)
            print('D/8 ARM readback verified: Standard LRS private containers, Entra-only access, subnet ACLs and Standard RBAC vault. Runtime access remains D/9/D/12.')
        elif args.readback:
            require(not args.verify_egress)
            readback(payload, args.readback)
            print('D/7 ARM readback verified: Free databases, exact ACA IPv4 firewall rules. Live connectivity and D/9 driver compatibility remain separate checks.')
        else:
            counts, variables = validate(payload, subscription=args.verify_egress)
            require(not variables['enable_database_access'] or args.verify_egress)
            if args.verify_egress:
                verify_egress(variables, args.verify_egress)
            print(f"Reviewed D/7 plan: {counts['create']} creates, {counts['update']} updates, {counts['delete']} obsolete firewall deletes; no replacements or paid fallback.")
    except Exception as error:
        # Report source locations only: exception messages and plan values can contain secrets.
        for frame in traceback.extract_tb(error.__traceback__):
            filename = Path(frame.filename).name
            if filename in ('validate-network-plan.py', 'validate-database-candidate.py', 'validate-livedocs-plan.py', 'discover-aca-egress.py', 'validate-data-services.py', 'validate-business-plan.py'):
                print(f'{filename}:{frame.lineno}: D/7 verification diagnostic', file=sys.stderr)
        raise SystemExit('D/7 verification failed; inspect private plan/Azure diagnostics. No apply was performed by this checker.')
