import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import 'video_detector.dart';

enum VideoDownloadState { running, complete, failed, cancelled }

class VideoDownloadItem {
  VideoDownloadItem({
    required this.url,
    required this.filePath,
    required this.fileName,
    required this.state,
    this.progress = 0,
    this.error,
  });

  final Uri url;
  final String filePath;
  final String fileName;
  VideoDownloadState state;
  int progress;
  String? error;
}

/// Stores videos in the app's private Documents/Videos folder.
/// No storage permission or external shared-storage access is required.
class VideoDownloadManager extends ChangeNotifier {
  VideoDownloadManager() : _dio = Dio();

  final Dio _dio;
  final List<VideoDownloadItem> _items = <VideoDownloadItem>[];
  final Map<VideoDownloadItem, CancelToken> _tokens =
      <VideoDownloadItem, CancelToken>{};

  List<VideoDownloadItem> get items => List.unmodifiable(_items);

  Future<Directory> _videoDirectory() async {
    final root = await getApplicationDocumentsDirectory();
    final dir = Directory(
      '${root.path}${Platform.pathSeparator}Videos',
    );
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  Future<void> loadSaved() async {
    final dir = await _videoDirectory();
    await for (final entity in dir.list(followLinks: false)) {
      if (entity is! File) continue;
      final name = entity.uri.pathSegments.last;
      if (!_isVideoFileName(name)) continue;
      if (_items.any((item) => item.filePath == entity.path)) continue;
      _items.add(VideoDownloadItem(
        url: Uri(),
        filePath: entity.path,
        fileName: name,
        state: VideoDownloadState.complete,
        progress: 100,
      ));
    }
    notifyListeners();
  }

  static bool _isVideoFileName(String file) {
    final lower = file.toLowerCase();
    return VideoDetector.extensions.any(lower.endsWith);
  }

  static String safeFileName(Uri url) {
    final candidate = url.pathSegments.isEmpty
        ? 'video.mp4'
        : url.pathSegments.last;
    var clean = candidate
        .replaceAll(RegExp(r'[\\/:*?"<>|\x00-\x1f]'), '_')
        .trim();
    if (clean.isEmpty || clean == '.' || clean == '..') clean = 'video.mp4';
    if (clean.length > 130) {
      final dot = clean.lastIndexOf('.');
      final extension = dot > 0 ? clean.substring(dot) : '.mp4';
      clean = clean.substring(0, 120) + extension;
    }
    if (!_isVideoFileName(clean)) clean += '.mp4';
    return clean;
  }

  Future<String> _unusedPath(Uri url) async {
    final dir = await _videoDirectory();
    final safe = safeFileName(url);
    final dot = safe.lastIndexOf('.');
    final stem = safe.substring(0, dot);
    final ext = safe.substring(dot);
    var candidate = '${dir.path}${Platform.pathSeparator}$safe';
    var suffix = 1;
    while (await File(candidate).exists()) {
      candidate = '${dir.path}${Platform.pathSeparator}${stem}_$suffix$ext';
      suffix++;
    }
    return candidate;
  }

  Future<VideoDownloadItem> download(Uri url) async {
    if (!VideoDetector.isDirectVideo(url)) {
      throw ArgumentError('Only direct HTTP(S) video files are supported.');
    }
    final destination = await _unusedPath(url);
    final token = CancelToken();
    final item = VideoDownloadItem(
      url: url,
      filePath: destination,
      fileName: destination.split(Platform.pathSeparator).last,
      state: VideoDownloadState.running,
    );
    _items.insert(0, item);
    _tokens[item] = token;
    notifyListeners();

    try {
      final response = await _dio.download(
        url.toString(),
        destination,
        cancelToken: token,
        onReceiveProgress: (received, total) {
          if (total <= 0 || item.state != VideoDownloadState.running) return;
          final next = (received * 100 ~/ total).clamp(0, 100);
          if (next != item.progress) {
            item.progress = next;
            notifyListeners();
          }
        },
      );
      final contentType =
          response.headers.value(Headers.contentTypeHeader)?.toLowerCase() ??
              '';
      if (contentType.startsWith('text/html') ||
          contentType.startsWith('application/json')) {
        throw const FormatException('The server returned a webpage, not a video.');
      }
      item.progress = 100;
      item.state = VideoDownloadState.complete;
    } on DioException catch (error) {
      item.state = CancelToken.isCancel(error)
          ? VideoDownloadState.cancelled
          : VideoDownloadState.failed;
      item.error = error.message;
      await _deleteIfExists(destination);
    } catch (error) {
      item.state = VideoDownloadState.failed;
      item.error = error.toString();
      await _deleteIfExists(destination);
    } finally {
      _tokens.remove(item);
      notifyListeners();
    }
    return item;
  }

  Future<void> cancel(VideoDownloadItem item) async {
    _tokens[item]?.cancel('Cancelled by user');
  }

  Future<void> delete(VideoDownloadItem item) async {
    if (item.state == VideoDownloadState.running) {
      await cancel(item);
      return;
    }
    await _deleteIfExists(item.filePath);
    _items.remove(item);
    notifyListeners();
  }

  Future<void> open(VideoDownloadItem item) async {
    if (item.state != VideoDownloadState.complete) return;
    await OpenFilex.open(item.filePath);
  }

  static Future<void> _deleteIfExists(String path) async {
    final file = File(path);
    if (await file.exists()) await file.delete();
  }

  @override
  void dispose() {
    for (final token in _tokens.values) {
      token.cancel('Browser closed');
    }
    _dio.close(force: true);
    super.dispose();
  }
}
