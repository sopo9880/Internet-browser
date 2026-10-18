import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/ad_blocker.dart';

void main() {
  final page = Uri.parse('https://news.example/articles');

  test('blocks subdomains with DNS label boundary', () {
    final blocker = AdBlocker();
    expect(
      blocker.shouldBlock(
        Uri.parse('https://ad.doubleclick.net/banner.js'),
        page: page,
      ),
      isTrue,
    );
    expect(
      blocker.shouldBlock(
        Uri.parse('https://notdoubleclick.net/banner.js'),
        page: page,
      ),
      isFalse,
    );
  });
  test('does not block same-origin resource', () {
    final blocker = AdBlocker();
    final site = Uri.parse('https://doubleclick.net/');
    expect(blocker.shouldBlock(site, page: site), isFalse);
  });
  test('YouTube cleanup is restricted to genuine YouTube origins', () {
    expect(AdBlocker.isYoutube(Uri.parse('https://www.youtube.com/watch')), isTrue);
    expect(AdBlocker.isYoutube(Uri.parse('https://m.youtube.com/shorts/x')), isTrue);
    expect(AdBlocker.isYoutube(Uri.parse('https://youtube.com.evil.test/watch')), isFalse);
    expect(AdBlocker.youtubeCleanupScript.contains('ytp-ad-skip-button'), isTrue);
  });
  test('site exemption disables filtering for that site', () {
    final blocker = AdBlocker(allowedHosts: ['example']);
    expect(
      blocker.shouldBlock(
        Uri.parse('https://doubleclick.net/ad'),
        page: Uri.parse('https://sub.example/page'),
      ),
      isFalse,
    );
    blocker.setExempt('example', false);
    expect(
      blocker.shouldBlock(
        Uri.parse('https://doubleclick.net/ad'),
        page: Uri.parse('https://sub.example/page'),
      ),
      isTrue,
    );
  });
}
