"""Exercise candidate policy boundaries and saved-plan execution without Azure."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
import test_destroy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidate', ROOT/'scripts/validate-database-candidate.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def plan():
    body = dict(sku=dict(name='GP_S_Gen5_2', tier='GeneralPurpose', family='Gen5', capacity=2),
        properties=dict(useFreeLimit=True, freeLimitExhaustionBehavior='AutoPause', maxSizeBytes=34359738368,
            requestedBackupStorageRedundancy='Local', autoPauseDelay=60, minCapacity=0.5, zoneRedundant=False))
    sql = dict(resource_group_name='rg-ecommerce-dev', location='northeurope', version='12.0',
        minimum_tls_version='1.2', public_network_access_enabled=False)
    mongo = dict(type='Microsoft.DocumentDB/mongoClusters@2026-06-01', location='northeurope',
        parent_id='/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/rg-ecommerce-dev',
        body=dict(properties=dict(administrator=dict(password='Synthetic-Only-123!'), compute=dict(tier='Free'),
            storage=dict(sizeGb=32,type='PremiumSSD'), sharding=dict(shardCount=1), highAvailability=dict(targetMode='Disabled'),
            serverVersion='8.0',publicNetworkAccess='Disabled',createMode='Default',authConfig=dict(allowedModes=['NativeAuth']))))
    values = [sql,
        dict(type='Microsoft.Sql/servers/databases@2023-08-01', name='products-gate', location='northeurope', body=body),
        mongo]
    config = [dict(address=a.removesuffix('[0]'), expressions={}) for a in policy.CANDIDATE]
    config[1]['expressions']['parent_id'] = dict(references=['azurerm_mssql_server.database_candidate'])
    return dict(complete=True, configuration=dict(root_module=dict(resources=config)), resource_changes=[
        dict(address=a, type=k, mode='managed', change=dict(actions=['create'], after=value))
        for (a,k),value in zip(policy.CANDIDATE.items(),values)])


def readback():
    changes = plan()['resource_changes']
    return dict(server=dict(location='northeurope', properties=dict(publicNetworkAccess='Disabled')),
        database=dict(location='northeurope', **copy.deepcopy(changes[1]['change']['after']['body'])),
        mongo=dict(location='northeurope', **copy.deepcopy(changes[2]['change']['after']['body'])))


class CandidatePolicyTests(unittest.TestCase):
    def test_free_candidate_and_counted_parent_references(self):
        self.assertEqual(policy.validate(plan()), dict(create=3, update=0))
    def test_paid_billing_public_access_cross_group_and_replacement_rejected(self):
        cases = [(0,'resource_group_name','rg-other'),
            (0,'public_network_access_enabled',True)]
        for i,key,value in cases:
            with self.subTest(key=key):
                p=plan(); p['resource_changes'][i]['change']['after'][key]=value
                with self.assertRaises(ValueError): policy.validate(p)
        p=plan();p['resource_changes'][2]['change']['after']['body']['properties']['compute']['tier']='M10'
        with self.assertRaises(ValueError):policy.validate(p)
        for value in ('BillOverUsage', None):
            p=plan(); p['resource_changes'][1]['change']['after']['body']['properties']['freeLimitExhaustionBehavior']=value
            with self.assertRaises(ValueError): policy.validate(p)
        p=plan();p['resource_changes'][0]['change']['actions']=['delete','create']
        with self.assertRaises(ValueError): policy.validate(p)
    def test_parent_substitution_missing_resource_and_app_mutation_rejected(self):
        p=plan();p['configuration']['root_module']['resources'][1]['expressions']['parent_id']['references']=['azurerm_mssql_server.other']
        with self.assertRaises(ValueError):policy.validate(p)
        p=plan();p['resource_changes'].pop()
        with self.assertRaises(ValueError):policy.validate(p)
        p=plan();p['resource_changes'].append(dict(address='module.livedocs[0].azurerm_container_app.host',
            type='azurerm_container_app',mode='managed',change=dict(actions=['update'],after=dict(resource_group_name='rg-ecommerce-dev'))))
        with self.assertRaises(ValueError):policy.validate(p)
    def test_readiness_contract_copies_are_byte_identical(self):
        for item in json.loads((ROOT/'verification/database-gate/contracts.json').read_text()):
            self.assertEqual(hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest(),item['sha256'])

    def test_firewall_and_mongo_public_access_rejected(self):
        p=plan();p['resource_changes'][2]['change']['after']['body']['properties']['publicNetworkAccess']='Enabled'
        with self.assertRaises(ValueError): policy.validate(p)
        p=plan();p['resource_changes'].append(dict(address='azurerm_mssql_firewall_rule.database_candidate[0]',
            type='azurerm_mssql_firewall_rule',mode='managed',change=dict(actions=['create'],after={})))
        with self.assertRaises(ValueError): policy.validate(p)

    def test_readback_rejects_paid_or_open_resources(self):
        r=readback();r['database']['sku']['extraServiceField']='allowed'
        policy.validate_readback(r['server'],r['database'],r['mongo'])
        for resource, field, value in [('server','publicNetworkAccess','Enabled'),
                ('database','freeLimitExhaustionBehavior','BillOverUsage'),
                ('mongo','publicNetworkAccess','Enabled'),('mongo','compute',dict(tier='M10'))]:
            with self.subTest(resource=resource,field=field):
                r=readback();r[resource]['properties'][field]=value
                with self.assertRaises(ValueError): policy.validate_readback(r['server'],r['database'],r['mongo'])


class CandidateWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_destroy.DestroyTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        fake = test_destroy.FAKE_TOOL.replace(
            '    elif operation == "show":',
            '    elif operation == "output":\n        print(os.environ["NAMES_JSON"])\n    elif operation == "show":')
        fake += '\nif tool == "az" and operation == "rest":\n    url = args[args.index("--url") + 1]\n    key = "mongo" if "mongoClusters/" in url else "database" if "/databases/" in url else "server"\n    print(json.dumps(json.loads(os.environ["READBACK_JSON"])[key]))\n'
        for tool in ('terraform', 'az'):
            (self.fixture.directory/tool).write_text(fake)
        self.env=self.fixture.env
        self.env.update(NAMES_JSON=json.dumps(dict(sql_server='sql-ecommerce-d6-reviewd6',
            sql_database='products-gate', mongo_cluster='mongo-ecommerce-d6-reviewd6')),
            READBACK_JSON=json.dumps(readback()))
        self.env.update(PLAN_JSON=json.dumps(plan()),TF_VAR_enable_database_candidate='true',DEPLOY_ACTION='plan')
    def run_candidate(self):
        return subprocess.run(['bash',str(ROOT/'scripts/deploy-database-candidate.sh')],env=self.env,capture_output=True,text=True)
    def test_plan_only_and_saved_plan_apply(self):
        self.assertEqual(self.run_candidate().returncode,0)
        self.assertFalse(any(c[:2] in (['terraform','apply'], ['az','rest']) for c in self.fixture.calls()))
        self.env['DEPLOY_ACTION']='apply'
        result=self.run_candidate();self.assertEqual(result.returncode,0,result.stderr)
        calls=self.fixture.calls()
        apply=next(c for c in calls if c[:2]==['terraform','apply'])
        saved=[c for c in calls if c[:2]==['terraform','plan']][-1]
        self.assertEqual(apply[-1],next(v[5:] for v in saved if v.startswith('-out=')))
        self.assertFalse(Path(apply[-1]).parent.exists())
        self.assertEqual(len([c for c in calls if c[:2]==['az','rest']]), 3)
    def test_rejected_plan_and_failed_apply_do_not_leak(self):
        self.env['DEPLOY_ACTION']='apply'
        p=plan();p['resource_changes'][2]['change']['after']['body']['properties']['compute']['tier']='M10';self.env['PLAN_JSON']=json.dumps(p)
        self.assertNotEqual(self.run_candidate().returncode,0)
        self.assertFalse(any(c[:2]==['terraform','apply'] for c in self.fixture.calls()))
        self.env['PLAN_JSON']=json.dumps(plan());self.env['FAIL_OPERATION']='terraform:apply'
        result=self.run_candidate();self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SENSITIVE-RAW-DIAGNOSTIC',result.stdout+result.stderr)
    def test_disabled_candidate_stops_before_terraform(self):
        self.env['TF_VAR_enable_database_candidate']='false'
        self.assertNotEqual(self.run_candidate().returncode,0)
        self.assertEqual(self.fixture.calls(),[])

    def test_failed_or_paid_readback_fails_without_raw_output(self):
        self.env['DEPLOY_ACTION']='apply'
        self.env['FAIL_OPERATION']='az:rest'
        result=self.run_candidate()
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SENSITIVE-RAW-DIAGNOSTIC',result.stdout+result.stderr)
        del self.env['FAIL_OPERATION']
        r=readback();r['database']['properties']['useFreeLimit']=False
        self.env['READBACK_JSON']=json.dumps(r)
        result=self.run_candidate()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('readback',result.stderr)
