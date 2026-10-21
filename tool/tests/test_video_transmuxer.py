"""Pinned source closure checks; actual media conversion runs in native smoke."""
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from tool.chromium.video_transmuxer import ROOT, bundle_transmuxer


class TransmuxerSourceTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_contains_upstream_attribution(self):
        first = bundle_transmuxer()
        self.assertEqual(first, bundle_transmuxer())
        self.assertIn('Copyright (c) Brightcove', first)
        self.assertIn('Licensed Apache-2.0', first)

    def test_changed_source_and_escaped_path_are_rejected(self):
        for case in ('source', 'path'):
            with self.subTest(case=case), TemporaryDirectory() as temporary:
                directory = Path(temporary)/'muxjs'
                shutil.copytree(ROOT/'third_party/muxjs', directory)
                if case == 'source':
                    (directory/'lib/mp4/transmuxer.js').write_bytes(b'changed upstream source')
                else:
                    path = directory/'provenance.json'
                    record = json.loads(path.read_text(encoding='utf-8'))
                    record['source_files']['lib/../../outside.js'] = '0'*64
                    path.write_text(json.dumps(record),encoding='utf-8')
                with self.assertRaises(ValueError): bundle_transmuxer(directory)


if __name__ == '__main__': unittest.main()
