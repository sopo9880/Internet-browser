import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/android_security_settings.dart';

void main() {
  test('Android security navigation falls back to general settings', () async {
    final actions = <String>[];
    final opened = await AndroidSecuritySettings.open(
      isAndroid: true,
      launch: (action) async {
        actions.add(action);
        if (action == AndroidSecuritySettings.securityAction) {
          throw StateError('Unsupported OEM shortcut');
        }
      },
    );
    expect(opened, isTrue);
    expect(actions, [
      AndroidSecuritySettings.securityAction,
      AndroidSecuritySettings.settingsAction,
    ]);
  });

  test('No Android settings navigation on Windows', () async {
    final actions = <String>[];
    final opened = await AndroidSecuritySettings.open(
      isAndroid: false,
      launch: (action) async => actions.add(action),
    );
    expect(opened, isFalse);
    expect(actions, isEmpty);
  });

  test('Unavailable Settings activities do not falsely report success',
      () async {
    final actions = <String>[];
    final opened = await AndroidSecuritySettings.open(
      isAndroid: true,
      launch: (action) async {
        actions.add(action);
        throw StateError('Unavailable');
      },
    );
    expect(opened, isFalse);
    expect(actions, hasLength(2));
  });
}
