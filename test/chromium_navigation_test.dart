import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/chromium_navigation.dart';

void main() {
  test('Chromium engine status must be actual native integration', () {
    expect(ChromiumEngineStatus.unavailable.ready, isFalse);
    expect(ChromiumEngineStatus.parse({
      'engine': 'android-webview', 'embedded': true
    }).ready, isFalse);
    expect(ChromiumEngineStatus.parse({
      'engine': 'chromium-native', 'embedded': false
    }).ready, isFalse);
    expect(ChromiumEngineStatus.parse({
      'engine': 'chromium-native', 'embedded': true
    }).ready, isTrue);
  });

  test('native navigation events retain tab identity and URL', () {
    final event = ChromiumNavigationEvent.parse({
      'tabId': 7,
      'type': 'url',
      'url': 'https://example.com/path',
      'title': 'Example',
      'progress': 45,
    });
    expect(event?.tabId, 7);
    expect(event?.url.toString(), 'https://example.com/path');
    expect(event?.progress, 45);
    expect(ChromiumNavigationEvent.parse({'type': 'url'}), isNull);
  });
}
