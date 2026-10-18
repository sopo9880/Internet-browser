import 'package:flutter_test/flutter_test.dart';
import 'package:internet_browser/browser/dpi_proxy.dart';

void main() {
  test('DPI proxy accepts only a SOCKS5 no-auth greeting', () {
    expect(BrowserDpiProxy.isSocks5Greeting([5, 0]), isTrue);
    expect(BrowserDpiProxy.isSocks5Greeting([5, 0, 1]), isTrue);
    expect(BrowserDpiProxy.isSocks5Greeting([]), isFalse);
    expect(BrowserDpiProxy.isSocks5Greeting([5]), isFalse);
    expect(BrowserDpiProxy.isSocks5Greeting([4, 0]), isFalse);
    expect(BrowserDpiProxy.isSocks5Greeting([5, 255]), isFalse);
  });

  test('Windows local-only SOCKS5 browser argument', () {
    expect(
      BrowserDpiProxy.windowsProxyArguments,
      '--proxy-server=socks5://127.0.0.1:1080',
    );
  });
}
