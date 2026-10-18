import 'dart:convert';

/// Metadata belongs to the VIDEO PAGE rather than its media CDN URL.
class VideoPageMetadata {
  const VideoPageMetadata({
    required this.page,
    required this.title,
    this.thumbnail,
  });

  final Uri page;
  final String title;
  final String? thumbnail;

  static String normalizeTitle(String? raw, {String fallback = '동영상'}) {
    final value = (raw ?? '')
        .replaceAll(RegExp(r'[\u0000-\u001f\u007f]'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (value.isEmpty || value.toLowerCase() == 'about:blank') {
      return fallback;
    }
    return value.length > 180 ? value.substring(0, 180).trim() : value;
  }

  static String safeFileStem(String title) {
    var stem = normalizeTitle(title)
        .replaceAll(RegExp(r'[\\/:*?"<>|]'), '_')
        .replaceAll(RegExp(r'[. ]+$'), '')
        .trim();
    if (stem.isEmpty || stem == '.' || stem == '..') stem = '동영상';
    if (stem.length > 100) stem = stem.substring(0, 100).trim();
    return stem;
  }

  static VideoPageMetadata parse(dynamic value, Uri fallbackPage,
      {String? fallbackTitle}) {
    dynamic decoded = value;
    if (value is String) {
      try {
        decoded = jsonDecode(value);
      } catch (_) {
        decoded = null;
      }
    }
    final map = decoded is Map ? decoded : const {};
    String? str(dynamic raw) => raw is String && raw.trim().isNotEmpty
        ? raw.trim()
        : null;
    final candidates = <String?>[
      str(map['videoTitle']),
      str(map['ogVideoTitle']),
      str(map['ogTitle']),
      str(map['twitterTitle']),
      str(map['schemaTitle']),
      str(map['documentTitle']),
      fallbackTitle,
    ];
    final title = candidates.firstWhere(
      (candidate) => candidate != null,
      orElse: () => null,
    );
    final image = str(map['poster']) ??
        str(map['ogImage']) ??
        str(map['twitterImage']);
    final resolved = image == null ? null : fallbackPage.resolve(image);
    final allowedThumbnail = resolved != null &&
        (resolved.scheme == 'https' || resolved.scheme == 'http');
    return VideoPageMetadata(
      page: fallbackPage,
      title: normalizeTitle(title, fallback: '동영상'),
      thumbnail: allowedThumbnail ? resolved.toString() : null,
    );
  }

  /// Site-agnostic video-scoped metadata, with page-level fallback.
  /// Never asks the video CDN to supply a website's title.
  static const discoverScript = r'''
(function () {
  function property(selector, attribute) {
    const element = document.querySelector(selector);
    return element && element.getAttribute(attribute) || null;
  }
  const video = document.querySelector('video');
  const first = (list) => list.find(x => typeof x === 'string' && x.trim()) || null;
  const data = {
    videoTitle: video && first([
      video.getAttribute('title'),
      video.getAttribute('aria-label'),
      video.closest('[itemscope]')?.querySelector('[itemprop="name"]')?.textContent,
    ]),
    ogVideoTitle: property('meta[property="og:video:title"]', 'content'),
    ogTitle: property('meta[property="og:title"]', 'content'),
    twitterTitle: property('meta[name="twitter:title"]', 'content'),
    schemaTitle: property('meta[itemprop="name"]', 'content'),
    documentTitle: document.title,
    poster: video?.getAttribute('poster'),
    ogImage: property('meta[property="og:image"]', 'content'),
    twitterImage: property('meta[name="twitter:image"]', 'content')
  };
  return JSON.stringify(data);
})();
''';
}
