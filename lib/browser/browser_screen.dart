import 'dart:convert';
import 'dart:async';

import 'package:package_info_plus/package_info_plus.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'ad_blocker.dart';
import 'chrome_extensions_screen.dart';
import 'welcome_screen.dart';
import 'chromium_navigation.dart';
import 'address_parser.dart';
import 'download_manager.dart';
import 'dpi_proxy.dart';
import 'dpi_options.dart';
import 'offline_video_player.dart';
import 'video_library.dart';
import 'video_metadata.dart';
import 'update_dialogs.dart';
import 'update_service.dart';
import 'video_detector.dart';

class BrowserTab {
  BrowserTab(this.id, this.initialUri) : uri = initialUri;

  final int id;
  Uri initialUri;
  Uri uri;
  String title = '새 탭';
  int progress = 100;
  InAppWebViewController? controller;
  final Set<Uri> videos = <Uri>{};
}

class BrowserScreen extends StatefulWidget {
  const BrowserScreen({super.key});

  @override
  State<BrowserScreen> createState() => _BrowserScreenState();
}

class _BrowserScreenState extends State<BrowserScreen> {
  final _address = TextEditingController();
  final _addressFocus = FocusNode();
  final _dpi = BrowserDpiProxy();
  final _chromium = ChromiumNavigation();
  StreamSubscription<ChromiumNavigationEvent>? _chromiumEvents;
  bool _chromiumReady = false;
  bool get _usesChromium => defaultTargetPlatform == TargetPlatform.android;
  DpiOptions _dpiOptions = const DpiOptions();
  final _library = VideoLibrary();
  bool _chromeVisible = true;
  bool _showTabStrip = false;
  int _previousScrollY = 0;
  int _scrollDistance = 0;
  final _downloads = VideoDownloadManager();
  final _ads = AdBlocker();
  final _updates = BrowserUpdateService();
  bool _checkingForUpdates = false;
  final _tabs = <BrowserTab>[];
  final _bookmarks = <String>[];
  final _history = <String>[];
  SharedPreferences? _prefs;
  WebViewEnvironment? _environment;
  bool _ready = false;
  String? _error;
  int _selected = 0;
  int _nextId = 1;

  BrowserTab get _tab => _tabs[_selected];

  @override
  void initState() {
    super.initState();
    _tabs.add(BrowserTab(_nextId++, Uri.parse(AddressParser.home)));
    _address.text = AddressParser.home;
    _initialize();
  }

