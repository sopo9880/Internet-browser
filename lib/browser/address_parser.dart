/// Restricts typed navigation to HTTP(S). All other inputs become searches.
class AddressParser {
  static const home = 'https://duckduckgo.com/';

  static Uri resolve(String raw) {
    final value = raw.trim();
    if (value.isEmpty) return Uri.parse(home);

    final uri = Uri.tryParse(value);
    if (uri != null && isRemoteHttp(uri)) {
      return uri;
    }

    // Reject explicit, unsupported schemes instead of executing special URLs.
    if (RegExp(r'^[a-z][a-z0-9+.-]*:', caseSensitive: false)
        .hasMatch(value)) {
      return search(value);
    }

    if (value.contains(RegExp(r'\s')) || !value.contains('.')) {
      return search(value);
    }

    final withScheme = Uri.tryParse('https://$value');
    if (withScheme == null || !isRemoteHttp(withScheme)) {
      return search(value);
    }
    return withScheme;
  }

  static Uri search(String query) =>
      Uri.https('duckduckgo.com', '/', <String, String>{'q': query});

  static bool isRemoteHttp(Uri uri) =>
      (uri.scheme == 'http' || uri.scheme == 'https') &&
      uri.host.isNotEmpty &&
      uri.userInfo.isEmpty;
}
