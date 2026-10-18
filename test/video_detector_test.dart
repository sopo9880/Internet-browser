import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/video_detector.dart';

void main() {
  test('accepts only direct video files over HTTP(S)', () {
    expect(VideoDetector.isDirectVideo(Uri.parse('https://a.b/clip.MP4?q=1')), isTrue);
    expect(VideoDetector.isDirectVideo(Uri.parse('https://a.b/movie.m3u8')), isFalse);
    expect(VideoDetector.isDirectVideo(Uri.parse('blob:https://a.b/123')), isFalse);
  });
  test('recognizes YouTube watch and shorts but not lookalike hosts', () {
    expect(VideoDetector.youtubeVideoId(
      Uri.parse('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
    ), 'dQw4w9WgXcQ');
    expect(VideoDetector.youtubeVideoId(
      Uri.parse('https://youtu.be/dQw4w9WgXcQ'),
    ), 'dQw4w9WgXcQ');
    expect(VideoDetector.youtubeVideoId(
      Uri.parse('https://m.youtube.com/shorts/dQw4w9WgXcQ'),
    ), 'dQw4w9WgXcQ');
    expect(VideoDetector.youtubeVideoId(
      Uri.parse('https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ'),
    ), isNull);
    expect(VideoDetector.youtubeVideoId(
      Uri.parse('https://youtube.com/watch?v=invalid'),
    ), isNull);
  });

  test('filters duplicate, unsafe, and unsupported candidates', () {
    final result = VideoDetector.parseCandidates([
      'https://videos.example/a.mp4',
      'https://videos.example/a.mp4',
      'javascript:alert(1)',
      'https://videos.example/index.html',
      'https://videos.example/b.webm',
    ]);
    expect(result, hasLength(2));
  });
}
