import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/chromium_extensions.dart';
import 'package:internet_browser/browser/welcome_screen.dart';

class _FakeExtensionHost implements ChromeExtensionHost {
  _FakeExtensionHost({required this.available, this.installed = false});

  final bool available;
  bool installed;
  int installCalls = 0;

  @override
  Future<ChromiumExtensionCapabilities> capabilities() async {
    if (!available) {
      return ChromiumExtensionCapabilities.unavailable;
    }
    return ChromiumExtensionCapabilities.fromMap(<String, dynamic>{
      'engine': 'android-chromium',
      'nativeEngine': true,
      'manifestV3': true,
      'declarativeNetRequest': true,
      'serviceWorkers': true,
      'permissionPrompts': true,
      'chromeWebStoreInstall': true,
      'actionPopup': true,
    });
  }

  @override
  Future<bool> install(String id) async {
    expect(id, RequiredChromeExtension.id);
    installCalls++;
    installed = true;
    return true;
  }

  @override
  Future<bool> isInstalledAndEnabled(String id) async {
    expect(id, RequiredChromeExtension.id);
    return installed;
  }

  @override
  Future<void> uninstall(String id) async {
    installed = false;
  }
}

void main() {
  testWidgets('welcome recommends exact AdBlock but disables unsupported install',
      (tester) async {
    final host = _FakeExtensionHost(available: false);
    await tester.pumpWidget(MaterialApp(
      home: WelcomeScreen(onContinue: () async {}, extensionHost: host),
    ));
    await tester.pumpAndSettle();

    expect(find.text(RequiredChromeExtension.name), findsOneWidget);
    expect(find.text(RequiredChromeExtension.id), findsOneWidget);
    final install = tester.widget<FilledButton>(
      find.byKey(const Key('welcome-adblock-install')),
    );
    expect(install.onPressed, isNull);
    expect(host.installCalls, 0);
  });

  testWidgets('previously installed AdBlock is recognized without reinstall',
      (tester) async {
    final host = _FakeExtensionHost(available: true, installed: true);
    await tester.pumpWidget(MaterialApp(
      home: WelcomeScreen(onContinue: () async {}, extensionHost: host),
    ));
    await tester.pumpAndSettle();

    expect(find.text('AdBlock 설치 및 활성화 확인'), findsOneWidget);
    final install = tester.widget<FilledButton>(
      find.byKey(const Key('welcome-adblock-install')),
    );
    expect(install.onPressed, isNull);
    expect(host.installCalls, 0);
  });

  testWidgets('install is user-initiated and verifies actual enabled state',
      (tester) async {
    final host = _FakeExtensionHost(available: true);
    await tester.pumpWidget(MaterialApp(
      home: WelcomeScreen(onContinue: () async {}, extensionHost: host),
    ));
    await tester.pumpAndSettle();

    expect(host.installCalls, 0);
    await tester.scrollUntilVisible(
      find.byKey(const Key('welcome-adblock-install')),
      180,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const Key('welcome-adblock-install')));
    await tester.pumpAndSettle();

    expect(host.installCalls, 1);
    expect(find.text('AdBlock 설치 및 활성화 확인'), findsOneWidget);
  });

  testWidgets('user may continue without installing AdBlock', (tester) async {
    final host = _FakeExtensionHost(available: false);
    var continued = 0;
    await tester.pumpWidget(MaterialApp(
      home: WelcomeScreen(
        onContinue: () async {
          continued++;
        },
        extensionHost: host,
      ),
    ));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const Key('welcome-continue')),
      180,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const Key('welcome-continue')));
    await tester.pumpAndSettle();

    expect(continued, 1);
    expect(host.installCalls, 0);
  });
}
