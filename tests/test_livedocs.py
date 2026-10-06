"""Exercise publication provenance and deployment cost/destruction boundaries."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
release = module('check-livedocs-release')
policy = module('validate-livedocs-plan')
smoke = module('smoke-livedocs')

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.value=json.loads((ROOT / 'releases/livedocs.json').read_text())
    def test_digest_source_and_publication_required(self):
        self.assertEqual(release.check(self.value), self.value)
        for key,value in [('image','mb0101/ecommerce-store-livedocs:latest'),('commitSha','main'),
                          ('publicationRun',0),('publicationRun',True),('schemaVersion',True)]:
            candidate=dict(self.value, **{key:value})
            with self.subTest(key=key,value=value), self.assertRaises(ValueError): release.check(candidate)
        with self.assertRaises(ValueError): release.check(dict(self.value, surprise='ignored'))
    def test_publication_must_be_successful_main_from_expected_repo_and_sha(self):
        run=dict(conclusion='success',head_sha=self.value['commitSha'],head_branch='main',event='push',
                 repository={'full_name':'MichalBoczula/ECommerceStore.LiveDocs'})
        with patch.object(release,'urlopen',return_value=io.BytesIO(json.dumps(run).encode())): release.verify(self.value)
        for key,value in [('conclusion','failure'),('head_sha','a'*40),('head_branch','feature'),
                          ('event','pull_request'),('repository',{'full_name':'other/repo'})]:
            with self.subTest(key=key), patch.object(release,'urlopen',return_value=io.BytesIO(json.dumps(dict(run,**{key:value})).encode())):
                with self.assertRaises(ValueError): release.verify(self.value)

class PlanTests(unittest.TestCase):
    def plan(self):
        changes=[]
        for address,kind in policy.ADDRESSES.items():
            after={'resource_group_name':'rg-ecommerce-dev'}
            if kind=='azurerm_container_app':
                after.update(workload_profile_name='Consumption',revision_mode='Single',
                    ingress=[{'allow_insecure_connections':False,'external_enabled':True,'target_port':8080}],
                    template=[{'min_replicas':0,'max_replicas':1,'container':[{'cpu':0.25,'memory':'0.5Gi'}]}])
            if kind=='azurerm_container_app_environment':
                after.update(workload_profile=[{'name':'Consumption','workload_profile_type':'Consumption'}],
                             logs_destination=None,infrastructure_resource_group_name='rg-ecommerce-dev-aca-managed')
            changes.append({'address':address,'type':kind,'mode':'managed','change':{'actions':['create'],'after':after}})
        return {'resource_changes':changes}
    def test_complete_small_deployment_and_idempotent_rerun(self):
        plan=self.plan()
        self.assertEqual(policy.validate(plan),{'create':4,'update':0})
        for item in plan['resource_changes']: item['change']['actions']=['no-op']
        self.assertEqual(policy.validate(plan),{'create':0,'update':0})
    def test_provider_disabled_logging_default_and_configured_destinations(self):
        plan = self.plan()
        environment = next(item['change']['after'] for item in plan['resource_changes'] if item['type'] == 'azurerm_container_app_environment')
        environment.update(logs_destination='', log_analytics_workspace_id='')
        self.assertEqual(policy.validate(plan), {'create':4, 'update':0})
        for field, value in (('logs_destination', 'log-analytics'), ('logs_destination', 'azure-monitor'),
                             ('log_analytics_workspace_id', 'configured-workspace')):
            rejected = copy.deepcopy(plan)
            next(item['change']['after'] for item in rejected['resource_changes'] if item['type'] == 'azurerm_container_app_environment')[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): policy.validate(rejected)
    def test_destroy_replacement_extra_missing_and_paid_resources_rejected(self):
        for actions in (['delete'],['delete','create'],['create','delete']):
            plan=self.plan(); plan['resource_changes'][0]['change']['actions']=actions
            with self.assertRaises(ValueError): policy.validate(plan)
        for mutation in ('paid','logging','group','extra','missing','allocation','http','replicas'):
            plan=self.plan(); items=plan['resource_changes']
            env=next(x['change']['after'] for x in items if x['type']=='azurerm_container_app_environment')
            app=next(x['change']['after'] for x in items if x['type']=='azurerm_container_app')
            if mutation=='paid': env['workload_profile'][0]['workload_profile_type']='D4'
            if mutation=='logging': env['logs_destination']='log-analytics'
            if mutation=='group': items[0]['change']['after']['resource_group_name']='rg-ecommerce-livedocs-archive'
            if mutation=='extra': items.append(copy.deepcopy(items[0]))
            if mutation=='missing': items.pop()
            if mutation=='allocation': app['template'][0]['container'][0]['cpu']=1
            if mutation=='http': app['ingress'][0]['allow_insecure_connections']=True
            if mutation=='replicas': app['template'][0]['min_replicas']=1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): policy.validate(plan)
    def test_errors_do_not_disclose_private_plan_values(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w') as target:
            json.dump({'resource_changes':[{'mode':'managed','type':'SENSITIVE_VALUE'}]},target); target.flush()
            result=subprocess.run(['python3',str(ROOT/'scripts/validate-livedocs-plan.py'),target.name],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SENSITIVE_VALUE', result.stdout+result.stderr)

class SmokeTests(unittest.TestCase):
    def test_unexpected_urls_are_rejected_before_network_access(self):
        for url in ('http://example.azurecontainerapps.io/livedoc/','https://example.com/livedoc/',
                    'https://user@example.azurecontainerapps.io/livedoc/','https://example.azurecontainerapps.io/livedoc/?secret=x'):
            with patch.object(smoke,'urlopen') as request, self.assertRaises(ValueError):
                smoke.check(url,'a'*40)
            request.assert_not_called()
    def test_wrong_source_commit_fails(self):
        class Response(io.BytesIO): status=200
        responses=[Response(b'OK') for _ in range(4)]+[Response(json.dumps({'commitSha':'b'*40}).encode())]
        with patch.object(smoke,'urlopen',side_effect=responses), self.assertRaises(ValueError):
            smoke.check('https://example.azurecontainerapps.io/livedoc/','a'*40)
