import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// The exact Chrome Web Store extension requested as a v0.2.0 release gate.
/// We must execute THIS extension; a substitute built-in ad filter is not
/// evidence of Chrome extension compatibility.
class RequiredChromeExtension {
  static const id = 'gighmmpiobklfepjocnamgkkbiglidom';
  static const name = 'AdBlock — Block Ads Across the Web';
  static const webStoreUrl =
      'https://chromewebstore.google.com/detail/adblock/gighmmpiobklfepjocnamgkkbiglidom';

  static bool validId(String id) => RegExp(r'^[a-p]{32}$').hasMatch(id);
}

/// Capability claims are NOT proof of installation or ad blocking.
/// Android WebView must never report a usable extensions system.
class ChromiumExtensionCapabilities {
  const ChromiumExtensionCapabilities({
    required this.engine,
    required this.nativeEngine,
    required this.manifestV3,
    required this.declarativeNetRequest,
    required this.serviceWorkers,
    required this.permissionPrompts,
    required this.chromeWebStoreInstall,
    required this.actionPopup,
  });

  final String engine;
  final bool nativeEngine;
  final bool manifestV3;
  final bool declarativeNetRequest;
  final bool serviceWorkers;
  final bool permissionPrompts;
  final bool chromeWebStoreInstall;
  final bool actionPopup;

  static const unavailable = ChromiumExtensionCapabilities(
    engine: 'Android WebView (no Chrome extension runtime)',
    nativeEngine: false,
    manifestV3: false,
    declarativeNetRequest: false,
    serviceWorkers: false,
    permissionPrompts: false,
    chromeWebStoreInstall: false,
    actionPopup: false,
  );

  factory ChromiumExtensionCapabilities.fromMap(Map<String, dynamic> map) =>
      ChromiumExtensionCapabilities(
        engine: map['engine'] is String
            ? map['engine'] as String : 'unknown',
        nativeEngine: map['nativeEngine'] == true,
        manifestV3: map['manifestV3'] == true,
        declarativeNetRequest: map['declarativeNetRequest'] == true,
        serviceWorkers: map['serviceWorkers'] == true,
        permissionPrompts: map['permissionPrompts'] == true,
        chromeWebStoreInstall: map['chromeWebStoreInstall'] == true,
        actionPopup: map['actionPopup'] == true,
      );

  bool get canLoadAdBlock =>
      engine == 'android-chromium' &&
      nativeEngine &&
      manifestV3 &&
      declarativeNetRequest &&
      serviceWorkers &&
      permissionPrompts &&
      chromeWebStoreInstall &&
      actionPopup;
}

/// A backend contract for an extension-capable, IN-APP Chromium Android
/// browser. Never use intents to an external browser as a silent substitute.
abstract class ChromeExtensionHost {
  Future<ChromiumExtensionCapabilities> capabilities();
  Future<bool> install(String id);
  Future<bool> isInstalledAndEnabled(String id);
  Future<void> uninstall(String id);
}

/// This channel is intentionally fail-closed until a native Chromium engine
/// implementing extension APIs is integrated and device-tested.
class AndroidChromiumExtensionHost implements ChromeExtensionHost {
  AndroidChromiumExtensionHost({MethodChannel? channel})
      : _channel = channel ??
            const MethodChannel('internet_browser/chromium_extensions');

  final MethodChannel _channel;

  @override
  Future<ChromiumExtensionCapabilities> capabilities() async {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return ChromiumExtensionCapabilities.unavailable;
    }
    try {
      final raw = await _channel.invokeMethod<dynamic>('capabilities');
      if (raw is! Map) return ChromiumExtensionCapabilities.unavailable;
      return ChromiumExtensionCapabilities.fromMap(
        Map<String, dynamic>.from(raw),
      );
    } on PlatformException {
      return ChromiumExtensionCapabilities.unavailable;
    } on MissingPluginException {
      return ChromiumExtensionCapabilities.unavailable;
    }
  }

  @override
  Future<bool> install(String id) async {
    if (!RequiredChromeExtension.validId(id)) {
      throw ArgumentError.value(id, 'id', 'Invalid Chrome extension ID');
    }
    if (!(await capabilities()).canLoadAdBlock) {
      throw StateError(
        'Android Chromium extension engine is not integrated. '
        'WebView cannot execute the requested Chrome extension.',
      );
    }
    final result = await _channel.invokeMethod<dynamic>(
      'installFromChromeWebStore', {'id': id},
    );
    return result == true;
  }

  @override
  Future<bool> isInstalledAndEnabled(String id) async {
    if (!RequiredChromeExtension.validId(id) ||
        !(await capabilities()).canLoadAdBlock) return false;
    try {
      return await _channel.invokeMethod<bool>(
            'isInstalledAndEnabled', {'id': id},
          ) ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  @override
  Future<void> uninstall(String id) async {
    if (!RequiredChromeExtension.validId(id)) {
      throw ArgumentError.value(id, 'id');
    }
    if (!(await capabilities()).canLoadAdBlock) {
      throw StateError('Chromium extension engine unavailable');
    }
    await _channel.invokeMethod<void>('uninstall', {'id': id});
  }
}
