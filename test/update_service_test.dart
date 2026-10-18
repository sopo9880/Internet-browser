import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/update_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, Object> releaseJson({
  String tag = 'v0.1.1',
  bool draft = false,
  bool prerelease = false,
  String? assetUrl,
  String? digest,
}) {
  const file = 'Internet-browser-Android-v0.1.1.apk';
  return <String, Object>{
    'tag_name': tag,
    'draft': draft,
    'prerelease': prerelease,
    'body': 'Bug fixes',
    'assets': <Map<String, Object>>[
      <String, Object>{
        'name': file,
        'state': 'uploaded',
        'size': 2048,
        'digest': digest ?? 'sha256:${List.filled(64, 'a').join()}',
        'browser_download_url': assetUrl ??
            'https://github.com/sopo9880/Internet-browser/'
                'releases/download/$tag/$file',
      },
    ],
  };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('compares numeric version segments, not strings', () {
    expect(BrowserUpdateService.compareVersions('0.4.10', '0.4.9'), greaterThan(0));
    expect(BrowserUpdateService.compareVersions('v0.4.12.1', '0.4.12'), greaterThan(0));
    expect(BrowserUpdateService.compareVersions('0.4.12', 'v0.4.12.0'), 0);
    expect(BrowserUpdateService.parseVersion('v0.2-beta'), isNull);
  });

  test('newer stable release selects only the official platform APK', () {
    final update = BrowserUpdateService.parseLatest(
      releaseJson(),
      installedVersion: '0.1.0',
      platform: UpdatePlatform.android,
    );
    expect(update, isNotNull);
    expect(update!.version, '0.1.1');
    expect(update.canInstallInApp, isTrue);
    expect(update.installer!.size, 2048);
    expect(update.installer!.sha256Digest, List.filled(64, 'a').join());
  });

  test('does not downgrade or offer draft and prerelease versions', () {
    expect(BrowserUpdateService.parseLatest(
      releaseJson(),
      installedVersion: '0.1.1',
      platform: UpdatePlatform.android,
    ), isNull);
    expect(BrowserUpdateService.parseLatest(
      releaseJson(draft: true),
      installedVersion: '0.1.0',
      platform: UpdatePlatform.android,
    ), isNull);
    expect(BrowserUpdateService.parseLatest(
      releaseJson(prerelease: true),
      installedVersion: '0.1.0',
      platform: UpdatePlatform.android,
    ), isNull);
  });

  test('rejects off-repository installer URL and absent digest', () {
    final forged = BrowserUpdateService.parseLatest(
      releaseJson(assetUrl: 'https://attacker.example/installer.apk'),
      installedVersion: '0.1.0',
      platform: UpdatePlatform.android,
    );
    expect(forged, isNotNull);
    expect(forged!.canInstallInApp, isFalse);

    final unsignedHash = BrowserUpdateService.parseLatest(
      releaseJson(digest: 'sha256:not-a-real-hash'),
      installedVersion: '0.1.0',
      platform: UpdatePlatform.android,
    );
    expect(unsignedHash, isNotNull);
    expect(unsignedHash!.canInstallInApp, isFalse);
  });

  test('refuses APK on Windows and keeps the release link available', () {
    final update = BrowserUpdateService.parseLatest(
      releaseJson(),
      installedVersion: '0.1.0',
      platform: UpdatePlatform.windows,
    );
    expect(update, isNotNull);
    expect(update!.installer, isNull);
    expect(update.releasePage.host, 'github.com');
  });

  test('seven-day snooze applies only to the announced release', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final service = BrowserUpdateService();
    final day = DateTime.utc(2026, 10, 18);
    final update = BrowserUpdateService.parseLatest(
      releaseJson(),
      installedVersion: '0.1.0',
      platform: UpdatePlatform.android,
    )!;

    expect(service.isSnoozed(prefs, update, now: day), isFalse);
    await service.snooze(prefs, update, now: day);
    expect(service.isSnoozed(
      prefs, update, now: day.add(const Duration(days: 6)),
    ), isTrue);
    expect(service.isSnoozed(
      prefs, update, now: day.add(const Duration(days: 7)),
    ), isFalse);

    final newer = BrowserUpdate(
      tag: 'v0.1.2',
      version: '0.1.2',
      description: '',
      releasePage: Uri.parse('https://github.com/sopo9880/Internet-browser/releases/tag/v0.1.2'),
      platform: UpdatePlatform.android,
    );
    expect(service.isSnoozed(prefs, newer, now: day), isFalse);
    service.dispose();
  });

  test('automatic checks are throttled; manual checks can bypass', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final service = BrowserUpdateService();
    final day = DateTime.utc(2026, 10, 18);
    expect(service.shouldCheckAutomatically(prefs, now: day), isTrue);
    await service.rememberSuccessfulCheck(prefs, now: day);
    expect(service.shouldCheckAutomatically(
      prefs, now: day.add(const Duration(hours: 1)),
    ), isFalse);
    expect(service.shouldCheckAutomatically(
      prefs, now: day.add(const Duration(hours: 12)),
    ), isTrue);
    service.dispose();
  });
}
