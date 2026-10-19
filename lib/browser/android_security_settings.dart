import 'dart:io';

import 'package:android_intent_plus/android_intent.dart';

/// Opens general Android security settings, like HYP Viewer. Samsung's
/// Auto Blocker page has no guaranteed public deep-link across One UI builds.
/// This utility never disables, bypasses or changes security protections.
class AndroidSecuritySettings {
  static const securityAction = 'android.settings.SECURITY_SETTINGS';
  static const settingsAction = 'android.settings.SETTINGS';

  static Future<bool> open({
    bool? isAndroid,
    Future<void> Function(String action)? launch,
  }) async {
    if (!(isAndroid ?? Platform.isAndroid)) return false;

    Future<void> openAction(String action) async {
      if (launch != null) return launch(action);
      await AndroidIntent(action: action).launch();
    }

    for (final action in [securityAction, settingsAction]) {
      try {
        await openAction(action);
        return true;
      } catch (_) {
        // Vendor Settings implementations vary; try the generic fallback.
      }
    }
    return false;
  }
}
