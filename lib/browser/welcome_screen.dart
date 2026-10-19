import 'package:flutter/material.dart';

import 'chrome_extensions_screen.dart';
import 'chromium_extensions.dart';

/// First-run Android welcome. User-facing installation is opt-in; the
/// requested extension is never silently installed, and an unsupported
/// Chromium host never renders a misleading working install button.
class WelcomeScreen extends StatefulWidget {
  WelcomeScreen({
    super.key,
    required this.onContinue,
    ChromeExtensionHost? extensionHost,
  }) : extensionHost = extensionHost ?? AndroidChromiumExtensionHost();

  final Future<void> Function() onContinue;
  final ChromeExtensionHost extensionHost;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  ChromiumExtensionCapabilities _capabilities =
      ChromiumExtensionCapabilities.unavailable;
  bool _loaded = false;
  bool _installed = false;
  bool _installing = false;
  bool _continuing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final caps = await widget.extensionHost.capabilities();
      final installed = caps.canLoadAdBlock &&
          await widget.extensionHost.isInstalledAndEnabled(
            RequiredChromeExtension.id,
          );
      if (!mounted) {
        return;
      }
      setState(() {
        _capabilities = caps;
        _installed = installed;
        _loaded = true;
        _error = null;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _capabilities = ChromiumExtensionCapabilities.unavailable;
        _installed = false;
        _loaded = true;
        _error = '확장 상태를 확인하지 못했습니다: $error';
      });
    }
  }

  Future<void> _installAdBlock() async {
    if (_installing || !_capabilities.canLoadAdBlock || _installed) {
      return;
    }
    setState(() {
      _installing = true;
      _error = null;
    });
    try {
      final result =
          await widget.extensionHost.install(RequiredChromeExtension.id);
      if (!result) {
        throw StateError('AdBlock 설치가 완료되지 않았습니다.');
      }
      final enabled = await widget.extensionHost.isInstalledAndEnabled(
        RequiredChromeExtension.id,
      );
      if (!enabled) {
        throw StateError('AdBlock이 아직 활성화되지 않았습니다.');
      }
      if (!mounted) {
        return;
      }
      setState(() => _installed = true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _error = 'AdBlock 설치 확인 실패: $error');
    } finally {
      if (mounted) {
        setState(() => _installing = false);
      }
    }
  }

  Future<void> _continue() async {
    if (_continuing) {
      return;
    }
    setState(() {
      _continuing = true;
      _error = null;
    });
    try {
      await widget.onContinue();
    } catch (error) {
      if (mounted) {
        setState(() => _error = '시작 설정을 저장하지 못했습니다: $error');
      }
    } finally {
      if (mounted) {
        setState(() => _continuing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final available = _loaded && _capabilities.canLoadAdBlock;

    return Scaffold(
      appBar: AppBar(
        title: const Text('환영합니다'),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 580),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const SizedBox(height: 8),
                Icon(Icons.travel_explore_outlined,
                    size: 62, color: theme.colorScheme.primary),
                const SizedBox(height: 14),
                Text(
                  'Internet Browser에 오신 것을 환영합니다',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                const Text(
                  '처음 시작하기 전에 광고 차단 기능을 설정할 수 있습니다.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(Icons.shield_outlined,
                                color: theme.colorScheme.primary, size: 32),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                '추천 확장 프로그램 · AdBlock',
                                style: theme.textTheme.titleLarge,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        const Text(RequiredChromeExtension.name),
                        const SizedBox(height: 6),
                        const Text(
                          'Chrome 웹 스토어의 AdBlock으로 광고를 차단할 수 있습니다. '
                          '설치는 선택 사항이며 사용자의 승인 후 진행됩니다.',
                        ),
                        const SizedBox(height: 12),
                        const Text('확장 프로그램 ID'),
                        const SelectableText(
                          RequiredChromeExtension.id,
                          style: TextStyle(fontFamily: 'monospace'),
                        ),
                        const SizedBox(height: 12),
                        if (!_loaded)
                          const LinearProgressIndicator()
                        else if (_installed)
                          const ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(Icons.verified_outlined),
                            title: Text('AdBlock 설치 및 활성화 확인'),
                          )
                        else if (!available)
                          const Text(
                            '현재 개발 빌드에는 확장 지원 Chromium 엔진이 아직 연결되지 '
                            '않았습니다. 실제 엔진이 준비되면 여기서 설치할 수 있습니다.',
                          )
                        else
                          const Text(
                            'Chromium 확장 엔진 사용 가능 · 아직 설치되지 않음',
                          ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            key: const Key('welcome-adblock-install'),
                            onPressed: available &&
                                    !_installed &&
                                    !_installing &&
                                    !_continuing
                                ? _installAdBlock
                                : null,
                            icon: const Icon(Icons.add_circle_outline),
                            label: Text(_installed
                                ? 'AdBlock 설치됨'
                                : _installing
                                    ? 'AdBlock 설치 확인 중'
                                    : 'AdBlock 설치'),
                          ),
                        ),
                        if (!_capabilities.canLoadAdBlock && _loaded)
                          Align(
                            alignment: Alignment.centerRight,
                            child: TextButton(
                              onPressed: () => Navigator.of(context).push<void>(
                                MaterialPageRoute(
                                  builder: (_) =>
                                      const ChromeExtensionsScreen(),
                                ),
                              ),
                              child: const Text('확장 지원 상태 자세히 보기'),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                const ListTile(
                  leading: Icon(Icons.tune),
                  title: Text('DPI 우회 설정'),
                  subtitle: Text('Chromium 네트워크 연동 후 인자 선택을 사용할 수 있습니다.'),
                ),
                const ListTile(
                  leading: Icon(Icons.video_library_outlined),
                  title: Text('영상 플레이어와 다운로드'),
                  subtitle: Text('지원되는 영상의 오프라인 보관·재생을 제공합니다.'),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    child: Text(
                      _error!,
                      key: const Key('welcome-error'),
                      style: TextStyle(color: theme.colorScheme.error),
                    ),
                  ),
                const SizedBox(height: 12),
                FilledButton(
                  key: const Key('welcome-continue'),
                  onPressed: _continuing ? null : _continue,
                  child: Text(_continuing ? '설정 저장 중...' : '브라우저 시작'),
                ),
                const SizedBox(height: 12),
                Text(
                  'AdBlock 없이도 시작할 수 있습니다. 이후 메뉴에서 확장 상태를 '
                  '다시 확인할 수 있습니다.',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
