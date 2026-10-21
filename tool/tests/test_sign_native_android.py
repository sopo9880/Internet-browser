"""Signing orchestration checks use synthetic keys/ZIPs and mocked signer tools.

These never certify a real APK or access a production credential.
"""
import base64,json,os,shutil,subprocess
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from tool.release_metadata import ReleaseMetadata
from tool.chromium import sign_native_android as signer

class NativeSigningPolicyTests(unittest.TestCase):
    def test_only_matching_hosted_main_signs(self):
        env={'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch',
             'RUNNER_ENVIRONMENT':'github-hosted','GITHUB_SHA':'a'*40}
        signer.require_hosted_main(env,'a'*40)
        for key,value in (('GITHUB_REF','refs/heads/feature'),('GITHUB_EVENT_NAME','pull_request'),
                          ('RUNNER_ENVIRONMENT','self-hosted'),('GITHUB_SHA','b'*40),('GITHUB_ACTIONS','false')):
            with self.subTest(key=key),self.assertRaises(ValueError):
                signer.require_hosted_main({**env,key:value},'a'*40)

    def test_source_provenance_requires_matching_compiled_product(self):
        transport={'compiled':True,'source_revision':signer.REVISION,'ndk_version':signer.NDK_VERSION,
                   'llvm_revision':signer.LLVM_VERSION,'sha256':'c'*64}
        report={'kind':'NATIVE_ANDROID_SOURCE_BUILD_NOT_RUNTIME_ACCEPTANCE','compiled':True,
                'product_objects_compiled':True,'source_validated':True,'production_signed':False,
                'integration_commit':'a'*40,'integration_tree':'b'*40,'product':signer.PRODUCT,
                'version_code':2002001,'package':signer.PRODUCT_PACKAGE,'source_revision':'d'*40,
                'upstream':{'upstream_driver_applied':True,'chromium_base':signer.PRODUCT['chromium_revision'],'root_after_driver':'d'*40},
                'overlay':{'source_revision':'d'*40,'product':signer.PRODUCT,
                           'files':{'chrome/browser/internet_browser/'+name:digest for name,digest in signer.product_hashes('c'*64).items()}}}
        arguments={'commit':'a'*40,'tree':'b'*40,'version':signer.PRODUCT['app_version'],'version_code':2002001}
        signer.validate_report(report,transport,**arguments)
        for field,bad in (('compiled',False),('source_validated',False),('integration_commit','f'*40),
                          ('integration_tree','e'*40),('package','other.app'),('version_code',2001001),('production_signed',True)):
            with self.subTest(field=field),self.assertRaises(ValueError):
                signer.validate_report({**report,field:bad},transport,**arguments)
        changed=deepcopy(report)
        changed['overlay']['files']['chrome/browser/internet_browser/resources.h']='0'*64
        with self.assertRaises(ValueError):signer.validate_report(changed,transport,**arguments)

    def test_changed_payload_is_not_hidden_by_signature_exclusions(self):
        import zipfile
        with TemporaryDirectory() as tmp:
            before=Path(tmp)/'before.zip';after=Path(tmp)/'after.zip'
            with zipfile.ZipFile(before,'w') as archive:
                archive.writestr('classes.dex',b'original');archive.writestr('META-INF/CERT.RSA',b'old-signature')
            with zipfile.ZipFile(after,'w') as archive:
                archive.writestr('classes.dex',b'original');archive.writestr('META-INF/CERT.RSA',b'new-signature')
            self.assertEqual(signer.signing_entries(before),signer.signing_entries(after))
            with zipfile.ZipFile(after,'w') as archive:archive.writestr('classes.dex',b'modified')
            self.assertNotEqual(signer.signing_entries(before),signer.signing_entries(after))

    def synthetic_sign(self, *, bad_certificate=False, change_payload=False):
        import zipfile
        with TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir();output=root/'output';key_temp=root/'keys';key_temp.mkdir()
            apk=source/'native-chromium.apk'
            with zipfile.ZipFile(apk,'w') as archive:archive.writestr('classes.dex',b'compiled fixture')
            commit=subprocess.check_output(['git','-C',str(signer.ROOT),'rev-parse','HEAD'],text=True).strip()
            env={**os.environ,'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch',
                 'RUNNER_ENVIRONMENT':'github-hosted','GITHUB_SHA':commit,'RUNNER_TEMP':str(key_temp),
                 'ANDROID_KEYSTORE_BASE64':base64.b64encode(b'\x30'+b'\0'*127).decode(),
                 'ANDROID_KEYSTORE_PASSWORD':'fake-store-password','ANDROID_KEY_ALIAS':'test-key',
                 'ANDROID_KEY_PASSWORD':'fake-key-password'}
            report={'integration_tree':'b'*40,'apk_sha256':signer.sha256(apk)}
            metadata=ReleaseMetadata('0.2.2','v0.2.2',1,2002001)
            calls=[]
            def tool(program,*args,env=None):
                calls.append((str(program),args))
                if env is not None:self.assertNotIn('ANDROID_KEYSTORE_BASE64',env)
                self.assertNotIn('fake-store-password',args);self.assertNotIn('fake-key-password',args)
                if str(program)=='keytool':return 'PrivateKeyEntry'
                if str(program)=='zipalign':
                    if args[0]=='-f':shutil.copyfile(args[-2],args[-1])
                    return ''
                if args[0]=='sign':
                    signed=Path(args[args.index('--out')+1]);shutil.copyfile(args[-1],signed)
                    if change_payload:
                        with zipfile.ZipFile(signed,'w') as archive:archive.writestr('classes.dex',b'tampered')
                    return ''
                certificate='f'*64 if bad_certificate else signer.PRODUCTION_CERT_SHA256
                return 'Number of signers: 1\nSigner #1 certificate SHA-256 digest: '+certificate+'\n'
            with patch.object(signer,'verify_source',return_value=(report,metadata)),patch.object(signer,'verify_native_apk'),patch.object(signer,'command',side_effect=tool):
                if bad_certificate or change_payload:
                    with self.assertRaises(ValueError):signer.sign(source,output,Path('aapt2'),Path('apksigner'),Path('zipalign'),env)
                    self.assertFalse((output/'Internet-browser-Android-v0.2.2.apk').exists())
                else:
                    result=signer.sign(source,output,Path('aapt2'),Path('apksigner'),Path('zipalign'),env)
                    self.assertTrue(result['production_signed'])
                    self.assertFalse(result['release_approved'])
                    self.assertEqual(result['release_certificate_sha256'],signer.PRODUCTION_CERT_SHA256)
                    count=len(calls)
                    with self.assertRaisesRegex(ValueError,'existing release APK'):
                        signer.sign(source,output,Path('aapt2'),Path('apksigner'),Path('zipalign'),env)
                    self.assertEqual(len(calls),count)
            self.assertEqual(list(key_temp.iterdir()),[])
    def test_synthetic_success_cleans_key_and_refuses_resigning(self):self.synthetic_sign()
    def test_wrong_certificate_cleans_key_without_staging_apk(self):self.synthetic_sign(bad_certificate=True)
    def test_changed_compiled_payload_cleans_key_without_staging_apk(self):self.synthetic_sign(change_payload=True)

if __name__=='__main__':unittest.main()
