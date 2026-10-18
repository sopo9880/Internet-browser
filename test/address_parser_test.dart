import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/address_parser.dart';

void main() {
  test('bare host gets HTTPS', () {
    expect(AddressParser.resolve('example.org').toString(), 'https://example.org');
  });
  test('preserves full HTTPS URL and path', () {
    expect(
      AddressParser.resolve('https://example.org/path?q=1').toString(),
      'https://example.org/path?q=1',
    );
  });
  test('searches normal words instead of treating them as hostnames', () {
    final uri = AddressParser.resolve('flutter docs');
    expect(uri.host, 'duckduckgo.com');
    expect(uri.queryParameters['q'], 'flutter docs');
  });
  test('never navigates to javascript or data scheme', () {
    for (final value in ['javascript:alert(1)', 'data:text/html,hi']) {
      final uri = AddressParser.resolve(value);
      expect(uri.scheme, 'https');
      expect(uri.host, 'duckduckgo.com');
    }
  });
}
