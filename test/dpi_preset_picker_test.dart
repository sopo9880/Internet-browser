import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/dpi_options.dart';
import 'package:internet_browser/browser/dpi_preset_picker.dart';

void main() {
  testWidgets('friendly DPI preset dropdown maps to safe native args',
      (tester) async {
    DpiOptions current = const DpiOptions();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, update) => DpiPresetPicker(
            options: current,
            windows: true,
            onChanged: (value) =>
                update(() => current = current.copyWith(preset: value)),
          ),
        ),
      ),
    ));
    expect(find.text('인자 목록'), findsOneWidget);
    expect(find.text(DpiOptions.presetNames[DpiPreset.balanced]!), findsOneWidget);
    expect(find.textContaining('실제 ByeDPI 인자:'), findsOneWidget);
    await tester.tap(find.byType(DropdownButtonFormField<DpiPreset>));
    await tester.pumpAndSettle();
    await tester.tap(find.text(DpiOptions.presetNames[DpiPreset.disorder]!).last);
    await tester.pumpAndSettle();
    expect(current.preset, DpiPreset.disorder);
    expect(find.textContaining('3+s'), findsOneWidget);
  });
}
