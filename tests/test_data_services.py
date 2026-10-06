"""D/8 plan boundaries, ARM readback and private secret transport."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_network_access as network

ROOT = Path(__file__).resolve().parents[1]
policy = network.policy.data_services
spec = importlib.util.spec_from_file_location('secret_setter', ROOT / 'scripts/set-development-secret.py')
setter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setter)
SUB = network.SUBSCRIPTION
EXPECTED = policy.names(SUB)
STORAGE = EXPECTED['root'] + 'Microsoft.Storage/storageAccounts/' + EXPECTED['storage']
VAULT = EXPECTED['root'] + 'Microsoft.KeyVault/vaults/' + EXPECTED['vault']


def plan(databases=False):
    p = network.plan(False, databases, databases)
    p['variables']['enable_data_services'] = {'value': 'true'}
    p['configuration']['root_module']['module_calls'] = {'data_services': {'expressions': {
        'subnet_id': {'references': ['module.consumption[0].subnet_id']},
        'tenant_id': {'references': ['data.azurerm_client_config.data_services[0].tenant_id']}},
        'module': {'resources': [{'address': 'azurerm_storage_container.files', 'expressions': {
            'storage_account_id': {'references': ['azurerm_storage_account.business']}}}]}}}
    acl = dict(default_action='Deny', ip_rules=[], virtual_network_subnet_ids=[EXPECTED['subnet']])
    for address, kind in policy.ADDRESSES.items():
        if kind == 'azurerm_storage_container':
            after = dict(name='invoices' if 'invoices' in address else 'photos', container_access_type='private', storage_account_id=STORAGE)
        elif kind == 'azurerm_storage_account':
            after = dict(name=EXPECTED['storage'], resource_group_name='rg-ecommerce-dev', location='northeurope',
                account_kind='StorageV2', account_tier='Standard', account_replication_type='LRS', access_tier='Hot',
                shared_access_key_enabled=False, allow_nested_items_to_be_public=False, default_to_oauth_authentication=True,
                https_traffic_only_enabled=True, min_tls_version='TLS1_2', public_network_access='Enabled',
                network_rules=[dict(acl, bypass=['None'])], blob_properties=[dict(versioning_enabled=False)])
        else:
            after = dict(name=EXPECTED['vault'], resource_group_name='rg-ecommerce-dev', location='northeurope',
                sku_name='standard', rbac_authorization_enabled=True, public_network_access_enabled=True,
                purge_protection_enabled=False, soft_delete_retention_days=7, tenant_id=SUB, access_policy=[],
                enabled_for_deployment=False, enabled_for_disk_encryption=False, enabled_for_template_deployment=False,
                network_acls=[dict(acl, bypass='None')])
        p['resource_changes'].append(dict(address=address, type=kind, mode='managed', change=dict(actions=['create'], after=after)))
    return p


def metadata():
    return dict(storage_account_id=STORAGE, key_vault_id=VAULT, subnet_id=EXPECTED['subnet'],
                mongo_databases=policy.MONGO_DATABASES, secret_names=policy.SECRET_NAMES)


def responses():
    acl = dict(defaultAction='Deny', bypass='None', ipRules=[], virtualNetworkRules=[dict(id=EXPECTED['subnet'])])
    return {STORAGE: dict(location='northeurope', kind='StorageV2', sku=dict(name='Standard_LRS'), properties=dict(
        allowBlobPublicAccess=False, allowSharedKeyAccess=False, defaultToOAuthAuthentication=True,
        supportsHttpsTrafficOnly=True, minimumTlsVersion='TLS1_2', publicNetworkAccess='Enabled', networkAcls=copy.deepcopy(acl))),
        VAULT: dict(location='northeurope', properties=dict(sku=dict(name='standard'), enableRbacAuthorization=True,
            softDeleteRetentionInDays=7, networkAcls=copy.deepcopy(acl))),
        STORAGE+'/blobServices/default': dict(properties=dict(isVersioningEnabled=False)),
        **{STORAGE+'/blobServices/default/containers/'+name: dict(properties=dict(publicAccess='None')) for name in ('invoices', 'photos')}}


class DataServicesTests(unittest.TestCase):
    def test_closed_database_and_files_only_stages(self):
        for databases, creates in ((False, 7), (True, 11)):
            with self.subTest(databases=databases):
                self.assertEqual(network.policy.validate(plan(databases), SUB)[0]['create'], creates)
        with self.assertRaises(ValueError): network.policy.validate(plan())

    def test_public_broad_wrong_parent_and_replacement_rejected(self):
        mutations = [('azurerm_storage_account', 'shared_access_key_enabled', True),
                     ('azurerm_storage_account', 'account_replication_type', 'GRS'),
                     ('azurerm_key_vault', 'rbac_authorization_enabled', False),
                     ('azurerm_key_vault', 'purge_protection_enabled', True),
                     ('azurerm_storage_container', 'container_access_type', 'blob'),
                     ('azurerm_storage_container', 'storage_account_id', STORAGE+'wrong')]
        for kind, field, value in mutations:
            p = plan()
            next(x for x in p['resource_changes'] if x['type']==kind)['change']['after'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): network.policy.validate(p, SUB)
        for mutation in ('ip', 'subnet', 'bypass', 'replace', 'missing', 'secret', 'binding'):
            p = plan(); resource = p['resource_changes'][-4]
            if mutation=='ip': resource['change']['after']['network_rules'][0]['ip_rules']=['1.2.3.4']
            if mutation=='subnet': resource['change']['after']['network_rules'][0]['virtual_network_subnet_ids']=[EXPECTED['subnet']+'wrong']
            if mutation=='bypass': resource['change']['after']['network_rules'][0]['bypass']=['AzureServices']
            if mutation=='replace': resource['change']['actions']=['delete','create']
            if mutation=='missing': p['resource_changes'].pop()
            if mutation=='secret': p['resource_changes'].append(dict(address='azurerm_key_vault_secret.unexpected', type='azurerm_key_vault_secret', mode='managed', change=dict(actions=['create'],after={})))
            if mutation=='binding': p['configuration']['root_module']['module_calls']['data_services']['expressions']['subnet_id']['references']=['module.other.subnet_id']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): network.policy.validate(p, SUB)

    def test_real_cli_accepts_d8_and_redacts_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'plan.json'; p=plan(True);path.write_text(json.dumps(p))
            command=[sys.executable,str(ROOT/'scripts/validate-network-plan.py'),str(path),'--verify-egress',SUB]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            p['resource_changes'][-1]['change']['after']['sku_name']='PRIVATE-SENTINEL';path.write_text(json.dumps(p))
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('PRIVATE-SENTINEL',result.stdout+result.stderr)

    def test_readback_rejects_network_and_retention_drift(self):
        values=responses();policy.readback(metadata(),SUB,lambda resource,api: values[resource])
        for mutation in ('acl','key','container','retention','identity'):
            values=responses(); data=metadata()
            if mutation=='acl': values[VAULT]['properties']['networkAcls']['defaultAction']='Allow'
            if mutation=='key': values[STORAGE]['properties']['allowSharedKeyAccess']=True
            if mutation=='container': values[STORAGE+'/blobServices/default/containers/photos']['properties']['publicAccess']='Blob'
            if mutation=='retention': values[STORAGE+'/blobServices/default']['properties']['deleteRetentionPolicy']={'enabled':True}
            if mutation=='identity': data['key_vault_id']=VAULT+'wrong'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): policy.readback(data,SUB,lambda resource,api: values[resource])

    def test_secret_transport_has_private_body_and_cleans_up_on_error(self):
        for fail in (False,True):
            paths=[]
            def run(args, **kwargs):
                self.assertNotIn('SECRET-SENTINEL',str(args))
                path=Path(args[args.index('--body')+1][1:]);paths.append(path)
                self.assertEqual(json.loads(path.read_text())['properties']['value'],'SECRET-SENTINEL')
                if os.name!='nt': self.assertEqual(path.stat().st_mode & 0o777,0o600)
                self.assertTrue(kwargs['capture_output'])
                if fail: raise subprocess.CalledProcessError(1,args,stderr='SECRET-SENTINEL')
            with patch.object(setter.shutil,'which',return_value='az'),patch.object(setter.subprocess,'run',side_effect=run):
                if fail:
                    with self.assertRaises(subprocess.CalledProcessError): setter.write_secret(metadata(),{'id':SUB},'users-mongo-connection','SECRET-SENTINEL')
                else: setter.write_secret(metadata(),{'id':SUB},'users-mongo-connection','SECRET-SENTINEL')
            self.assertFalse(paths[0].exists())

    def test_secret_write_rejects_archive_wrong_subscription_and_unapproved_names(self):
        for mutation in ('archive','subscription','name','empty'):
            data=metadata();sub=SUB;name='users-mongo-connection';value='hidden'
            if mutation=='archive': data['key_vault_id']=VAULT.replace('rg-ecommerce-dev','rg-ecommerce-livedocs-archive')
            if mutation=='subscription': sub='22222222-2222-2222-2222-222222222222'
            if mutation=='name': name='arbitrary-secret'
            if mutation=='empty': value=''
            with self.subTest(mutation=mutation),patch.object(setter.subprocess,'run') as run,self.assertRaises(ValueError):
                setter.write_secret(data,{'id':sub},name,value)
            run.assert_not_called()
