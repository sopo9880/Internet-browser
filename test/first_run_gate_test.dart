import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/welcome_screen.dart';
import 'package:internet_browser/main.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('fresh Android app opens AdBlock welcome on first launch',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    SharedPreferences.setMockInitialValues(<String, Object>{});

    await tester.pumpWidget(const InternetBrowserApp());
    await tester.pumpAndSettle();

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.textContaining('추천 확장 프로그램'), findsOneWidget);
    expect(find.byKey(const Key('welcome-adblock-install')), findsOneWidget);
  });
}
