import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'download_manager.dart';
import 'video_metadata.dart';

/// Persistent metadata lives alongside, but never replaces, existing videos.
class SavedVideo {
  SavedVideo({
    required this.filePath,
    required this.title,
    this.sourcePage,
    this.thumbnail,
    this.quality,
    this.durationSeconds,
    this.lastPositionMs = 0,
    this.subtitlePath,
  });

  final String filePath;
  String title;
  String? sourcePage;
  String? thumbnail;
  String? quality;
  int? durationSeconds;
  int lastPositionMs;
  String? subtitlePath;

  factory SavedVideo.fromJson(String path, Map<String, dynamic> data) {
    int? numeric(dynamic raw) => raw is num ? raw.toInt() : null;
    return SavedVideo(
      filePath: path,
      title: VideoPageMetadata.normalizeTitle(
        data['title'] is String ? data['title'] as String : null,
        fallback: filenameTitle(path),
      ),
      sourcePage: data['sourcePage'] is String
          ? data['sourcePage'] as String : null,
      thumbnail: data['thumbnail'] is String
          ? data['thumbnail'] as String : null,
      quality: data['quality'] is String ? data['quality'] as String : null,
      durationSeconds: numeric(data['durationSeconds']),
      lastPositionMs: numeric(data['lastPositionMs']) ?? 0,
      subtitlePath: data['subtitlePath'] is String
          ? data['subtitlePath'] as String : null,
    );
  }

  static String filenameTitle(String path) {
    final name = path.replaceAll(String.fromCharCode(92), '/').split('/').last;
    final dot = name.lastIndexOf('.');
    return dot > 0 ? name.substring(0, dot) : name;
  }

  Map<String, dynamic> toJson() => {
        'title': title,
        'sourcePage': sourcePage,
        'thumbnail': thumbnail,
        'quality': quality,
        'durationSeconds': durationSeconds,
        'lastPositionMs': lastPositionMs,
        'subtitlePath': subtitlePath,
      };
}

/// v0.1.1 has only video files. Scan them and seamlessly migrate into this
/// index without moving, overwriting or deleting any user video.
class VideoLibrary extends ChangeNotifier {
  final Map<String, SavedVideo> _byName = {};

  SavedVideo forItem(VideoDownloadItem item) {
    final entry = _byName[item.fileName];
    return entry ??
        SavedVideo(
          filePath: item.filePath,
          title: SavedVideo.filenameTitle(item.fileName),
        );
  }

  List<SavedVideo> all(List<VideoDownloadItem> items) => [
        for (final item in items)
          if (item.state == VideoDownloadState.complete) forItem(item),
      ];

  Future<File> _index() async {
    final dir = Directory(
      '${(await getApplicationDocumentsDirectory()).path}'
      '${Platform.pathSeparator}Videos',
    );
    await dir.create(recursive: true);
    return File('${dir.path}${Platform.pathSeparator}library.json');
  }

  Future<void> loadSaved(List<VideoDownloadItem> items) async {
    _byName.clear();
    try {
      final file = await _index();
      if (await file.exists()) {
        final data = jsonDecode(await file.readAsString());
        if (data is Map && data['items'] is Map) {
          final entries = data['items'] as Map;
          for (final e in entries.entries) {
            if (e.key is String && e.value is Map) {
              _byName[e.key as String] = SavedVideo.fromJson(
                (e.value as Map)['filePath'] is String
                    ? (e.value as Map)['filePath'] as String
                    : e.key as String,
                Map<String, dynamic>.from(e.value as Map),
              );
            }
          }
        }
      }
    } catch (_) {
      // Damaged metadata must never hide or remove a downloaded video.
    }
    for (final item in items) {
      if (item.state != VideoDownloadState.complete) continue;
      final previous = _byName[item.fileName];
      _byName[item.fileName] = previous == null
          ? SavedVideo(
              filePath: item.filePath,
              title: SavedVideo.filenameTitle(item.fileName),
            )
          : SavedVideo.fromJson(item.filePath, previous.toJson());
    }
    notifyListeners();
  }

  Future<void> register(
    VideoDownloadItem item, {
    VideoPageMetadata? page,
    String? title,
    String? thumbnail,
    String? quality,
    int? durationSeconds,
  }) async {
    if (item.state != VideoDownloadState.complete) return;
    final saved = SavedVideo(
      filePath: item.filePath,
      title: VideoPageMetadata.normalizeTitle(
        title ?? page?.title,
        fallback: SavedVideo.filenameTitle(item.fileName),
      ),
      sourcePage: page?.page.toString(),
      thumbnail: thumbnail ?? page?.thumbnail,
      quality: quality,
      durationSeconds: durationSeconds,
    );
    _byName[item.fileName] = saved;
    notifyListeners();
    await save();
  }

  Future<void> editTitle(SavedVideo item, String title) async {
    item.title = VideoPageMetadata.normalizeTitle(title,
        fallback: item.title);
    notifyListeners();
    await save();
  }

  Future<void> setSubtitle(SavedVideo item, String? path) async {
    item.subtitlePath = path;
    notifyListeners();
    await save();
  }

  Future<void> setPlaybackPosition(
    SavedVideo item,
    Duration position,
  ) async {
    if (position.inMilliseconds < 0) return;
    item.lastPositionMs = position.inMilliseconds;
    await save();
  }

  Future<void> forget(VideoDownloadItem item) async {
    _byName.remove(item.fileName);
    notifyListeners();
    await save();
  }

  Future<void> save() async {
    final file = await _index();
    final items = <String, dynamic>{
      for (final entry in _byName.entries)
        entry.key: {...entry.value.toJson(), 'filePath': entry.value.filePath},
    };
    await file.writeAsString(jsonEncode({'version': 1, 'items': items}),
        flush: true);
  }
}
