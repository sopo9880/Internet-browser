import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Android PiP, foreground media notification and bundled native library
/// directory. No system-wide VPN permission or root access is requested.
class AndroidMediaBridge {
  static const channel = MethodChannel('internet_browser/platform');

  static bool get supported => defaultTargetPlatform == TargetPlatform.android;

  static void setMediaCommandHandler(Future<void> Function(String)? handler) {
    if (!supported) return;
    channel.setMethodCallHandler((call) async {
      if (call.method == 'play' || call.method == 'pause') {
        await handler?.call(call.method);
      }
    });
  }

  static Future<String?> nativeLibraryDir() async {
    if (!supported) return null;
    try {
      return await channel.invokeMethod<String>('getNativeLibraryDir');
    } on PlatformException {
      return null;
    }
  }

  static Future<bool> enterPictureInPicture() async {
    if (!supported) return false;
    try {
      return await channel.invokeMethod<bool>('enterPip') ?? false;
    } on PlatformException {
      return false;
    }
  }

  static Future<void> setPlayback({
    required String title,
    required bool playing,
  }) async {
    if (!supported) return;
    try {
      await channel.invokeMethod<bool>('setPlayback', {
        'title': title,
        'playing': playing,
      });
    } on PlatformException {
      // A failed notification must not block local video playback.
    }
  }

  static Future<void> stopPlayback() async {
    if (!supported) return;
    try {
      await channel.invokeMethod<bool>('stopPlayback');
    } on PlatformException {
      // Device's OEM may have disabled the service.
    }
  }
}
