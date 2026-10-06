"""Exercise exact-ACA ACLs, staged rollout and fail-closed egress discovery."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_database_candidate

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('network_policy', ROOT / 'scripts/validate-network-plan.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
SUBSCRIPTION = '11111111-1111-1111-1111-111111111111'
ENVIRONMENT = f'/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-ecommerce-dev/providers/Microsoft.App/managedEnvironments/cae-ecommerce-dev'


def plan(access=True, databases=True, docs=True):
    value = test_database_candidate.plan()
    value['variables'].update({k: {'value': v} for k, v in dict(
        enable_database_access=access, enable_database_candidate=databases, enable_livedocs=docs,
        enable_shared_environment=True, database_aca_ipv4=['20.40.60.80'] if access else [],
        name_prefix='ecommerce', location='northeurope', candidate_suffix='reviewd7').items()})
    changes = value['resource_changes'] if databases else []
    if databases:
        changes[0]['change']['after'].update(name='sql-ecommerce-dev-d6-reviewd7', public_network_access_enabled=access)
        changes[2]['change']['after']['name'] = 'mongo-ecommerce-dev-d6-reviewd7'
        changes[2]['change']['after']['body']['properties']['publicNetworkAccess'] = 'Enabled' if access else 'Disabled'
    values = [dict(name='vnet-ecommerce-dev', location='northeurope', address_space=['10.42.0.0/16']),
        dict(name='aca', virtual_network_name='vnet-ecommerce-dev', address_prefixes=['10.42.0.0/23'],
             service_endpoint=[{'service':'Microsoft.Storage'},{'service':'Microsoft.KeyVault'}], delegation=[{'service_delegation':[{'name':'Microsoft.App/environments'}]}]),
        dict(name='cae-ecommerce-dev', location='northeurope', infrastructure_resource_group_name='rg-ecommerce-dev-aca-managed',
             workload_profile=[dict(name='Consumption',workload_profile_type='Consumption')], logs_destination=None,
             internal_load_balancer_enabled=False,public_network_access='Enabled',zone_redundancy_enabled=False)]
    for (address, kind), after in zip(policy.NETWORK.items(), values):
        changes.append(dict(address=address,type=kind,mode='managed',change=dict(actions=['create'],after=dict(resource_group_name='rg-ecommerce-dev',**after))))
    if docs:
        after=dict(resource_group_name='rg-ecommerce-dev',container_app_environment_id=ENVIRONMENT,workload_profile_name='Consumption',revision_mode='Single',
            ingress=[dict(allow_insecure_connections=False,external_enabled=True,target_port=8080)],
            template=[dict(min_replicas=0,max_replicas=1,container=[dict(cpu=0.25,memory='0.5Gi',image=json.loads((ROOT/'releases/livedocs.json').read_text())['image'])])])
        changes.append(dict(address=policy.LIVE,type='azurerm_container_app',mode='managed',change=dict(actions=['create'],after=after)))
    for base, kind in policy.RULES.items():
        parent='azurerm_mssql_server.database_candidate' if kind=='azurerm_mssql_firewall_rule' else 'azapi_resource.mongo_candidate'
        field='server_id' if kind=='azurerm_mssql_firewall_rule' else 'parent_id'
        value['configuration']['root_module']['resources'].append(dict(address=base,expressions={field:{'references':[parent]}}))
        if access:
            after=dict(name='aca-20-40-60-80')
            if kind=='azurerm_mssql_firewall_rule': after.update(start_ip_address='20.40.60.80',end_ip_address='20.40.60.80')
            else: after.update(type='Microsoft.DocumentDB/mongoClusters/firewallRules@2026-06-01',body={'properties':{'startIpAddress':'20.40.60.80','endIpAddress':'20.40.60.80'}})
            changes.append(dict(address=base+'["20.40.60.80"]',type=kind,mode='managed',change=dict(actions=['create'],after=after)))
    value['resource_changes']=changes
    return value


class NetworkPolicyTests(unittest.TestCase):
    def test_terraform_renderer_without_variables_or_configuration(self):
        checker = policy.load('network_mock_checker', 'check-network-test-plans.py')
        for name, p in [('shared_environment_without_docs', plan(False, False, False)),
                        ('livedocs_uses_shared_environment', plan(False, False, True)),
                        ('aca_database_access', plan())]:
            if name == 'aca_database_access':
                for item in p['resource_changes'][:2]:
                    item['change']['after']['location'] = 'francecentral'
                for original in list(p['resource_changes'][-2:]):
                    item = copy.deepcopy(original)
                    item['address'] = item['address'].replace('20.40.60.80', '20.40.60.81')
                    after = item['change']['after']
                    after['name'] = 'aca-20-40-60-81'
                    if item['type'] == 'azurerm_mssql_firewall_rule':
                        after.update(start_ip_address='20.40.60.81', end_ip_address='20.40.60.81')
                    else:
                        after['body']['properties'].update(startIpAddress='20.40.60.81', endIpAddress='20.40.60.81')
                    p['resource_changes'].append(item)
            rendered = {'resource_changes': p['resource_changes']}
            with self.subTest(name=name):
                self.assertGreater(policy.validate({**rendered, **checker.envelope(name)})[0]['create'], 0)
                # The real saved-plan checker still requires the complete envelope.
                with self.assertRaises(KeyError): policy.validate(rendered)

    def test_staged_environment_and_exact_ip_access(self):
        self.assertEqual(policy.validate(plan(False,False,False))[0],dict(create=3,update=0,delete=0))
        self.assertEqual(policy.validate(plan(False,False,True))[0],dict(create=4,update=0,delete=0))
        self.assertEqual(policy.validate(plan())[0],dict(create=9,update=0,delete=0))

    def test_only_obsolete_firewall_deletion_allowed(self):
        p=plan()
        item=copy.deepcopy(p['resource_changes'][-1])
        item['address']=item['address'].replace('20.40.60.80','20.40.60.81')
        before=item['change']['after'];before['name']='aca-20-40-60-81'
        before['body']['properties']={'startIpAddress':'20.40.60.81','endIpAddress':'20.40.60.81'}
        item['change']=dict(actions=['delete'],before=before,after=None)
        p['resource_changes'].append(item)
        self.assertEqual(policy.validate(p)[0]['delete'],1)
        p['resource_changes'][0]['change']['actions']=['delete']
        with self.assertRaises(ValueError): policy.validate(p)

    def test_broad_rules_paid_tiers_replacement_unknown_and_wrong_parent_rejected(self):
        for mutation in ('broad','paid','replace','extra','parent','endpoint','replicas','image','wrongenvironment'):
            p=plan(); resources={x['address']:x for x in p['resource_changes']}
            if mutation=='broad': p['resource_changes'][-1]['change']['after']['body']['properties']['endIpAddress']='255.255.255.255'
            if mutation=='paid': p['resource_changes'][2]['change']['after']['body']['properties']['compute']['tier']='M10'
            if mutation=='replace': p['resource_changes'][0]['change']['actions']=['delete','create']
            if mutation=='extra': p['resource_changes'].append(dict(address='azurerm_nat_gateway.extra',type='azurerm_nat_gateway',mode='managed',change=dict(actions=['create'],after={})))
            if mutation=='parent': p['configuration']['root_module']['resources'][-1]['expressions']['parent_id']['references']=['azapi_resource.other']
            if mutation=='endpoint': resources['module.consumption[0].azurerm_subnet.host']['change']['after']['service_endpoint'].append({'service':'Microsoft.Sql'})
            if mutation=='replicas': resources[policy.LIVE]['change']['after']['template'][0]['min_replicas']=1
            if mutation=='image': resources[policy.LIVE]['change']['after']['template'][0]['container'][0]['image']='example:latest'
            if mutation=='wrongenvironment': resources[policy.LIVE]['change']['after']['container_app_environment_id']=ENVIRONMENT.replace('rg-ecommerce-dev','rg-other')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): policy.validate(p)

    def test_d6_validator_remains_closed_to_network_access(self):
        p=plan();p['resource_changes']=[x for x in p['resource_changes'] if x['address'] in policy.candidate.CANDIDATE]
        with self.assertRaises(ValueError): policy.candidate.validate(p)

    def test_enabled_cli_requires_live_egress_comparison_without_leaking_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'plan.json';p=plan();p['secret']='SENSITIVE-RAW-VALUE';path.write_text(json.dumps(p))
            result=subprocess.run([sys.executable,str(ROOT/'scripts/validate-network-plan.py'),str(path)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('SENSITIVE-RAW-VALUE',result.stdout+result.stderr)


class EgressTests(unittest.TestCase):
    def response(self):
        return dict(properties=dict(environmentId=ENVIRONMENT,workloadProfileName='Consumption',provisioningState='Succeeded',
                                    outboundIpAddresses=['20.40.60.80','20.40.60.81'],staticIp='8.8.8.8'))

    def test_reported_outbound_only_and_exact_environment(self):
        with patch.object(policy.egress,'arm_get',return_value=self.response()) as get:
            self.assertEqual(policy.egress.discover(SUBSCRIPTION,'cae-ecommerce-dev',['ca-ecommerce-dev-livedocs']),['20.40.60.80','20.40.60.81'])
            self.assertEqual(get.call_args.args[1],'2026-01-01')
        for field,value in [('outboundIpAddresses',[]),('environmentId',ENVIRONMENT.replace('rg-ecommerce-dev','rg-other')),
                             ('workloadProfileName','D4'),('provisioningState','Failed')]:
            r=self.response();r['properties'][field]=value
            with self.subTest(field=field),patch.object(policy.egress,'arm_get',return_value=r),self.assertRaises(ValueError):
                policy.egress.discover(SUBSCRIPTION,'cae-ecommerce-dev',['ca-ecommerce-dev-livedocs'])

    def test_private_loopback_multicast_cidr_and_allow_azure_rejected(self):
        for ip in ('0.0.0.0','127.0.0.1','10.1.2.3','169.254.1.2','192.168.0.1','224.0.0.1','255.255.255.255','20.40.60.80/32','::1'):
            with self.subTest(ip=ip), self.assertRaises(ValueError): policy.egress.public_ipv4([ip])

    def test_fresh_egress_change_rejects_old_acl(self):
        variables={k:v['value'] for k,v in plan()['variables'].items()}
        with patch.object(policy.egress,'discover',return_value=['20.40.60.81']),self.assertRaises(ValueError):
            policy.verify_egress(variables,SUBSCRIPTION)

    def test_readback_rejects_extra_or_broad_rules(self):
        names=dict(database_access_enabled=True,aca_ipv4=['20.40.60.80'],environment_name='cae-ecommerce-dev',discovery_app='ca-ecommerce-dev-livedocs',
                   candidate=dict(sql_server='sql-ecommerce-dev-d6-reviewd7',sql_database='products-gate',mongo_cluster='mongo-ecommerce-dev-d6-reviewd7',sql_location='francecentral'))
        response={'value':[{'name':'aca-20-40-60-80','properties':{'startIpAddress':'20.40.60.80','endIpAddress':'20.40.60.80'}}]}
        with patch.object(policy.egress,'discover',return_value=['20.40.60.80']),patch.object(policy.candidate,'readback') as db,patch.object(policy.egress,'arm_get',return_value=response):
            policy.readback(names,SUBSCRIPTION)
            self.assertTrue(db.call_args.kwargs['public_access_enabled'])
            response['value'].append({'name':'all','properties':{'startIpAddress':'0.0.0.0','endIpAddress':'0.0.0.0'}})
            with self.assertRaises(ValueError): policy.readback(names,SUBSCRIPTION)


if __name__=='__main__': unittest.main()
