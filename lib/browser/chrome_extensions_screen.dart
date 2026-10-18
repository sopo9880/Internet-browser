import 'package:flutter/material.dart';

import 'chromium_extensions.dart';

/// v0.2.0 extension compatibility screen. It explicitly shows unsupported
/// engines instead of pretending that an HTML WebView can install Chrome CRX.
class ChromeExtensionsScreen extends StatefulWidget {
  const ChromeExtensionsScreen({super.key});

  @override
  State<ChromeExtensionsScreen> createState() => _ChromeExtensionsScreenState();
}

class _ChromeExtensionsScreenState extends State<ChromeExtensionsScreen> {
  final ChromeExtensionHost _host = AndroidChromiumExtensionHost();
  late Future<ChromiumExtensionCapabilities> _capabilities;
  bool _working = false;
  bool _installed = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _capabilities = _host.capabilities();
    _refresh();
  }

  Future<void> _refresh() async {
    final enabled =
        await _host.isInstalledAndEnabled(RequiredChromeExtension.id);
    if (mounted) setState(() => _installed = enabled);
  }

  Future<void> _install() async {
    setState(() {
      _working = true;
      _error = null;
    });
    try {
      final installed = await _host.install(RequiredChromeExtension.id);
      if (!installed) {
        throw StateError('Chromium extension host did not install AdBlock.');
      }
      await _refresh();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _remove() async {
    setState(() {
      _working = true;
      _error = null;
    });
    try {
      await _host.uninstall(RequiredChromeExtension.id);
      await _refresh();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Chrome 확장 프로그램')),
        body: FutureBuilder<ChromiumExtensionCapabilities>(
          future: _capabilities,
          builder: (context, snapshot) {
            final caps =
                snapshot.data ?? ChromiumExtensionCapabilities.unavailable;
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Column(
                    children: [
                      const ListTile(
                        leading: Icon(Icons.extension_outlined),
                        title: Text(RequiredChromeExtension.name),
                        subtitle: Text('필수 호환성 검증 대상'),
                      ),
                      ListTile(
                        title: const Text('확장 ID'),
                        subtitle: const SelectableText(
                          RequiredChromeExtension.id,
                        ),
                      ),
                      ListTile(
                        title: const Text('현재 브라우저 엔진'),
                        subtitle: Text(caps.engine),
                      ),
                      ListTile(
                        title: Text(caps.canLoadAdBlock
                            ? '확장 엔진 연결됨'
                            : 'Chromium 확장 엔진 미통합'),
                        subtitle: Text(caps.canLoadAdBlock
                            ? (_installed ? 'AdBlock 설치 확인' : '확장 설치 필요')
                            : '현재 Android WebView에서는 이 Chrome 확장을 실행할 수 없습니다. '
                              'Chromium Android 엔진과 MV3 API 연동이 선행되어야 합니다.'),
                        leading: Icon(
                          caps.canLoadAdBlock
                              ? Icons.check_circle_outline
                              : Icons.info_outline,
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Expanded(
                              child: FilledButton.icon(
                                onPressed: !caps.canLoadAdBlock || _working ||
                                        _installed
                                    ? null
                                    : _install,
                                icon: const Icon(Icons.add),
                                label: const Text('AdBlock 설치'),
                              ),
                            ),
                            if (_installed) ...[
                              const SizedBox(width: 8),
                              OutlinedButton(
                                onPressed: _working ? null : _remove,
                                child: const Text('제거'),
                              ),
                            ],
                          ],
                        ),
                      ),
                      if (_error != null)
                        Padding(
                          padding: const EdgeInsets.all(12),
                          child: SelectableText(_error!),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  '정식 지원 판정 기준: Chrome Web Store 설치, '
                  'Manifest V3 서비스 워커, declarativeNetRequest 광고 차단, '
                  '권한 승인·팝업·재시작 후 유지·실기기 검증.',
                ),
              ],
            );
          },
        ),
      );
