import io,json,unittest,zipfile
from urllib.request import urlopen
from tool.chromium.adblock_probe import select_rule,probe_server,AD_PATH,CONTROL_PATH,RULE_PATTERN
class AuthenticAdBlockProbeTests(unittest.TestCase):
    def rules(self,enabled=True,condition=None):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('rules.json',json.dumps([{'id':123,'action':{'type':'block'},'condition':condition or {'urlFilter':RULE_PATTERN}}]))
        stream.seek(0)
        return zipfile.ZipFile(stream),{'declarative_net_request':{'rule_resources':[{'id':'vendor-set','path':'rules.json','enabled':enabled}]}}
    def test_selects_enabled_vendor_rule_without_installing_custom_rules(self):
        archive,manifest=self.rules()
        with archive:self.assertEqual(select_rule(archive,manifest)['rule_id'],123)
    def test_disabled_or_site_constrained_rules_do_not_support_the_loopback_probe(self):
        for enabled,condition in ((False,None),(True,{'urlFilter':RULE_PATTERN,'initiatorDomains':['unrelated.example']})):
            with self.subTest(enabled=enabled):
                archive,manifest=self.rules(enabled,condition)
                with archive,self.assertRaises(ValueError):select_rule(archive,manifest)
    def test_server_records_both_requests_without_an_adblocker(self):
        with probe_server() as (base,snapshot):
            for path in (CONTROL_PATH,AD_PATH):
                with urlopen(base+path,timeout=5) as response:self.assertEqual(response.status,200)
            counts=snapshot()
            self.assertEqual(counts[CONTROL_PATH],1);self.assertEqual(counts[AD_PATH],1)
if __name__=='__main__':unittest.main()
