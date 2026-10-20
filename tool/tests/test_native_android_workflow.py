"""Execute the actual workflow policy with controlled refs/version files."""
import json,os,subprocess,sys,textwrap
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
ROOT=Path(__file__).resolve().parents[2]
class NativeAndroidWorkflowPolicyTests(unittest.TestCase):
    def check(self,phase,ref,version='0.2.2'):
        workflow=(ROOT/'.github/workflows/native-android.yml').read_text(encoding='utf-8')
        code=textwrap.dedent(workflow.split("          python3 - <<'PY'\n",1)[1].split('          PY\n',1)[0])
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'native/chromium').mkdir(parents=True)
            (root/'native/chromium/product.json').write_text(json.dumps({'app_version':'0.2.2'}))
            (root/'pubspec.yaml').write_text('version: '+version+'+1\n')
            output=root/'outputs'
            env={**os.environ,'BUILD_PHASE':phase,'COMPILER_JOBS':'2','GITHUB_REF':ref,'GITHUB_OUTPUT':str(output),
                 'PYTHONPATH':str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')}
            result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True)
            return result,output.read_text() if output.exists() else ''
    def test_product_objects_can_be_checked_on_feature_branch(self):
        result,output=self.check('product-objects','refs/heads/feature','0.2.1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('version_code=2002001',output)
    def test_formal_apk_requires_main_and_matching_release_version(self):
        for ref,version in (('refs/heads/feature','0.2.2'),('refs/heads/main','0.2.1')):
            with self.subTest(ref=ref,version=version):
                result,output=self.check('apk',ref,version)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(output,'')
        result,output=self.check('apk','refs/heads/main')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('version_code=2002001',output)
    def test_unknown_phase_cannot_select_an_unrestricted_build(self):
        result,output=self.check('bypass','refs/heads/main')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(output,'')
if __name__=='__main__':unittest.main()
