import 'address_parser.dart';

/// A conservative first-party-safe host filter, not a full EasyList engine.
///
/// Network hooks are provided by Android WebView and Windows WebView2.
/// A full syntax-compatible cosmetic/network rules engine is scheduled later.
class AdBlocker {
  AdBlocker({this.enabled = true, Iterable<String> allowedHosts = const []})
      : allowedHosts = <String>{...allowedHosts};

  bool enabled;
  final Set<String> allowedHosts;

  static const blockedHosts = <String>{
    'doubleclick.net',
    'googlesyndication.com',
    'googleadservices.com',
    'adservice.google.com',
    'google-analytics.com',
    'googletagmanager.com',
    'adnxs.com',
    'adsrvr.org',
    'taboola.com',
    'outbrain.com',
    'criteo.com',
    'rubiconproject.com',
    'pubmatic.com',
    'scorecardresearch.com',
    'quantserve.com',
  };

  static bool hostMatches(String host, String domain) {
    final h = host.toLowerCase();
    final d = domain.toLowerCase();
    return h == d || h.endsWith('.' + d);
  }

  bool isExempt(Uri page) {
    return allowedHosts.any((host) => hostMatches(page.host, host));
  }

  bool shouldBlock(Uri resource, {required Uri page}) {
    if (!enabled || isExempt(page)) return false;
    if (!AddressParser.isRemoteHttp(resource)) return false;
    // Never block the document's own origin just because of a generic rule.
    if (resource.host.toLowerCase() == page.host.toLowerCase()) {
      return false;
    }
    return blockedHosts.any((host) => hostMatches(resource.host, host));
  }

  void setExempt(String host, bool exempt) {
    final normalized = host.trim().toLowerCase();
    if (normalized.isEmpty) return;
    if (exempt) {
      allowedHosts.add(normalized);
    } else {
      allowedHosts.remove(normalized);
    }
  }

  /// Conservative element hiding; no remote JS, no arbitrary filter execution.
  static const cosmeticScript = r'''
(function () {
  if (document.getElementById('internet-browser-ad-style')) return;
  const style = document.createElement('style');
  style.id = 'internet-browser-ad-style';
  style.textContent =
    'ins.adsbygoogle, [data-ad-slot], iframe[src*="doubleclick.net"], ' +
    '[id^="google_ads_"], [class~="adsbygoogle"] { display: none !important; }';
  (document.head || document.documentElement).appendChild(style);
})();
''';
}
