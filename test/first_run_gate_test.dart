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
    try {
      SharedPreferences.setMockInitialValues(<String, Object>{});

      await tester.pumpWidget(const InternetBrowserApp());
      // The first-run gate displays an indeterminate loading animation until
      // preferences resolve. pumpAndSettle can time out on that animation,
      // so wait for the actual welcome route with bounded frame pumps.
      for (var attempt = 0;
          attempt < 20 && find.byType(WelcomeScreen).evaluate().isEmpty;
          attempt++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      expect(find.byType(MaterialApp), findsOneWidget);
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(find.textContaining('추천 확장 프로그램'), findsOneWidget);
      expect(find.byKey(const Key('welcome-adblock-install')), findsOneWidget);
    } finally {
      // Flutter checks global debug invariants before addTearDown callbacks.
      debugDefaultTargetPlatformOverride = null;
    }
  });
}
