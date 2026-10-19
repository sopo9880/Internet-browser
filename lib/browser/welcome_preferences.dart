import 'package:shared_preferences/shared_preferences.dart';

/// Tracks a fresh Android install without resetting v0.1.x user data.
///
/// A user upgrading from an already-used v0.1.x installation does not get
/// interrupted by a new first-run tour. Only the onboarding marker is written.
class WelcomePreferences {
  const WelcomePreferences._();

  static const completedKey = 'welcome_v0200_completed';

  static const _priorInstallKeys = <String>{
    'bookmarks',
    'history',
    'ads_enabled',
    'ads_exceptions',
    'dpi_enabled',
    'update_auto_check',
  };

  static bool hasExistingSettings(SharedPreferences preferences) {
    return preferences.getKeys().any((key) =>
        _priorInstallKeys.contains(key) || key.startsWith('dpi_'));
  }

  static Future<bool> shouldShow(
    SharedPreferences preferences, {
    required bool onAndroid,
  }) async {
    if (!onAndroid || preferences.getBool(completedKey) == true) {
      return false;
    }
    if (hasExistingSettings(preferences)) {
      await markCompleted(preferences);
      return false;
    }
    return true;
  }

  static Future<void> markCompleted(SharedPreferences preferences) async {
    if (!await preferences.setBool(completedKey, true)) {
      throw StateError('Could not save the first-run welcome choice');
    }
  }
}