  Future<void> _initialize() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _prefs = prefs;
      _dpiOptions = DpiOptions.fromPrefs(prefs);
      _ads.enabled = prefs.getBool('ads_enabled') ?? true;
      _ads.allowedHosts.addAll(prefs.getStringList('ads_exceptions') ?? []);
      _bookmarks.addAll(prefs.getStringList('bookmarks') ?? []);
      _history.addAll(prefs.getStringList('history') ?? []);
      // v0.2.0 Android intentionally targets an app-embedded Chromium
      // engine. Never configure WebView's proxy or fall back to WebView.
      bool proxyConnected = false;
      if (_usesChromium) {
        final engine = await _chromium.status();
        _chromiumReady = engine.ready;
        if (_chromiumReady) {
          _chromiumEvents = _chromium.events.listen(_onChromiumEvent);
        }
      } else {
        proxyConnected = await _dpi.initialize(
          enabled: prefs.getBool('dpi_enabled') ?? false,
          options: _dpiOptions,
        );
      }
      if (defaultTargetPlatform == TargetPlatform.windows) {
        final version = await WebViewEnvironment.getAvailableVersion();
        if (version == null) {
          throw StateError('Microsoft Edge WebView2 Runtime is required.');
        }
        _environment = await WebViewEnvironment.create(
          settings: proxyConnected
              ? WebViewEnvironmentSettings(
                  additionalBrowserArguments:
                      BrowserDpiProxy.windowsProxyArguments,
                )
              : null,
        );
      }
      await _downloads.loadSaved();
      await _library.loadSaved(_downloads.items);
      if (mounted) {
        setState(() => _ready = true);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _checkForUpdates(automatic: true);
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  void dispose() {
    _address.dispose();
    _addressFocus.dispose();
    _dpi.dispose();
    unawaited(_chromiumEvents?.cancel());
    _downloads.dispose();
    _library.dispose();
    _updates.dispose();
    _environment?.dispose();
    super.dispose();
  }

  void _message(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(text), duration: const Duration(seconds: 3)),
    );
  }


  /// Startup checks are quiet when offline and throttled to protect GitHub's
  /// unauthenticated API limit. Manual checks always bypass the throttle and
  /// any seven-day snooze.
  Future<void> _checkForUpdates({required bool automatic}) async {
    if (_checkingForUpdates) return;
    final preferences = _prefs;
    final platform = BrowserUpdateService.runningPlatform;
    if (preferences == null || platform == null) {
      if (!automatic) _message('현재 플랫폼에서 업데이트 확인을 지원하지 않습니다.');
      return;
    }
    if (automatic && !_updates.shouldCheckAutomatically(preferences)) return;

    _checkingForUpdates = true;
    try {
      final app = await PackageInfo.fromPlatform();
      final release = await _updates.checkLatest(
        installedVersion: app.version,
        platform: platform,
      );
      if (automatic) {
        await _updates.rememberSuccessfulCheck(preferences);
      }
      if (!mounted) return;
      if (release == null) {
        if (!automatic) {
          _message('현재 최신 버전이거나 게시된 정식 릴리스가 없습니다.');
        }
        return;
      }
      if (automatic && _updates.isSnoozed(preferences, release)) return;
      await showBrowserUpdatePrompt(
        context: context,
        update: release,
        service: _updates,
        preferences: preferences,
      );
    } catch (error) {
      if (!automatic && mounted) {
        _message('업데이트 확인에 실패했습니다: $error');
      }
    } finally {
      _checkingForUpdates = false;
    }
  }

  void _syncAddress() {
    if (_addressFocus.hasFocus) return;
    final text = _tab.uri.toString();
    if (_address.text == text) return;
    _address.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
  }

  void _dismissAddressEditor() {
    if (_addressFocus.hasFocus) _addressFocus.unfocus();
  }

  Future<void> _submitAddress(String input) async {
    _dismissAddressEditor();
    await _go(input);
  }

  void _onWebScroll(int y) {
    if (!mounted) return;
    _dismissAddressEditor();
    final delta = y - _previousScrollY;
    _previousScrollY = y;
    if (y < 18 && !_chromeVisible) {
      setState(() => _chromeVisible = true);
      _scrollDistance = 0;
      return;
    }
    if (delta == 0) return;
    if (_scrollDistance.sign != delta.sign) _scrollDistance = 0;
    _scrollDistance += delta;
    if (_scrollDistance > 52 && _chromeVisible && y > 100) {
      setState(() => _chromeVisible = false);
      _scrollDistance = 0;
    } else if (_scrollDistance < -42 && !_chromeVisible) {
      setState(() => _chromeVisible = true);
      _scrollDistance = 0;
    }
  }

  void _revealChrome() => setState(() => _chromeVisible = true);


  void _addTab([Uri? url]) {
    _addressFocus.unfocus();
    _revealChrome();
    setState(() {
      _tabs.add(BrowserTab(_nextId++, url ?? Uri.parse(AddressParser.home)));
      _selected = _tabs.length - 1;
      _syncAddress();
    });
  }

  void _selectTab(int index) {
    _addressFocus.unfocus();
    _revealChrome();
    setState(() {
      _selected = index;
      _syncAddress();
    });
  }

  void _closeTab(int index) {
    _addressFocus.unfocus();
    if (_tabs.length == 1) {
      _go(AddressParser.home);
      return;
    }
    setState(() {
      _tabs.removeAt(index);
      if (index < _selected) _selected--;
      if (_selected >= _tabs.length) _selected = _tabs.length - 1;
      _syncAddress();
    });
  }

  Future<void> _go(String input) async {
    final uri = AddressParser.resolve(input);
    final tab = _tab;
    tab.uri = uri;
    _syncAddress();
    if (_usesChromium) {
      if (!_chromiumReady) {
        _message('Android Chromium 엔진이 아직 연결되지 않았습니다.');
        return;
      }
      try {
        await _chromium.navigate(tab.id, uri);
      } catch (error) {
        _message('Chromium 탐색 실패: $error');
      }
      return;
    }
    if (tab.controller == null) {
      setState(() => tab.initialUri = uri);
      return;
    }
    try {
      await tab.controller!.loadUrl(
        urlRequest: URLRequest(url: WebUri(uri.toString())),
      );
    } catch (error) {
      _message('탐색 실패: $error');
    }
  }

  Future<void> _back() async {
    if (_usesChromium) {
      if (_chromiumReady && await _chromium.canBack(_tab.id)) {
        await _chromium.back(_tab.id);
      } else if (_tabs.length > 1) {
        _closeTab(_selected);
      }
      return;
    }
    final controller = _tab.controller;
    if (controller != null && await controller.canGoBack()) {
      await controller.goBack();
    } else if (_tabs.length > 1) {
      _closeTab(_selected);
    }
  }

  Future<void> _forward() async {
    if (_usesChromium) {
      if (_chromiumReady && await _chromium.canForward(_tab.id)) {
        await _chromium.forward(_tab.id);
      }
      return;
    }
    final controller = _tab.controller;
    if (controller != null && await controller.canGoForward()) {
      await controller.goForward();
    }
  }

  Future<void> _reload() async {
    if (_usesChromium) {
      if (_chromiumReady) await _chromium.reload(_tab.id);
      return;
    }
    await _tab.controller?.reload();
  }

  void _updateLocationUri(BrowserTab tab, Uri? uri) {
    if (!mounted || !_tabs.contains(tab) || uri == null) return;
    if (!AddressParser.isRemoteHttp(uri)) return;
    setState(() {
      tab.uri = uri;
      if (identical(tab, _tab)) _syncAddress();
    });
  }

  void _updateLocation(BrowserTab tab, WebUri? webUri) {
    final uri = webUri == null ? null : Uri.tryParse(webUri.toString());
    _updateLocationUri(tab, uri);
  }

  /// The native Chromium module emits the same browsing events as WebView2.
  /// A missing engine emits none and the Android UI stays explicitly blocked.
  void _onChromiumEvent(ChromiumNavigationEvent event) {
    if (!mounted) return;
    BrowserTab? tab;
    for (final candidate in _tabs) {
      if (candidate.id == event.tabId) {
        tab = candidate;
        break;
      }
    }
    if (tab == null) return;
    final activeTab = tab;
    switch (event.type) {
      case 'url':
        _updateLocationUri(activeTab, event.url);
      case 'title':
        if (event.title != null) {
          setState(() => activeTab.title = event.title!);
        }
      case 'progress':
        if (event.progress != null) {
          setState(() =>
              activeTab.progress = event.progress!.clamp(0, 100).toInt());
        }
      case 'loadStarted':
        setState(() {
          activeTab.progress = 0;
          activeTab.videos.clear();
        });
        _updateLocationUri(activeTab, event.url);
      case 'loadFinished':
        _updateLocationUri(activeTab, event.url);
        unawaited(_pageFinished(activeTab));
      case 'resource':
        final uri = event.url;
        if (uri != null) _newMediaUrl(activeTab, uri.toString());
      case 'pointerDown':
        _dismissAddressEditor();
      case 'scroll':
        final y = event.payload['y'];
        if (y is num && identical(activeTab, _tab)) _onWebScroll(y.toInt());
    }
  }

  Future<dynamic> _evaluatePageScript(BrowserTab tab, String source) async {
    if (_usesChromium) {
      if (!_chromiumReady) return null;
      return _chromium.javascript(tab.id, source);
    }
    return tab.controller?.evaluateJavascript(source: source);
  }

  void _saveHistory(Uri uri) {
    if (!AddressParser.isRemoteHttp(uri)) return;
    final url = uri.toString();
    _history.remove(url);
    _history.insert(0, url);
    if (_history.length > 150) _history.removeRange(150, _history.length);
    _prefs?.setStringList('history', _history);
  }

  bool get _bookmarked => _bookmarks.contains(_tab.uri.toString());

  void _toggleBookmark() {
    final url = _tab.uri.toString();
    setState(() {
      if (_bookmarks.contains(url)) {
        _bookmarks.remove(url);
      } else {
        _bookmarks.insert(0, url);
      }
    });
    _prefs?.setStringList('bookmarks', _bookmarks);
  }

  void _newMediaUrl(BrowserTab tab, String input) {
    if (!mounted || !_tabs.contains(tab)) return;
    final uri = Uri.tryParse(input);
    if (uri == null || !VideoDetector.isDirectVideo(uri)) return;
    if (tab.videos.length >= 30 || tab.videos.contains(uri)) return;
    setState(() => tab.videos.add(uri));
  }

  Future<void> _detectMedia(BrowserTab tab) async {
    if (_usesChromium && !_chromiumReady) return;
    if (!_usesChromium && tab.controller == null) return;
    try {
      dynamic result = await _evaluatePageScript(
        tab, VideoDetector.discoverScript,
      );
      if (result is String) {
        try {
          result = jsonDecode(result);
        } catch (_) {
          result = null;
        }
      }
      if (!mounted || !_tabs.contains(tab)) return;
      setState(() => tab.videos.addAll(VideoDetector.parseCandidates(result)));
    } catch (_) {
      // Unsupported media APIs must never stop page navigation.
    }
  }

  Future<void> _pageFinished(BrowserTab tab) async {
    if (!mounted || !_tabs.contains(tab)) return;
    _saveHistory(tab.uri);
    if (_ads.enabled && !_ads.isExempt(tab.uri)) {
      try {
        await _evaluatePageScript(tab, AdBlocker.cosmeticScript);
        if (AdBlocker.isYoutube(tab.uri)) {
          await _evaluatePageScript(tab, AdBlocker.youtubeCleanupScript);
        }
      } catch (_) {}
    }
    await _detectMedia(tab);
    try {
      if (!_usesChromium) {
        await _evaluatePageScript(tab, r'''
(function() {
 if (window.__internetBrowserFocusInstalled) return;
 window.__internetBrowserFocusInstalled = true;
 document.addEventListener('pointerdown', function() {
   if (window.flutter_inappwebview) {
     window.flutter_inappwebview.callHandler('browserPointerDown');
   }
 }, {passive: true, capture: true});
})();
''');
      }
    } catch (_) {}
  }

  Future<VideoPageMetadata> _readPageMetadata(BrowserTab tab) async {
    dynamic value;
    try {
      value = await _evaluatePageScript(tab, VideoPageMetadata.discoverScript);
    } catch (_) {}
    return VideoPageMetadata.parse(
      value, tab.uri, fallbackTitle: tab.title,
    );
  }

  Future<void> _download(Uri uri) async {
    if (!VideoDetector.isDirectVideo(uri)) {
      _message('직접 연결된 MP4/WebM/MOV/M4V 영상만 저장 가능합니다.');
      return;
    }
    _message('영상 다운로드를 시작했습니다.');
    try {
      final metadata = await _readPageMetadata(_tab);
      final item = await _downloads.download(uri, metadata: metadata);
      if (item.state == VideoDownloadState.complete) {
        await _library.register(item, page: metadata);
        _message('다운로드 완료: ${item.fileName}');
      } else if (item.state == VideoDownloadState.failed) {
        _message('다운로드 실패: ${item.error ?? '오류'}');
      }
    } catch (error) {
      _message('다운로드 오류: $error');
    }
  }

  Future<void> _downloadYoutube(Uri page) async {
    var confirmed = false;
    final permitted = await showDialog<bool>(
      context: context,
      builder: (dialog) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('YouTube 영상 저장'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                '저장 권한이 있는 영상만 다운로드하세요. '
                '음성과 영상이 결합된 스트림은 일반적으로 최대 360p입니다. '
                '일부 영상은 스트림을 제공하지 않을 수 있습니다.',
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('이 영상의 저장 권한을 확인했습니다'),
                value: confirmed,
                onChanged: (value) => update(
                  () => confirmed = value ?? false,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialog, false),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: confirmed
                  ? () => Navigator.pop(dialog, true)
                  : null,
              child: const Text('저장 시작'),
            ),
          ],
        ),
      ),
    );
    if (permitted != true || !mounted) return;
    _message('YouTube 영상 스트림 확인 및 다운로드를 시작했습니다.');
    try {
      final metadata = await _readPageMetadata(_tab);
      final item = await _downloads.downloadYoutube(page);
      if (item.state == VideoDownloadState.complete) {
        await _library.register(
          item,
          page: metadata,
          title: item.resolvedTitle,
          thumbnail: item.thumbnailUrl,
          quality: item.qualityLabel,
          durationSeconds: item.durationSeconds,
        );
      }
      if (!mounted) return;
      if (item.state == VideoDownloadState.complete) {
        _message('영상 다운로드 완료: ${item.fileName}');
      } else if (item.state == VideoDownloadState.failed) {
        _message('영상 저장 실패: ${item.error ?? '원인을 확인하세요.'}');
      }
    } catch (error) {
      _message('YouTube 스트림 확인 실패: $error');
    }
  }

  Future<void> _showVideos() async {
    final tab = _tab;
    await _detectMedia(tab);
    if (!mounted) return;
    final metadata = await _readPageMetadata(tab);
    if (!mounted) return;
    final urls = tab.videos.toList();
    final youtubeId = VideoDetector.youtubeVideoId(tab.uri);
    if (urls.isEmpty && youtubeId == null) {
      _message('저장 가능한 직접 영상 또는 YouTube 영상 페이지를 찾지 못했습니다.');
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (sheet) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: 0.65,
          child: Column(
            children: [
              const ListTile(
                title: Text('영상 다운로드'),
                subtitle: Text('저장 권한이 있는 콘텐츠만 다운로드하세요'),
              ),
              Expanded(
                child: ListView.builder(
                  itemCount: urls.length + (youtubeId == null ? 0 : 1),
                  itemBuilder: (_, i) {
                    if (youtubeId != null && i == 0) {
                      return ListTile(
                        leading: const Icon(Icons.smart_display_outlined),
                        title: Text('현재 영상: ${metadata.title}'),
                        subtitle: const Text('가능한 음성+영상 통합 스트림'),
                        trailing: const Icon(Icons.download_outlined),
                        onTap: () {
                          Navigator.pop(sheet);
                          _downloadYoutube(tab.uri);
                        },
                      );
                    }
                    final index = youtubeId == null ? i : i - 1;
                    return ListTile(
                      leading: const Icon(Icons.movie_outlined),
                      title: Text(
                        metadata.title == '동영상'
                            ? (urls[index].pathSegments.isEmpty
                                ? '동영상'
                                : urls[index].pathSegments.last)
                            : metadata.title,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(urls[index].host),
                      trailing: const Icon(Icons.download_outlined),
                      onTap: () {
                        Navigator.pop(sheet);
                        _download(urls[index]);
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openOfflineVideo(VideoDownloadItem selected) async {
    final completed = _downloads.items.where(
      (item) => item.state == VideoDownloadState.complete,
    ).toList();
    final index = completed.indexOf(selected);
    if (index < 0 || !mounted) return;
    final saved = completed.map(_library.forItem).toList();
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => OfflineVideoPlayer(
          items: saved,
          initialIndex: index,
          onPositionChanged: _library.setPlaybackPosition,
        ),
      ),
    );
  }

  Future<void> _renameOfflineVideo(VideoDownloadItem item) async {
    final saved = _library.forItem(item);
    final controller = TextEditingController(text: saved.title);
    try {
      final title = await showDialog<String>(
        context: context,
        builder: (dialog) => AlertDialog(
          title: const Text('영상 제목 수정'),
          content: TextField(
            controller: controller,
            autofocus: true,
            maxLength: 180,
            decoration: const InputDecoration(
              hintText: '영상 제목',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialog),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialog, controller.text),
              child: const Text('저장'),
            ),
          ],
        ),
      );
      if (title != null) await _library.editTitle(saved, title);
    } finally {
      controller.dispose();
    }
  }

  Future<void> _deleteOfflineVideo(VideoDownloadItem item) async {
    final wasActive = item.state == VideoDownloadState.running;
    await _downloads.delete(item);
    if (!wasActive) await _library.forget(item);
  }

  Future<void> _showDownloads() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (sheet) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: 0.78,
          child: AnimatedBuilder(
            animation: Listenable.merge([_downloads, _library]),
            builder: (_, child) {
              final items = _downloads.items;
              return Column(
                children: [
                  const ListTile(
                    title: Text('오프라인 동영상 서재'),
                    subtitle: Text('앱 내 플레이어 · 제목 편집 · 이어보기'),
                  ),
                  Expanded(
                    child: items.isEmpty
                        ? const Center(child: Text('저장된 동영상이 없습니다.'))
                        : ListView.builder(
                            itemCount: items.length,
                            itemBuilder: (_, i) {
                              final item = items[i];
                              final saved = _library.forItem(item);
                              final completed =
                                  item.state == VideoDownloadState.complete;
                              final running =
                                  item.state == VideoDownloadState.running;
                              final details = <String>[
                                if (saved.quality != null) saved.quality!,
                                if (saved.durationSeconds != null)
                                  '${Duration(seconds: saved.durationSeconds!)}',
                                if (saved.lastPositionMs > 0)
                                  '이어보기 ${Duration(milliseconds: saved.lastPositionMs)}',
                              ];
                              return ListTile(
                                title: Text(
                                  completed ? saved.title
                                      : (item.resolvedTitle ?? item.fileName),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                subtitle: running
                                    ? LinearProgressIndicator(
                                        value: item.progress / 100,
                                      )
                                    : Text(
                                        item.error == null
                                            ? (completed
                                                ? (details.isEmpty
                                                    ? '오프라인 저장 완료'
                                                    : details.join(' · '))
                                                : item.state.name)
                                            : '${item.state.name}: ${item.error}',
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                leading: Icon(
                                  completed
                                      ? Icons.play_circle_outline
                                      : Icons.download_outlined,
                                ),
                                onTap: completed
                                    ? () {
                                        Navigator.pop(sheet);
                                        _openOfflineVideo(item);
                                      }
                                    : null,
                                trailing: PopupMenuButton<String>(
                                  tooltip: '동영상 메뉴',
                                  onSelected: (selected) async {
                                    if (selected == 'rename' && completed) {
                                      await _renameOfflineVideo(item);
                                    }
                                    if (selected == 'delete') {
                                      await _deleteOfflineVideo(item);
                                    }
                                  },
                                  itemBuilder: (_) => [
                                    if (completed)
                                      const PopupMenuItem(
                                        value: 'rename',
                                        child: Text('제목 수정'),
                                      ),
                                    PopupMenuItem(
                                      value: 'delete',
                                      child: Text(running ? '다운로드 취소' : '삭제'),
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Future<void> _showSaved(String title, List<String> values,
      {bool removable = false}) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (sheet) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: 0.7,
          child: StatefulBuilder(
            builder: (_, refresh) => Column(
              children: [
                ListTile(title: Text(title)),
                Expanded(
                  child: values.isEmpty
                      ? const Center(child: Text('항목이 없습니다.'))
                      : ListView.builder(
                          itemCount: values.length,
                          itemBuilder: (_, i) {
                            final link = values[i];
                            return ListTile(
                              title: Text(link, maxLines: 2),
                              onTap: () {
                                Navigator.pop(sheet);
                                _go(link);
                              },
                              trailing: removable
                                  ? IconButton(
                                      onPressed: () {
                                        setState(() => values.removeAt(i));
                                        refresh(() {});
                                        _prefs?.setStringList(
                                            'bookmarks', _bookmarks);
                                      },
                                      icon: const Icon(Icons.close),
                                    )
                                  : null,
                            );
                          },
                        ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _showDpiOptions() async {
    final prefs = _prefs;
    if (prefs == null) return;
    DpiOptions editing = _dpiOptions;
    final split = TextEditingController(text: editing.splitValue);
    final disorder = TextEditingController(text: editing.disorderValue);
    final tls = TextEditingController(text: editing.tlsValue);
    try {
      await showDialog<void>(
        context: context,
        builder: (dialog) => StatefulBuilder(
          builder: (context, update) => AlertDialog(
            title: const Text('ByeDPI 우회 인자 설정'),
            content: SizedBox(
              width: 430,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButtonFormField<DpiPreset>(
                      initialValue: editing.preset,
                      decoration: const InputDecoration(
                        labelText: '우회 프리셋',
                      ),
                      items: [
                        for (final preset in DpiPreset.values)
                          DropdownMenuItem(
                            value: preset,
                            child: Text(DpiOptions.presetNames[preset]!),
                          ),
                      ],
                      onChanged: (value) {
                        if (value != null) {
                          update(() =>
                              editing = editing.copyWith(preset: value));
                        }
                      },
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '프리셋은 Windows·Android 플랫폼별 적절한 인자를 '
                      '선택합니다. 사용자 지정 시 각 옵션을 개별 설정합니다.',
                    ),
                    if (editing.preset == DpiPreset.custom) ...[
                      SwitchListTile(
                        title: const Text('Split · 요청 분할'),
                        value: editing.split,
                        onChanged: (value) => update(() =>
                            editing = editing.copyWith(split: value)),
                      ),
                      TextField(
                        controller: split,
                        enabled: editing.split,
                        decoration: const InputDecoration(
                          labelText: 'Split 위치 (예: 1+s)',
                        ),
                      ),
                      SwitchListTile(
                        title: const Text('Disorder · 역순 전송'),
                        value: editing.disorder,
                        onChanged: (value) => update(() =>
                            editing = editing.copyWith(disorder: value)),
                      ),
                      TextField(
                        controller: disorder,
                        enabled: editing.disorder,
                        decoration: const InputDecoration(
                          labelText: 'Disorder 위치 (예: 3+s)',
                        ),
                      ),
                      SwitchListTile(
                        title: const Text('TLS Record 분할'),
                        value: editing.tlsRecord,
                        onChanged: (value) => update(() =>
                            editing = editing.copyWith(tlsRecord: value)),
                      ),
                      TextField(
                        controller: tls,
                        enabled: editing.tlsRecord,
                        decoration: const InputDecoration(
                          labelText: 'TLS Record 위치 (예: 1+s)',
                        ),
                      ),
                      SwitchListTile(
                        title: const Text('Auto · 실패 시 재시도'),
                        value: editing.autoRetry,
                        onChanged: (value) => update(() =>
                            editing = editing.copyWith(autoRetry: value)),
                      ),
                      SwitchListTile(
                        title: const Text('HTTP Host 변형'),
                        value: editing.httpModification,
                        onChanged: (value) => update(() =>
                            editing = editing.copyWith(
                              httpModification: value)),
                      ),
                      SwitchListTile(
                        title: const Text('Fake · TTL 제한 가짜 패킷'),
                        value: editing.fakePacket,
                        onChanged: (value) => update(() =>
                            editing = editing.copyWith(fakePacket: value)),
                      ),
                      if (editing.fakePacket)
                        DropdownButtonFormField<int>(
                          initialValue: editing.fakeTtl,
                          decoration: const InputDecoration(
                            labelText: 'Fake TTL 값',
                          ),
                          items: [
                            for (final ttl in const [4, 8, 12, 16, 32])
                              DropdownMenuItem(value: ttl, child: Text('$ttl')),
                          ],
                          onChanged: (value) {
                            if (value != null) {
                              update(() =>
                                  editing = editing.copyWith(fakeTtl: value));
                            }
                          },
                        ),
                    ],
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () {
                  split.text = '1+s';
                  disorder.text = '3+s';
                  tls.text = '1+s';
                  update(() => editing = const DpiOptions());
                },
                child: const Text('기본값 복원'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(dialog),
                child: const Text('취소'),
              ),
              FilledButton(
                onPressed: () async {
                  final candidate = editing.copyWith(
                    splitValue: split.text.trim(),
                    disorderValue: disorder.text.trim(),
                    tlsValue: tls.text.trim(),
                  );
                  if (candidate.preset == DpiPreset.custom &&
                      ((candidate.split &&
                            !DpiOptions.validPosition(candidate.splitValue)) ||
                       (candidate.disorder &&
                            !DpiOptions.validPosition(candidate.disorderValue)) ||
                       (candidate.tlsRecord &&
                            !DpiOptions.validPosition(candidate.tlsValue)))) {
                    _message('인자 형식이 잘못됐습니다. 1+s 같은 위치만 입력하세요.');
                    return;
                  }
                  await candidate.save(prefs);
                  _dpiOptions = candidate;
                  // Android Chromium does not use the WebView proxy API.
                  if (_usesChromium &&
                      (prefs.getBool('dpi_enabled') ?? false)) {
                    _message('Chromium 네트워크 프록시 연결 구현 후 적용됩니다.');
                  }
                  if (mounted) {
                    setState(() {});
                    if (dialog.mounted) Navigator.pop(dialog);
                    _message(defaultTargetPlatform == TargetPlatform.windows
                        ? '설정 저장 완료. Windows 재시작 후 적용됩니다.'
                        : 'Android Chromium 프록시 연동 대기 · 설정 저장됨');
                  }
                },
                child: const Text('저장 및 적용'),
              ),
            ],
          ),
        ),
      );
    } finally {
      split.dispose();
      disorder.dispose();
      tls.dispose();
    }
  }

  Future<void> _showSettings() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: 0.68,
          child: StatefulBuilder(
            builder: (_, update) {
              final host = _tab.uri.host;
              return ListView(
                children: [
                  const ListTile(title: Text('브라우저 보호 설정')),
                  SwitchListTile(
                    title: const Text('광고 차단'),
                    subtitle: const Text('기본 광고 서버·배너 차단'),
                    value: _ads.enabled,
                    onChanged: (value) {
                      setState(() => _ads.enabled = value);
                      update(() {});
                      _prefs?.setBool('ads_enabled', value);
                      _reload();
                    },
                  ),
                  SwitchListTile(
                    title: const Text('현재 사이트 광고 차단 제외'),
                    subtitle: Text(host),
                    value: _ads.isExempt(_tab.uri),
                    onChanged: host.isEmpty
                        ? null
                        : (value) {
                            setState(() => _ads.setExempt(host, value));
                            update(() {});
                            _prefs?.setStringList(
                                'ads_exceptions', _ads.allowedHosts.toList());
                            _reload();
                          },
                  ),
                  const Divider(),
                  SwitchListTile(
                    title: const Text('시작할 때 업데이트 확인'),
                    subtitle: const Text('정식 릴리스 확인, 최대 12시간마다'),
                    value: _prefs?.getBool('update_auto_check') ?? true,
                    onChanged: (value) {
                      _prefs?.setBool('update_auto_check', value);
                      update(() {});
                    },
                  ),
                  ListTile(
                    leading: const Icon(Icons.system_update_outlined),
                    title: const Text('지금 업데이트 확인'),
                    subtitle: const Text('GitHub Releases에서 최신 버전 확인'),
                    onTap: () {
                      Navigator.of(context).pop();
                      _checkForUpdates(automatic: false);
                    },
                  ),
                  const Divider(),
                  SwitchListTile(
                    secondary: const Icon(Icons.shield_outlined),
                    title: const Text('ByeDPI 우회 엔진'),
                    subtitle: Text(_usesChromium
                        ? 'Android Chromium 네트워크 우회 엔진 연결 대기 · 설정값 저장 가능'
                        : '${_dpi.status}\nWindows: 변경 후 앱 재시작 필요'),
                    value: _prefs?.getBool('dpi_enabled') ?? false,
                    onChanged: (value) async {
                      await _prefs?.setBool('dpi_enabled', value);
                      if (_usesChromium) {
                        _message('Android Chromium 프록시 연동 전까지 설정만 저장합니다.');
                      } else {
                        _message('Windows DPI 변경사항은 앱 재시작 후 적용됩니다.');
                      }
                      if (mounted) {
                        setState(() {});
                        update(() {});
                      }
                    },
                  ),
                  ListTile(
                    leading: const Icon(Icons.tune),
                    title: const Text('DPI 우회 인자 및 프리셋'),
                    subtitle: Text(
                      DpiOptions.presetNames[_dpiOptions.preset] ??
                          '기본 (권장)',
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () async {
                      await _showDpiOptions();
                      if (mounted) update(() {});
                    },
                  ),
                  ListTile(
                    leading: const Icon(Icons.info_outline),
                    title: const Text('DPI 연결 상태'),
                    subtitle: Text(_usesChromium
                        ? 'Chromium 엔진 네트워크 계층 연결 미완료'
                        : _dpi.status),
                  ),
                  const ListTile(
                    leading: Icon(Icons.info_outline),
                    title: Text('Internet Browser'),
                    subtitle: Text(
                      '기본 광고 필터는 전체 EasyList 규칙을 지원하지 않습니다.',
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }


  Future<void> _showTabChooser() async {
    await showModalBottomSheet<void>(
      context: context,
      builder: (sheet) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            ListTile(
              title: const Text('열린 탭'),
              trailing: IconButton(
                tooltip: '새 탭',
                icon: const Icon(Icons.add),
                onPressed: () {
                  Navigator.pop(sheet);
                  _addTab();
                },
              ),
            ),
            for (var i = 0; i < _tabs.length; i++)
              ListTile(
                selected: i == _selected,
                leading: const Icon(Icons.tab),
                title: Text(_tabs[i].title, maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                subtitle: Text(_tabs[i].uri.toString(), maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                trailing: IconButton(
                  tooltip: '탭 닫기',
                  icon: const Icon(Icons.close),
                  onPressed: () {
                    Navigator.pop(sheet);
                    _closeTab(i);
                  },
                ),
                onTap: () {
                  Navigator.pop(sheet);
                  _selectTab(i);
                },
              ),
          ],
        ),
      ),
    );
  }

  Widget _tabStrip() => SizedBox(
        height: 34,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          itemCount: _tabs.length + 1,
          itemBuilder: (_, index) {
            if (index == _tabs.length) {
              return IconButton(
                tooltip: '새 탭',
                onPressed: _addTab,
                icon: const Icon(Icons.add),
              );
            }
            final tab = _tabs[index];
            return Material(
              color: index == _selected
                  ? Theme.of(context).colorScheme.surfaceContainerHighest
                  : Colors.transparent,
              child: InkWell(
                onTap: () => _selectTab(index),
                child: SizedBox(
                  width: 172,
                  child: Row(
                    children: [
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          tab.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      IconButton(
                        tooltip: '닫기',
                        iconSize: 18,
                        onPressed: () => _closeTab(index),
                        icon: const Icon(Icons.close),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      );

  Widget _toolbar(bool wide) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 5),
        child: Row(
          children: [
            IconButton(
                tooltip: '뒤로',
                onPressed: _back,
                icon: const Icon(Icons.arrow_back)),
            IconButton(
                tooltip: '앞으로',
                onPressed: _forward,
                icon: const Icon(Icons.arrow_forward)),
            if (wide)
              IconButton(
                  tooltip: '새로고침',
                  onPressed: _reload,
                  icon: const Icon(Icons.refresh)),
            Expanded(
              child: TextField(
                controller: _address,
                 focusNode: _addressFocus,
                keyboardType: TextInputType.url,
                textInputAction: TextInputAction.go,
                autocorrect: false,
                onSubmitted: _submitAddress,
                 onTapOutside: (_) => _dismissAddressEditor(),
                decoration: InputDecoration(
                  isDense: true,
                  prefixIcon: const Icon(Icons.language, size: 18),
                  hintText: '검색 또는 주소',
                  contentPadding: const EdgeInsets.symmetric(vertical: 10),
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(22)),
                ),
              ),
            ),
            IconButton(
              tooltip: '탭 목록',
              onPressed: _showTabChooser,
              icon: Badge(
                label: Text('${_tabs.length}'),
                child: const Icon(Icons.tab),
              ),
            ),
            PopupMenuButton<String>(
              tooltip: '메뉴',
              onSelected: (value) {
                switch (value) {
                  case 'new':
                    _addTab();
                  case 'videos':
                    _showVideos();
                  case 'refresh':
                    _reload();
                  case 'bookmark':
                    _toggleBookmark();
                  case 'bookmarks':
                    _showSaved('북마크', _bookmarks, removable: true);
                  case 'history':
                    _showSaved('방문 기록', _history);
                  case 'downloads':
                    _showDownloads();
                  case 'settings':
                    _showSettings();
                  case 'extensions':
                    Navigator.of(context).push<void>(
                      MaterialPageRoute(
                        builder: (_) => const ChromeExtensionsScreen(),
                      ),
                    );
                  case 'welcome':
                    Navigator.of(context).push<void>(
                      MaterialPageRoute(
                        builder: (_) => WelcomeScreen(
                          onContinue: () async {
                            if (context.mounted) Navigator.of(context).pop();
                          },
                        ),
                      ),
                    );
                  case 'toggle_tabs':
                    setState(() => _showTabStrip = !_showTabStrip);
                }
              },
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'new', child: Text('새 탭')),
                const PopupMenuItem(value: 'videos', child: Text('동영상 감지·다운로드')),
                const PopupMenuItem(value: 'refresh', child: Text('새로고침')),
                PopupMenuItem(
                    value: 'bookmark',
                    child: Text(_bookmarked ? '북마크 해제' : '북마크 추가')),
                const PopupMenuItem(
                    value: 'bookmarks', child: Text('북마크')),
                const PopupMenuItem(value: 'history', child: Text('방문 기록')),
                const PopupMenuItem(
                    value: 'downloads', child: Text('동영상 서재')),
                if (defaultTargetPlatform == TargetPlatform.android)
                  const PopupMenuItem(
                    value: 'extensions',
                    child: Text('Chrome 확장 관리 (준비 중)'),
                  ),
                if (defaultTargetPlatform == TargetPlatform.android)
                  const PopupMenuItem(
                    value: 'welcome',
                    child: Text('환영 화면 · AdBlock 설치 안내'),
                  ),
                const PopupMenuItem(
                    value: 'settings', child: Text('광고·DPI 설정')),
                if (wide) PopupMenuItem(
                    value: 'toggle_tabs', child: Text(_showTabStrip ? '탭줄 숨기기' : '탭줄 표시')),
              ],
            ),
          ],
        ),
      );

  Widget _webView(BrowserTab tab) => InAppWebView(
        key: ValueKey(tab.id),
        webViewEnvironment: _environment,
        initialUrlRequest: URLRequest(
          url: WebUri(tab.initialUri.toString()),
        ),
        initialSettings: InAppWebViewSettings(
          javaScriptEnabled: true,
          useShouldOverrideUrlLoading: true,
          useShouldInterceptRequest: true,
          useOnLoadResource: true,
          useOnDownloadStart: true,
          supportMultipleWindows: true,
          mediaPlaybackRequiresUserGesture: true,
          isInspectable: kDebugMode,
        ),
        onWebViewCreated: (controller) {
          tab.controller = controller;
          controller.addJavaScriptHandler(
            handlerName: 'browserPointerDown',
            callback: (_) {
              _dismissAddressEditor();
              return null;
            },
          );
        },
        onLoadStart: (controller, url) {
          if (!mounted || !_tabs.contains(tab)) return;
          setState(() {
            tab.progress = 0;
            tab.videos.clear();
          });
          _updateLocation(tab, url);
        },
        onLoadStop: (controller, url) async {
          _updateLocation(tab, url);
          await _pageFinished(tab);
        },
        onScrollChanged: (controller, x, y) {
          if (identical(tab, _tab)) _onWebScroll(y);
        },
        onProgressChanged: (controller, progress) {
          if (mounted && _tabs.contains(tab) && tab.progress != progress) {
            setState(() => tab.progress = progress);
          }
        },
        onTitleChanged: (controller, title) {
          if (mounted && _tabs.contains(tab)) {
            setState(() => tab.title =
                title == null || title.isEmpty ? tab.uri.host : title);
          }
        },
        onUpdateVisitedHistory: (controller, url, isReload) {
          _updateLocation(tab, url);
        },
        shouldOverrideUrlLoading: (controller, action) async {
          final url = action.request.url;
          if (url == null) return NavigationActionPolicy.CANCEL;
          final uri = Uri.tryParse(url.toString());
          if (uri == null) return NavigationActionPolicy.CANCEL;
          if (AddressParser.isRemoteHttp(uri) || uri.scheme == 'about') {
            return NavigationActionPolicy.ALLOW;
          }
          return NavigationActionPolicy.CANCEL;
        },
        shouldInterceptRequest: (controller, request) async {
          final resource = Uri.tryParse(request.url.toString());
          if (resource == null || !_ads.shouldBlock(resource, page: tab.uri)) {
            return null;
          }
          return WebResourceResponse(
            contentType: 'text/plain',
            contentEncoding: 'utf-8',
            data: Uint8List(0),
            statusCode: 403,
            reasonPhrase: 'Blocked by browser',
          );
        },
        onLoadResource: (controller, resource) {
          _newMediaUrl(tab, resource.url.toString());
        },
        onDownloadStartRequest: (controller, request) async {
          final uri = Uri.tryParse(request.url.toString());
          if (uri != null) _download(uri);
        },
        onCreateWindow: (controller, action) async {
          final raw = action.request.url?.toString();
          final uri = raw == null ? null : Uri.tryParse(raw);
          if (uri == null || !AddressParser.isRemoteHttp(uri)) return false;
          _addTab(uri);
          return true;
        },
      );

  Widget _engineView(BrowserTab tab) {
    if (!_usesChromium) return _webView(tab);
    if (!_chromiumReady) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.extension_off_outlined, size: 48),
              const SizedBox(height: 12),
              const Text(
                'Android Chromium 엔진 이식 중',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              const Text(
                '현재 개발 빌드에는 확장 프로그램을 실행하는 Chromium '
                '네이티브 엔진이 포함되지 않았습니다. WebView로 자동 대체하지 '
                '않으며 AdBlock 호환성 검증 전에는 릴리스하지 않습니다.',
                textAlign: TextAlign.center,
              ),
              TextButton(
                onPressed: () => Navigator.of(context).push<void>(
                  MaterialPageRoute(
                    builder: (_) => const ChromeExtensionsScreen(),
                  ),
                ),
                child: const Text('확장 엔진 상태 보기'),
              ),
            ],
          ),
        ),
      );
    }
    return ChromiumAndroidPage(tabId: tab.id, url: tab.initialUri);
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width > 680;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: Scaffold(
        body: SafeArea(
          child: _error != null
              ? Center(child: SelectableText('브라우저 초기화 실패:\n$_error'))
              : !_ready
                  ? const Center(child: CircularProgressIndicator())
                  : Column(
                      children: [
                        if (_chromeVisible) ...[
                          if (wide && _showTabStrip) _tabStrip(),
                          _toolbar(wide),
                        ],
                        if (_tab.progress < 100)
                          LinearProgressIndicator(
                            value: _tab.progress / 100,
                          ),
                        Expanded(
                          child: Stack(
                            children: [
                              Positioned.fill(
                                child: Listener(
                                  onPointerDown: (_) => _dismissAddressEditor(),
                                  child: IndexedStack(
                                    index: _selected,
                                    children: _tabs.map(_engineView).toList(),
                                  ),
                                ),
                              ),
                              if (!_chromeVisible)
                                Positioned(
                                  right: 8,
                                  top: 8,
                                  child: FloatingActionButton.small(
                                    tooltip: '주소창 펼치기',
                                    onPressed: _revealChrome,
                                    child: const Icon(
                                      Icons.keyboard_arrow_down,
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
        ),
      ),
    );
  }

}
