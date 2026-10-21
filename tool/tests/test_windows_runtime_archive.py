import unittest
from tool.chromium.prepare_windows_runtime import archive_paths
class NativeRuntimeArchiveTests(unittest.TestCase):
    def test_regular_installer_layout(self):
        paths=archive_paths('Path = Chrome-bin\\chrome.exe\nSize = 10\n\nPath = Chrome-bin\\155.0.8059.84\\chrome.dll\n')
        self.assertEqual(paths,['Chrome-bin/chrome.exe','Chrome-bin/155.0.8059.84/chrome.dll'])
    def test_traversal_absolute_alternate_stream_and_colliding_paths_rejected(self):
        base='Path = Chrome-bin/chrome.exe\n'
        for path in ('../escape','Chrome-bin/../escape','C:/escape','/Chrome-bin/file','Chrome-bin/a:stream','Chrome-bin/space.','Chrome-bin/CHROME.EXE'):
            with self.subTest(path=path),self.assertRaises(ValueError):archive_paths(base+'Path = '+path+'\n')
        with self.assertRaises(ValueError):archive_paths(base+'Symbolic Link = outside\n')
    def test_missing_launcher_cannot_be_presented_as_a_runtime(self):
        with self.assertRaises(ValueError):archive_paths('Path = Chrome-bin/resources.pak\n')
if __name__=='__main__':unittest.main()
