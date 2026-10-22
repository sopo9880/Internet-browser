"""Exercise the actual Java navigation methods, without claiming device acceptance."""
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AndroidNavigationPolicyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'Java compiler/runtime required')
    def test_web_and_intent_routing_respects_the_saved_setting(self):
        methods = (ROOT / 'native/chromium/android/java/navigation_methods.java.inc').read_text(encoding='utf-8')
        fixture = '''
@interface CalledByNative {}
class ContextUtils {
  static final Preferences prefs = new Preferences();
  static Preferences getAppSharedPreferences() { return prefs; }
}
class Preferences {
  java.util.Map<String, Boolean> values = new java.util.HashMap<>();
  boolean getBoolean(String key, boolean fallback) { return values.getOrDefault(key, fallback); }
  Preferences edit() { return this; }
  Preferences putBoolean(String key, boolean value) { values.put(key, value); return this; }
  void apply() {}
}
public class NavigationPolicyCheck {
''' + methods + '''
  static void expect(boolean value) { if (!value) throw new AssertionError(); }
  public static void main(String[] args) {
    for (String scheme : new String[] {"http", "https", "intent", "vnd.youtube", "instagram", "market"})
      expect(shouldBlockInternetBrowserExternalApp(scheme));
    for (String scheme : new String[] {"tel", "mailto", "sms", "content", "file", "about", "chrome", "blob", "", null})
      expect(!shouldBlockInternetBrowserExternalApp(scheme));
    setInternetBrowserBlockExternalApps(false);
    expect(!getInternetBrowserBlockExternalApps());
    for (String scheme : new String[] {"http", "https", "intent", "vnd.youtube", "instagram", "market"})
      expect(!shouldBlockInternetBrowserExternalApp(scheme));
    setInternetBrowserBlockExternalApps(true);
    expect(getInternetBrowserBlockExternalApps());
    expect(shouldBlockInternetBrowserExternalApp("https"));
    expect(!shouldBlockInternetBrowserExternalApp("tel"));
  }
}
'''
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'NavigationPolicyCheck.java'
            source.write_text(fixture, encoding='utf-8')
            subprocess.run(['javac', '-d', str(folder), str(source)], check=True, capture_output=True)
            subprocess.run(['java', '-cp', str(folder), 'NavigationPolicyCheck'], check=True, capture_output=True)
