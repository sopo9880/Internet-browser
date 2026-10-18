import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum UpdatePlatform { windows, android }

/// An installer published as an asset of this project's official release.
/// Only files with a GitHub-provided SHA-256 digest may be installed in-app.
class InstallerAsset {
  const InstallerAsset({
    required this.name,
    required this.uri,
    required this.sha256Digest,
    required this.size,
  });

  final String name;
  final Uri uri;
  final String? sha256Digest;
  final int size;

  bool get canInstall => sha256Digest != null;
}

class BrowserUpdate {
  const BrowserUpdate({
    required this.tag,
    required this.version,
    required this.description,
    required this.releasePage,
    required this.platform,
    this.installer,
  });

  final String tag;
  final String version;
  final String description;
  final Uri releasePage;
  final UpdatePlatform platform;
  final InstallerAsset? installer;

  bool get canInstallInApp => installer?.canInstall ?? false;
}

/// Checks the public GitHub Releases API without requesting account credentials.
///
/// Never runs an updater downloaded from arbitrary release notes or off-repo
/// URLs. EXE/APK execution is a separate, explicit user confirmation.
class BrowserUpdateService {
  BrowserUpdateService({Dio? dio})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 10),
                receiveTimeout: const Duration(seconds: 15),
              ),
            );

  static const repository = 'sopo9880/Internet-browser';
  static final Uri latestApi = Uri.https(
    'api.github.com',
    '/repos/$repository/releases/latest',
  );
  static const _snoozedTagKey = 'update_snoozed_tag';
  static const _snoozedUntilKey = 'update_snoozed_until';
  static const _lastCheckedKey = 'update_last_auto_check';
  static const _autoCheckKey = 'update_auto_check';
  static const _autoCheckInterval = Duration(hours: 12);
  static const _snoozeDuration = Duration(days: 7);
  static const _maxInstallerBytes = 800 * 1024 * 1024;

  final Dio _dio;

  static UpdatePlatform? get runningPlatform {
    if (Platform.isWindows) return UpdatePlatform.windows;
    if (Platform.isAndroid) return UpdatePlatform.android;
    return null;
  }

  /// Versions used by this app have 3 or 4 numeric components, optionally v.
  /// No lexical comparison: 0.4.10 is newer than 0.4.9.
  static List<int>? parseVersion(String value) {
    final match = RegExp(r'^v?([0-9]+(?:\.[0-9]+){2,3})$')
        .firstMatch(value.trim());
    if (match == null) return null;
    return match.group(1)!.split('.').map(int.parse).toList();
  }

  static int compareVersions(String first, String second) {
    final left = parseVersion(first);
    final right = parseVersion(second);
    if (left == null || right == null) {
      throw const FormatException('Invalid application version');
    }
    for (var i = 0; i < 4; i++) {
      final a = i < left.length ? left[i] : 0;
      final b = i < right.length ? right[i] : 0;
      if (a != b) return a.compareTo(b);
    }
    return 0;
  }

  static Uri _releaseUrl(String tag) => Uri.https(
        'github.com',
        '/sopo9880/Internet-browser/releases/tag/$tag',
      );

  /// Null means no newer eligible stable release. A release without a
  /// compatible, verified installer can still be viewed in the browser.
  static BrowserUpdate? parseLatest(
    Object? data, {
    required String installedVersion,
    required UpdatePlatform platform,
  }) {
    if (data is! Map) {
      throw const FormatException('Invalid GitHub Releases response');
    }

    final tag = data['tag_name'];
    if (tag is! String || parseVersion(tag) == null) return null;
    if (data['draft'] == true || data['prerelease'] == true) return null;
    if (compareVersions(tag, installedVersion) <= 0) return null;

    final rawVersion = tag.startsWith('v') ? tag.substring(1) : tag;
    final expectedName = platform == UpdatePlatform.android
        ? 'Internet-browser-Android-v$rawVersion.apk'
        : 'Internet-browser-Windows-Setup-v$rawVersion.exe';

    InstallerAsset? asset;
    final listedAssets = data['assets'];
    if (listedAssets is List) {
      for (final item in listedAssets) {
        if (item is! Map || item['state'] != 'uploaded') continue;
        final name = item['name'];
        final rawUrl = item['browser_download_url'];
        final size = item['size'];
        if (name is! String ||
            name.toLowerCase() != expectedName.toLowerCase() ||
            rawUrl is! String ||
            size is! int ||
            size <= 0 ||
            size > _maxInstallerBytes) {
          continue;
        }

        final uri = Uri.tryParse(rawUrl);
        if (uri == null ||
            uri.scheme != 'https' ||
            uri.host != 'github.com' ||
            uri.userInfo.isNotEmpty) {
          continue;
        }
        final segments = uri.pathSegments;
        if (segments.length != 6 ||
            segments[0] != 'sopo9880' ||
            segments[1] != 'Internet-browser' ||
            segments[2] != 'releases' ||
            segments[3] != 'download' ||
            segments[4] != tag ||
            segments[5] != name) {
          continue;
        }

        String? digest;
        final rawDigest = item['digest'];
        if (rawDigest is String &&
            RegExp(r'^sha256:[a-fA-F0-9]{64}$').hasMatch(rawDigest)) {
          digest = rawDigest.substring(7).toLowerCase();
        }
        asset = InstallerAsset(
          name: name,
          uri: uri,
          sha256Digest: digest,
          size: size,
        );
        break;
      }
    }

    return BrowserUpdate(
      tag: tag,
      version: rawVersion,
      description: data['body'] is String ? data['body'] as String : '',
      releasePage: _releaseUrl(tag),
      platform: platform,
      installer: asset,
    );
  }

  Future<BrowserUpdate?> checkLatest({
    required String installedVersion,
    required UpdatePlatform platform,
  }) async {
    final response = await _dio.getUri<dynamic>(
      latestApi,
      options: Options(
        headers: const <String, String>{
          'Accept': 'application/vnd.github+json',
          'User-Agent': 'Internet-browser-update-checker',
        },
        validateStatus: (status) => status == 200 || status == 404,
      ),
    );

    // This is expected until the first official release is published.
    if (response.statusCode == 404) return null;
    return parseLatest(
      response.data,
      installedVersion: installedVersion,
      platform: platform,
    );
  }

  bool get autoCheckEnabled => true;

  bool shouldCheckAutomatically(
    SharedPreferences preferences, {
    DateTime? now,
  }) {
    if (!(preferences.getBool(_autoCheckKey) ?? true)) return false;
    final last = preferences.getInt(_lastCheckedKey);
    if (last == null) return true;
    final time = now ?? DateTime.now();
    return time.millisecondsSinceEpoch - last >=
        _autoCheckInterval.inMilliseconds;
  }

  Future<void> rememberSuccessfulCheck(
    SharedPreferences preferences, {
    DateTime? now,
  }) async {
    await preferences.setInt(
      _lastCheckedKey,
      (now ?? DateTime.now()).millisecondsSinceEpoch,
    );
  }

  bool isSnoozed(
    SharedPreferences preferences,
    BrowserUpdate release, {
    DateTime? now,
  }) {
    if (preferences.getString(_snoozedTagKey) != release.tag) return false;
    final until = preferences.getInt(_snoozedUntilKey);
    if (until == null) return false;
    return (now ?? DateTime.now()).millisecondsSinceEpoch < until;
  }

  Future<void> snooze(
    SharedPreferences preferences,
    BrowserUpdate release, {
    DateTime? now,
  }) async {
    await preferences.setString(_snoozedTagKey, release.tag);
    await preferences.setInt(
      _snoozedUntilKey,
      (now ?? DateTime.now()).add(_snoozeDuration).millisecondsSinceEpoch,
    );
  }

  /// Downloads to a private temp directory, validates size and SHA-256,
  /// and never executes a partial or unverified file.
  Future<File> downloadVerifiedInstaller(
    InstallerAsset asset, {
    required void Function(int received, int total) onProgress,
    CancelToken? cancelToken,
  }) async {
    if (!asset.canInstall) {
      throw StateError('This release asset does not have a SHA-256 digest.');
    }
    if (asset.size <= 0 || asset.size > _maxInstallerBytes) {
      throw StateError('Invalid installer size.');
    }

    final directory = Directory(
      '${(await getTemporaryDirectory()).path}${Platform.pathSeparator}'
      'internet_browser_updates',
    );
    await directory.create(recursive: true);

    // The name has been matched to the fixed platform-specific release
    // naming convention by parseLatest, with no path separators.
    final target = File('${directory.path}${Platform.pathSeparator}${asset.name}');
    final partial = File('${target.path}.part');

    if (await target.exists()) {
      final digest = (await sha256.bind(target.openRead()).first).toString();
      if (digest.toLowerCase() == asset.sha256Digest &&
          await target.length() == asset.size) {
        return target;
      }
      await target.delete();
    }

    try {
      if (await partial.exists()) await partial.delete();
      await _dio.download(
        asset.uri.toString(),
        partial.path,
        cancelToken: cancelToken,
        onReceiveProgress: onProgress,
        options: Options(
          receiveTimeout: const Duration(minutes: 5),
          followRedirects: true,
          maxRedirects: 5,
        ),
      );
      if (await partial.length() != asset.size) {
        throw const FormatException('Installer size did not match release metadata');
      }
      final actual = (await sha256.bind(partial.openRead()).first).toString();
      if (actual.toLowerCase() != asset.sha256Digest) {
        throw const FormatException('Installer SHA-256 verification failed');
      }
      return partial.rename(target.path);
    } catch (_) {
      if (await partial.exists()) await partial.delete();
      rethrow;
    }
  }

  /// Requires a separate user tap after a verified download.
  /// No silent installation, elevated shell, or Android security bypass.
  Future<void> requestInstall(File installer, UpdatePlatform platform) async {
    if (!await installer.exists()) {
      throw StateError('The downloaded installer is missing.');
    }
    if (platform == UpdatePlatform.windows) {
      if (!installer.path.toLowerCase().endsWith('.exe')) {
        throw StateError('Windows setup must be an EXE installer.');
      }
      await Process.start(
        installer.path,
        const <String>[],
        mode: ProcessStartMode.detached,
      );
      return;
    }
    if (!installer.path.toLowerCase().endsWith('.apk')) {
      throw StateError('Android package must be an APK.');
    }
    final result = await OpenFilex.open(
      installer.path,
      type: 'application/vnd.android.package-archive',
    );
    if (result.type != ResultType.done) {
      throw StateError(result.message);
    }
  }

  void dispose() {
    _dio.close(force: true);
  }
}
