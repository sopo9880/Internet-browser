import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/chromium_extensions.dart';

void main() {
  test('pin the exact user-required AdBlock Chrome extension', () {
    expect(RequiredChromeExtension.id, 'gighmmpiobklfepjocnamgkkbiglidom');
    expect(RequiredChromeExtension.validId(RequiredChromeExtension.id), isTrue);
    expect(RequiredChromeExtension.validId('some-other-extension'), isFalse);
    expect(RequiredChromeExtension.validId('../traversal'), isFalse);
  });

  test('Android WebView is NOT a Chrome extensions runtime', () {
    final caps = ChromiumExtensionCapabilities.unavailable;
    expect(caps.nativeEngine, isFalse);
    expect(caps.canLoadAdBlock, isFalse);
  });

  test('a partial Chromium extension implementation fails closed', () {
    final caps = ChromiumExtensionCapabilities.fromMap({
      'engine': 'android-chromium',
      'nativeEngine': true,
      'manifestV3': true,
      'chromeWebStoreInstall': true,
      'declarativeNetRequest': false,
      'serviceWorkers': true,
      'permissionPrompts': true,
      'actionPopup': true,
    });
    expect(caps.canLoadAdBlock, isFalse);
  });

  test('all native and MV3 capabilities are required', () {
    final caps = ChromiumExtensionCapabilities.fromMap({
      'engine': 'android-chromium',
      'nativeEngine': true,
      'manifestV3': true,
      'chromeWebStoreInstall': true,
      'declarativeNetRequest': true,
      'serviceWorkers': true,
      'permissionPrompts': true,
      'actionPopup': true,
    });
    expect(caps.canLoadAdBlock, isTrue);
    // Even these capabilities do NOT assert that the extension has installed,
    // persisted after relaunch, or blocked real network requests.
  });
}
