"""Check saved-plan deployment/teardown ordering without Azure or public HTTP."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_destroy
import test_livedocs

ROOT=Path(__file__).resolve().parents[1]
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_destroy.DestroyTests(); self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.env=self.fixture.env
        self.env['LIVEDOCS_ARCHIVE_STORAGE_ACCOUNT']='stecomldtestarchive'
        self.env['PLAN_JSON']=json.dumps(test_livedocs.PlanTests().plan())
        target=self.fixture.directory/'python3'
        target.write_text('#!'+sys.executable+'\n'+r'''
import os, pathlib, sys
name=pathlib.Path(sys.argv[1]).name
if name in ('check-livedocs-release.py','smoke-livedocs.py'):
    if os.environ.get('FAIL_PYTHON')==name:
        sys.exit('Synthetic verification failure')
    print('Synthetic verification passed')
else:
    os.execv(sys.executable,[sys.executable,*sys.argv[1:]])
''')
        target.chmod(0o700)
        target=self.fixture.directory/'terraform'
        text=target.read_text().replace('elif operation == "state" and args[1:] == ["pull"]:',
            'elif operation == "output":\n        print(json.dumps({"portal_url":"https://test.azurecontainerapps.io/livedoc/","commit_sha":"a"*40}))\n    elif operation == "state" and args[1:] == ["pull"]:')
        target.write_text(text)
    def run_deploy(self):
        return subprocess.run(['bash',str(ROOT/'scripts/deploy-livedocs-development.sh')],env=self.env,capture_output=True,text=True)
    def test_plan_only_never_applies_and_removes_private_plan(self):
        result=self.run_deploy(); self.assertEqual(result.returncode,0,result.stderr)
        calls=self.fixture.calls(); self.assertFalse(any(x[:2]==['terraform','apply'] for x in calls))
        plan=next(x for x in calls if x[:2]==['terraform','plan'])
        private=Path(next(x[5:] for x in plan if x.startswith('-out='))).parent
        self.assertFalse(private.exists())
    def test_apply_uses_reviewed_saved_plan_and_archive_verified_twice(self):
        self.env['DEPLOY_ACTION']='apply'
        result=self.run_deploy(); self.assertEqual(result.returncode,0,result.stderr)
        calls=self.fixture.calls()
        plan=next(x for x in calls if x[:2]==['terraform','plan'])
        apply=next(x for x in calls if x[:2]==['terraform','apply'])
        self.assertEqual(apply[-1],next(x[5:] for x in plan if x.startswith('-out=')))
        self.assertEqual(len([x for x in calls if x[:3]==['az','storage','account']]),2)
    def test_provenance_failure_prevents_azure_and_terraform_operations(self):
        self.env['FAIL_PYTHON']='check-livedocs-release.py'
        self.assertNotEqual(self.run_deploy().returncode,0)
        self.assertEqual(self.fixture.calls(),[])
    def test_disallowed_changes_never_apply(self):
        self.env['DEPLOY_ACTION']='apply'
        value=json.loads(self.env['PLAN_JSON']); value['resource_changes'][0]['change']['actions']=['delete','create']
        self.env['PLAN_JSON']=json.dumps(value)
        self.assertNotEqual(self.run_deploy().returncode,0)
        self.assertFalse(any(x[:2]==['terraform','apply'] for x in self.fixture.calls()))
    def test_apply_failure_is_redacted_and_public_smoke_failure_is_not_success(self):
        self.env['DEPLOY_ACTION']='apply'; self.env['FAIL_OPERATION']='terraform:apply'
        result=self.run_deploy(); self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SENSITIVE-RAW-DIAGNOSTIC',result.stdout+result.stderr)
        self.env.pop('FAIL_OPERATION'); self.env['FAIL_PYTHON']='smoke-livedocs.py'
        self.assertNotEqual(self.run_deploy().returncode,0)
    def test_destroy_retains_archive_and_rejects_archive_import(self):
        self.fixture.set_plan(['delete'])
        result=self.fixture.run_destroy(); self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('archive account retained',result.stdout)
        self.fixture.set_plan(['delete'],'/subscriptions/test/resourceGroups/rg-ecommerce-livedocs-archive/providers/Microsoft.Storage/storageAccounts/archive')
        calls_before=len(self.fixture.calls())
        self.assertNotEqual(self.fixture.run_destroy().returncode,0)
        self.assertFalse(any(x[:2]==['terraform','apply'] for x in self.fixture.calls()[calls_before:]))
    def test_archive_backend_conflict_stops_before_azure_mutation(self):
        # The helper refuses initialized roots; CI's Terraform cache is sufficient.
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'scripts').mkdir(); (root/'foundations/livedocs/.terraform').mkdir(parents=True)
            shutil.copy(ROOT/'scripts/init-livedocs-archive.sh',root/'scripts')
            result=subprocess.run(['bash',str(root/'scripts/init-livedocs-archive.sh'),'rg-state','existingstate','1'*8+'-'+'1'*4+'-'+'1'*4+'-'+'1'*4+'-'+'1'*12],env=self.env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.fixture.calls(),[])
