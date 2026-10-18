import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// Native embedded Chromium surface, *not* Android WebView or an external app.
/// Unavailable until the Chromium engine implementing EmbeddedChromiumEngine
/// has actually been compiled into the Android application.
class ChromiumEngineStatus {
  const ChromiumEngineStatus({required this.engine, required this.embedded});

  final String engine;
  final bool embedded;

  bool get ready => engine == 'chromium-native' && embedded;

  static const unavailable =
      ChromiumEngineStatus(engine: 'missing', embedded: false);

  factory ChromiumEngineStatus.parse(Object? value) {
    if (value is! Map) return unavailable;
    final m = Map<String, dynamic>.from(value);
    return ChromiumEngineStatus(
      engine: m['engine'] is String ? m['engine'] as String : 'unknown',
      embedded: m['embedded'] == true,
    );
  }
}

class ChromiumNavigationEvent {
  ChromiumNavigationEvent._(this.tabId, this.type, this.payload);

  final int tabId;
  final String type;
  final Map<String, dynamic> payload;

  Uri? get url {
    final value = payload['url'];
    return value is String ? Uri.tryParse(value) : null;
  }

  String? get title =>
      payload['title'] is String ? payload['title'] as String : null;

  int? get progress =>
      payload['progress'] is num ? (payload['progress'] as num).toInt() : null;

  static ChromiumNavigationEvent? parse(dynamic value) {
    if (value is! Map) return null;
    final m = Map<String, dynamic>.from(value);
    if (m['tabId'] is! num || m['type'] is! String) return null;
    return ChromiumNavigationEvent._(
      (m['tabId'] as num).toInt(),
      m['type'] as String,
      m,
    );
  }
}

class ChromiumNavigation {
  ChromiumNavigation({
    MethodChannel? channel,
    EventChannel? eventChannel,
  })  : _channel = channel ??
            const MethodChannel('internet_browser/chromium_navigation'),
        _events = eventChannel ??
            const EventChannel('internet_browser/chromium_events');

  final MethodChannel _channel;
  final EventChannel _events;

  Future<ChromiumEngineStatus> status() async {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return ChromiumEngineStatus.unavailable;
    }
    try {
      return ChromiumEngineStatus.parse(
        await _channel.invokeMethod<dynamic>('status'),
      );
    } on MissingPluginException {
      return ChromiumEngineStatus.unavailable;
    } on PlatformException {
      return ChromiumEngineStatus.unavailable;
    }
  }

  Stream<ChromiumNavigationEvent> get events =>
      _events.receiveBroadcastStream().map(ChromiumNavigationEvent.parse)
          .where((event) => event != null).cast<ChromiumNavigationEvent>();

  Future<T?> _command<T>(int tabId, String name, [Map<String, dynamic>? args]) =>
      _channel.invokeMethod<T>(name, <String, dynamic>{
        'tabId': tabId,
        ...?args,
      });

  Future<void> navigate(int tabId, Uri url) async {
    await _command<dynamic>(tabId, 'navigate', {'url': url.toString()});
  }

  Future<void> back(int tabId) async {
    await _command<dynamic>(tabId, 'back');
  }

  Future<void> forward(int tabId) async {
    await _command<dynamic>(tabId, 'forward');
  }

  Future<void> reload(int tabId) async {
    await _command<dynamic>(tabId, 'reload');
  }

  Future<bool> canBack(int tabId) async =>
      await _command<bool>(tabId, 'canBack') ?? false;

  Future<bool> canForward(int tabId) async =>
      await _command<bool>(tabId, 'canForward') ?? false;

  Future<dynamic> javascript(int tabId, String script) =>
      _command<dynamic>(tabId, 'javascript', {'source': script});
}

class ChromiumAndroidPage extends StatelessWidget {
  const ChromiumAndroidPage({
    super.key,
    required this.tabId,
    required this.url,
  });

  final int tabId;
  final Uri url;

  @override
  Widget build(BuildContext context) {
    if (defaultTargetPlatform != TargetPlatform.android) {
      return const Center(
        child: Text('Embedded Chromium is supported on Android only.'),
      );
    }
    return AndroidView(
      key: ValueKey('chromium-$tabId'),
      viewType: 'internet_browser/chromium_view',
      layoutDirection: TextDirection.ltr,
      creationParams: <String, dynamic>{
        'tabId': tabId,
        'initialUrl': url.toString(),
      },
      creationParamsCodec: const StandardMessageCodec(),
    );
  }
}
