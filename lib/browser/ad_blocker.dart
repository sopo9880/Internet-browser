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

  /// Apply player-specific cleanup only to the actual YouTube origins.
  static bool isYoutube(Uri page) => <String>{
    'youtube.com', 'www.youtube.com', 'm.youtube.com',
    'music.youtube.com',
  }.contains(page.host.toLowerCase());

  static bool hostMatches(String host, String domain) {
    final h = host.toLowerCase();
    final d = domain.toLowerCase();
    return h == d || h.endsWith('.$d');
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
  /// Best-effort skip of visible buttons; embedded/unskippable ads may still
  /// play. Never claim complete YouTube ad blocking.
  static const youtubeCleanupScript = r'''
(function () {
  if (window.__internetBrowserYoutubeHelper) return;
  window.__internetBrowserYoutubeHelper = true;
  function closeSkippableAds() {
    const selectors = [
      '.ytp-ad-skip-button',
      '.ytp-ad-skip-button-modern',
      '.ytp-skip-ad-button',
      '.ytp-ad-overlay-close-button'
    ];
    for (const selector of selectors) {
      document.querySelectorAll(selector).forEach(element => {
        if (element.getClientRects().length > 0) element.click();
      });
    }
  }
  closeSkippableAds();
  const observer = new MutationObserver(closeSkippableAds);
  observer.observe(document.documentElement, {childList: true, subtree: true});
})();
''';

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
