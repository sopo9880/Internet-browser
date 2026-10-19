import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/video_library.dart';

void main() {
  test('old stored filename is preserved as a fallback title', () {
    expect(SavedVideo.filenameTitle('old_video_001.mp4'), 'old_video_001');
  });
  test('persisted title and progress survive serialization', () {
    final before = SavedVideo(
      filePath: '/videos/test.webm',
      title: '영상 제목',
      lastPositionMs: 12345,
    );
    final after = SavedVideo.fromJson(before.filePath, before.toJson());
    expect(after.title, '영상 제목');
    expect(after.lastPositionMs, 12345);
  });
}
