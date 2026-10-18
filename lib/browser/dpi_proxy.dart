import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import 'android_media_bridge.dart';
import 'dpi_options.dart';

/// App-only DPI transport. A SOCKS5 greeting does NOT prove that individual
/// sites can be reached through a DPI rule; show that limitation in the UI.
class BrowserDpiProxy {
  static const host = '127.0.0.1';
  static const port = 1080;

  Process? _ownedProcess;
  bool _connected = false;
  String _status = '사용 안 함';

  bool get connected => _connected;
  String get status => _status;

  static bool isSocks5Greeting(List<int> bytes) =>
      bytes.length >= 2 && bytes[0] == 5 && bytes[1] == 0;

  static String get windowsProxyArguments =>
      '--proxy-server=socks5://127.0.0.1:1080';

  /// Check the actual SOCKS5 handshake rather than simply an open TCP port.
  static Future<bool> checkLocalSocks() async {
    Socket? socket;
    try {
      socket = await Socket.connect(
        host,
        port,
        timeout: const Duration(milliseconds: 650),
      );
      socket.add(const [5, 1, 0]);
      await socket.flush();
      final reply = await socket.first.timeout(
        const Duration(milliseconds: 850),
      );
      return isSocks5Greeting(reply);
    } catch (_) {
      return false;
    } finally {
      socket?.destroy();
    }
  }

  Future<bool> initialize({required bool enabled,
      DpiOptions options = const DpiOptions()}) async {
    if (!enabled) {
      _status = '사용 안 함';
      _connected = false;
      return false;
    }
    if (defaultTargetPlatform == TargetPlatform.windows) {
      return _startWindows(options);
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      return _applyAndroid(options);
    }
    _status = '지원하지 않는 플랫폼';
    return false;
  }

  Future<bool> _startWindows(DpiOptions options) async {
    if (!await checkLocalSocks()) {
      final exeDirectory = File(Platform.resolvedExecutable).parent.path;
      final binary = File(
        '$exeDirectory${Platform.pathSeparator}tools${Platform.pathSeparator}ciadpi.exe',
      );
      if (!await binary.exists()) {
        _status = 'ByeDPI 실행 파일이 설치되지 않았습니다.';
        return false;
      }
      try {
        _ownedProcess = await Process.start(
          binary.path,
          options.toArguments(windows: true),
        );
        _ownedProcess!.stdout.listen((_) {});
        _ownedProcess!.stderr.listen((_) {});
        var ready = false;
        for (var i = 0; i < 8; i++) {
          if (await checkLocalSocks()) {
            ready = true;
            break;
          }
          await Future<void>.delayed(const Duration(milliseconds: 250));
        }
        if (!ready) {
          _ownedProcess?.kill();
          _ownedProcess = null;
          _status = 'ByeDPI 시작 실패: SOCKS5 응답을 받지 못했습니다.';
          return false;
        }
      } catch (error) {
        _ownedProcess?.kill();
        _ownedProcess = null;
        _status = 'ByeDPI 실행 실패: $error';
        return false;
      }
    }
    _connected = true;
    _status = '로컬 SOCKS5 연결 확인 · 사이트별 우회 검증 필요';
    return true;
  }

  /// Android bundles an NDK-native ByeDPI executable in nativeLibraryDir.
  /// No other app or external SOCKS5 service is needed.
  Future<bool> _applyAndroid(DpiOptions options) async {
    final occupied = await checkLocalSocks();
    if (occupied && _ownedProcess == null) {
      _status = '127.0.0.1:1080 포트를 다른 SOCKS5 엔진이 사용 중입니다.';
      return false;
    }
    if (!occupied) {
      final libDir = await AndroidMediaBridge.nativeLibraryDir();
      if (libDir == null || libDir.isEmpty) {
        _status = 'Android 네이티브 엔진 경로를 확인하지 못했습니다.';
        return false;
      }
      final exe = File('${libDir}${Platform.pathSeparator}libciadpi.so');
      if (!await exe.exists()) {
        _status = '이 기기의 Android ABI에 맞는 내장 ByeDPI 엔진이 없습니다.';
        return false;
      }
      try {
        _ownedProcess = await Process.start(
          exe.path,
          options.toArguments(windows: false),
        );
        _ownedProcess!.stdout.listen((_) {});
        _ownedProcess!.stderr.listen((_) {});
        var ready = false;
        for (var i = 0; i < 12; i++) {
          if (await checkLocalSocks()) {
            ready = true;
            break;
          }
          await Future<void>.delayed(const Duration(milliseconds: 250));
        }
        if (!ready) {
          _ownedProcess?.kill();
          _ownedProcess = null;
          _status = '내장 ByeDPI 시작 실패: SOCKS5 응답 없음';
          return false;
        }
      } catch (error) {
        _ownedProcess?.kill();
        _ownedProcess = null;
        _status = '내장 ByeDPI 실행 오류: $error';
        return false;
      }
    }
    try {
      final supported = await WebViewFeature.isFeatureSupported(
        WebViewFeature.PROXY_OVERRIDE,
      );
      if (!supported) {
        _status = 'Android WebView 프록시 설정을 지원하지 않습니다.';
        _ownedProcess?.kill();
        _ownedProcess = null;
        return false;
      }
      await ProxyController.instance().setProxyOverride(
        settings: ProxySettings(
          proxyRules: [ProxyRule(url: 'socks5://127.0.0.1:1080')],
          bypassRules: ['localhost', '127.0.0.1'],
        ),
      );
      _connected = true;
      _status = '내장 ByeDPI SOCKS5 연결 · 사이트별 실제 우회 검증 필요';
      return true;
    } catch (error) {
      _connected = false;
      _ownedProcess?.kill();
      _ownedProcess = null;
      _status = 'WebView SOCKS5 설정 실패: $error';
      return false;
    }
  }

  Future<void> disableAndroid() async {
    if (defaultTargetPlatform != TargetPlatform.android) return;
    try {
      await ProxyController.instance().clearProxyOverride();
    } catch (_) {
      // WebView implementations can report unsupported proxy operations.
    }
    _connected = false;
    _ownedProcess?.kill();
    _ownedProcess = null;
    _status = '사용 안 함';
  }

  void dispose() {
    _ownedProcess?.kill();
    _ownedProcess = null;
  }
}
