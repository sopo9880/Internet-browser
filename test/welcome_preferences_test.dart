import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/welcome_preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('fresh Android installation shows AdBlock welcome once', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final prefs = await SharedPreferences.getInstance();

    expect(await WelcomePreferences.shouldShow(prefs, onAndroid: true), isTrue);
    expect(prefs.containsKey(WelcomePreferences.completedKey), isFalse);

    await WelcomePreferences.markCompleted(prefs);
    expect(await WelcomePreferences.shouldShow(prefs, onAndroid: true), isFalse);
    expect(prefs.getBool(WelcomePreferences.completedKey), isTrue);
  });

  test('Windows welcome is not shown for an Android-only extension', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final prefs = await SharedPreferences.getInstance();
    expect(await WelcomePreferences.shouldShow(prefs, onAndroid: false), isFalse);
    expect(prefs.containsKey(WelcomePreferences.completedKey), isFalse);
  });

  test('upgrading v0.1.x preserves existing bookmarks and history', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'bookmarks': <String>['https://example.com/'],
      'history': <String>['https://example.com/'],
      'dpi_enabled': true,
    });
    final prefs = await SharedPreferences.getInstance();
    expect(await WelcomePreferences.shouldShow(prefs, onAndroid: true), isFalse);
    expect(prefs.getBool(WelcomePreferences.completedKey), isTrue);
    expect(prefs.getStringList('bookmarks'), <String>['https://example.com/']);
    expect(prefs.getStringList('history'), <String>['https://example.com/']);
    expect(prefs.getBool('dpi_enabled'), isTrue);
  });

  test('old DPI settings are detected even without bookmark records', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'dpi_preset': 'auto',
    });
    final prefs = await SharedPreferences.getInstance();
    expect(WelcomePreferences.hasExistingSettings(prefs), isTrue);
    expect(await WelcomePreferences.shouldShow(prefs, onAndroid: true), isFalse);
  });
}
