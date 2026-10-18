import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/dpi_options.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('DPI parameters reject arbitrary shell arguments', () {
    expect(DpiOptions.validPosition('1+s'), isTrue);
    expect(DpiOptions.validPosition('3+s'), isTrue);
    expect(DpiOptions.validPosition('1;rm -rf /'), isFalse);
    expect(DpiOptions.validPosition('--version'), isFalse);
  });

  test('Android and Windows use platform-aware default disorder', () {
    const o = DpiOptions(preset: DpiPreset.disorder);
    expect(o.toArguments(windows: true), contains('3+s'));
    expect(o.toArguments(windows: false), contains('1'));
  });

  test('advanced DPI flags persist', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    const original = DpiOptions(
      preset: DpiPreset.custom, splitValue: '2+s',
      disorder: true, fakePacket: true, fakeTtl: 12,
    );
    await original.save(prefs);
    final restored = DpiOptions.fromPrefs(prefs);
    expect(restored.preset, DpiPreset.custom);
    expect(restored.splitValue, '2+s');
    expect(restored.disorder, isTrue);
    expect(restored.toArguments(windows: true), contains('12'));
  });
}
