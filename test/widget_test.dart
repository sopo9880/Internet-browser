import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('browser app renders its own application shell', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await tester.pumpWidget(const InternetBrowserApp());

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.text('Internet Browser'), findsOneWidget);
  });
}
