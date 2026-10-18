import 'address_parser.dart';

/// v0.1.0 intentionally supports direct, non-DRM file URLs only.
/// HLS, DASH, blob URLs and authenticated streams require separate handling.
class VideoDetector {
  static const extensions = <String>{
    '.mp4', '.webm', '.mov', '.m4v', '.mkv', '.avi', '.3gp', '.m2ts', '.ts', '.flv'
  };
 
  /// Match a YouTube video id only on actual YouTube hosts.
  static String? youtubeVideoId(Uri uri) {
    if (uri.scheme != 'https' && uri.scheme != 'http') return null;
    final host = uri.host.toLowerCase();
    String? id;
    if (host == 'youtu.be' || host == 'www.youtu.be') {
      id = uri.pathSegments.isEmpty ? null : uri.pathSegments.first;
    } else if (host == 'youtube.com' ||
        host == 'www.youtube.com' ||
        host == 'm.youtube.com' ||
        host == 'music.youtube.com') {
      if (uri.path == '/watch') {
        id = uri.queryParameters['v'];
      } else if (uri.pathSegments.length == 2 &&
          const ['shorts', 'embed', 'live'].contains(uri.pathSegments.first)) {
        id = uri.pathSegments.last;
      }
    }
    if (id == null) return null;
    return RegExp(r'^[a-zA-Z0-9_-]{11}$').hasMatch(id) ? id : null;
  }


  static bool isDirectVideo(Uri uri) {
    if (!AddressParser.isRemoteHttp(uri)) return false;
    final path = uri.path.toLowerCase();
    return extensions.any(path.endsWith);
  }

  static List<Uri> parseCandidates(dynamic result) {
    if (result is! List) return <Uri>[];
    final unique = <String>{};
    final videos = <Uri>[];
    for (final item in result) {
      if (item is! String) continue;
      final uri = Uri.tryParse(item);
      if (uri == null || !isDirectVideo(uri)) continue;
      if (unique.add(uri.toString())) videos.add(uri);
      if (videos.length >= 30) break;
    }
    return videos;
  }

  static const discoverScript = r'''
(function () {
  const found = new Set();
  for (const media of document.querySelectorAll('video, video source')) {
    const candidate = media.currentSrc || media.src ||
      media.getAttribute('src');
    if (!candidate) continue;
    try { found.add(new URL(candidate, document.baseURI).href); } catch (_) {}
  }
  return Array.from(found).slice(0, 30);
})();
''';
}
