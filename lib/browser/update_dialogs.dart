import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import 'update_service.dart';

Future<void> openOfficialReleasePage(
  BuildContext context,
  BrowserUpdate update,
) async {
  try {
    final opened = await launchUrl(
      update.releasePage,
      mode: LaunchMode.externalApplication,
    );
    if (!opened) throw StateError('Unable to open the release page');
  } catch (error) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('릴리스 페이지를 열지 못했습니다: $error')),
    );
  }
}

/// Shows a non-blocking update prompt. A seven-day snooze only applies to
/// this release tag; a newer release can still be announced immediately.
Future<void> showBrowserUpdatePrompt({
  required BuildContext context,
  required BrowserUpdate update,
  required BrowserUpdateService service,
  required SharedPreferences preferences,
}) async {
  await showDialog<void>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text('새 버전 v${update.version}'),
      content: SizedBox(
        width: 430,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Internet Browser 업데이트가 있습니다.'),
              const SizedBox(height: 12),
              if (update.description.trim().isNotEmpty) ...[
                Text(
                  update.description.length > 900
                      ? '${update.description.substring(0, 900)}…'
                      : update.description,
                  maxLines: 16,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 12),
              ],
              Text(
                update.canInstallInApp
                    ? '다운로드 후 파일 무결성을 확인하고 설치 화면을 엽니다. '
                        '설치는 사용자가 직접 승인합니다.'
                    : '이 플랫폼에서 검증된 설치 파일을 찾지 못했습니다. '
                        '공식 GitHub 릴리스 페이지에서 확인할 수 있습니다.',
                style: Theme.of(dialogContext).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () async {
            await service.snooze(preferences, update);
            if (dialogContext.mounted) Navigator.of(dialogContext).pop();
          },
          child: const Text('7일간 보지 않기'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(),
          child: const Text('나중에'),
        ),
        FilledButton(
          onPressed: () {
            Navigator.of(dialogContext).pop();
            if (update.canInstallInApp) {
              showDialog<void>(
                context: context,
                barrierDismissible: false,
                builder: (_) => InstallerDownloadDialog(
                  update: update,
                  service: service,
                ),
              );
            } else {
              openOfficialReleasePage(context, update);
            }
          },
          child: Text(
            update.canInstallInApp ? '업데이트 다운로드' : '릴리스 페이지',
          ),
        ),
      ],
    ),
  );
}

/// Streams the installer to private temp storage. Downloading never installs
/// silently; the user explicitly taps the install button after SHA-256 check.
class InstallerDownloadDialog extends StatefulWidget {
  const InstallerDownloadDialog({
    required this.update,
    required this.service,
    super.key,
  });

  final BrowserUpdate update;
  final BrowserUpdateService service;

  @override
  State<InstallerDownloadDialog> createState() =>
      _InstallerDownloadDialogState();
}

class _InstallerDownloadDialogState extends State<InstallerDownloadDialog> {
  final _cancellation = CancelToken();
  File? _verifiedFile;
  String? _error;
  String? _completionMessage;
  int _received = 0;
  int _total = 0;
  bool _launching = false;

  @override
  void initState() {
    super.initState();
    _beginDownload();
  }

  Future<void> _beginDownload() async {
    final asset = widget.update.installer;
    if (asset == null || !asset.canInstall) {
      setState(() => _error = '검증 가능한 설치 파일을 찾지 못했습니다.');
      return;
    }
    try {
      final file = await widget.service.downloadVerifiedInstaller(
        asset,
        cancelToken: _cancellation,
        onProgress: (received, total) {
          if (!mounted) return;
          setState(() {
            _received = received;
            _total = total;
          });
        },
      );
      if (mounted) setState(() => _verifiedFile = file);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _launchInstaller() async {
    final file = _verifiedFile;
    if (file == null || _launching) return;
    setState(() => _launching = true);
    try {
      await widget.service.requestInstall(file, widget.update.platform);
      if (!mounted) return;
      setState(() {
        _completionMessage = widget.update.platform == UpdatePlatform.windows
            ? 'Windows 설치 프로그램을 실행했습니다. 안내에 따라 설치하세요.'
            : 'Android 설치 화면을 열었습니다. 설치를 승인하세요.';
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _launching = false);
    }
  }

  @override
  void dispose() {
    _cancellation.cancel('Update dialog closed');
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasResult = _verifiedFile != null;
    final progress = _total > 0
        ? (_received / _total).clamp(0.0, 1.0).toDouble()
        : null;

    return AlertDialog(
      title: Text('v${widget.update.version} 업데이트'),
      content: SizedBox(
        width: 390,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_completionMessage != null)
              Text(_completionMessage!)
            else if (_error != null)
              SelectableText(
                '업데이트를 준비하지 못했습니다.\n$_error',
              )
            else if (hasResult)
              const Text(
                'SHA-256 무결성 검증이 완료됐습니다. '
                '설치 버튼을 누르면 운영체제 설치 화면이 열립니다.',
              )
            else ...[
              const Text('공식 GitHub Releases에서 설치 파일 다운로드 중'),
              const SizedBox(height: 12),
              LinearProgressIndicator(value: progress),
              const SizedBox(height: 8),
              Text(
                _total > 0
                    ? '${(100 * progress!).round()}%'
                    : '받은 데이터: ${(_received / (1024 * 1024)).toStringAsFixed(1)} MB',
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(hasResult || _error != null ? '닫기' : '취소'),
        ),
        if (_error != null)
          TextButton(
            onPressed: () => openOfficialReleasePage(context, widget.update),
            child: const Text('릴리스 페이지'),
          ),
        if (hasResult && _completionMessage == null)
          FilledButton(
            onPressed: _launching ? null : _launchInstaller,
            child: Text(
              _launching
                  ? '실행 중…'
                  : widget.update.platform == UpdatePlatform.windows
                      ? '설치 프로그램 실행'
                      : 'APK 설치 화면 열기',
            ),
          ),
      ],
    );
  }
}
