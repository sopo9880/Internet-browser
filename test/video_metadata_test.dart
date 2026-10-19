import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/video_metadata.dart';

void main() {
  final page = Uri.parse('https://media.example/watch?v=42');

  test('video-specific title beats generic page title', () {
    final value = VideoPageMetadata.parse({
      'videoTitle': '실제 영상 제목',
      'ogTitle': '사이트 제목',
      'documentTitle': '브라우저 이름',
      'poster': '/media/thumb.jpg',
    }, page);
    expect(value.title, '실제 영상 제목');
    expect(value.thumbnail, 'https://media.example/media/thumb.jpg');
  });

  test('fallback title used when document has no metadata', () {
    expect(VideoPageMetadata.parse({}, page,
        fallbackTitle: '이미지와 동영상').title, '이미지와 동영상');
  });

  test('sanitizes filenames without removing Korean text', () {
    expect(VideoPageMetadata.safeFileStem('테스트: 영상 / 1?'),
        '테스트_ 영상 _ 1_');
    expect(VideoPageMetadata.safeFileStem('...'), '동영상');
  });

  test('ignores dangerous thumbnail scheme', () {
    expect(VideoPageMetadata.parse({
      'ogImage': 'javascript:alert(1)'
    }, page).thumbnail, isNull);
  });
}
