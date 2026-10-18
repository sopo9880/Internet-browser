import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'ad_blocker.dart';
import 'address_parser.dart';
import 'download_manager.dart';
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
  final _downloads = VideoDownloadManager();
  final _ads = AdBlocker();
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
      _ads.enabled = prefs.getBool('ads_enabled') ?? true;
      _ads.allowedHosts.addAll(prefs.getStringList('ads_exceptions') ?? []);
      _bookmarks.addAll(prefs.getStringList('bookmarks') ?? []);
      _history.addAll(prefs.getStringList('history') ?? []);
      if (defaultTargetPlatform == TargetPlatform.windows) {
        final version = await WebViewEnvironment.getAvailableVersion();
        if (version == null) {
          throw StateError('Microsoft Edge WebView2 Runtime is required.');
        }
        _environment = await WebViewEnvironment.create();
      }
      await _downloads.loadSaved();
      if (mounted) setState(() => _ready = true);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  void dispose() {
    _address.dispose();
    _downloads.dispose();
    _environment?.dispose();
    super.dispose();
  }

  void _message(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(text), duration: const Duration(seconds: 3)),
    );
  }

  void _syncAddress() {
    final text = _tab.uri.toString();
    _address.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
  }

  void _addTab([Uri? url]) {
    setState(() {
      _tabs.add(BrowserTab(_nextId++, url ?? Uri.parse(AddressParser.home)));
      _selected = _tabs.length - 1;
      _syncAddress();
    });
  }

  void _selectTab(int index) {
    setState(() {
      _selected = index;
      _syncAddress();
    });
  }

  void _closeTab(int index) {
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
    if (tab.controller == null) {
      setState(() => tab.initialUri = uri);
      return;
    }
    try {
      await tab.controller!.loadUrl(
        urlRequest: URLRequest(url: WebUri(uri.toString())),
      );
    } catch (error) {
      _message('탐색 실패: ' + error.toString());
    }
  }

  Future<void> _back() async {
    final controller = _tab.controller;
    if (controller != null && await controller.canGoBack()) {
      await controller.goBack();
    } else if (_tabs.length > 1) {
      _closeTab(_selected);
    }
  }

  Future<void> _forward() async {
    final controller = _tab.controller;
    if (controller != null && await controller.canGoForward()) {
      await controller.goForward();
    }
  }

  Future<void> _reload() async => _tab.controller?.reload();

  void _updateLocation(BrowserTab tab, WebUri? webUri) {
    if (!mounted || !_tabs.contains(tab) || webUri == null) return;
    final uri = Uri.tryParse(webUri.toString());
    if (uri == null || !AddressParser.isRemoteHttp(uri)) return;
    setState(() {
      tab.uri = uri;
      if (identical(tab, _tab)) _syncAddress();
    });
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
    if (tab.controller == null) return;
    try {
      dynamic result = await tab.controller!.evaluateJavascript(
        source: VideoDetector.discoverScript,
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
        await tab.controller?.evaluateJavascript(
          source: AdBlocker.cosmeticScript,
        );
      } catch (_) {}
    }
    await _detectMedia(tab);
  }

  Future<void> _download(Uri uri) async {
    if (!VideoDetector.isDirectVideo(uri)) {
      _message('직접 연결된 MP4/WebM/MOV/M4V 영상만 저장 가능합니다.');
      return;
    }
    _message('영상 다운로드를 시작했습니다.');
    try {
      final item = await _downloads.download(uri);
      if (item.state == VideoDownloadState.complete) {
        _message('다운로드 완료: ' + item.fileName);
      } else if (item.state == VideoDownloadState.failed) {
        _message('다운로드 실패: ' + (item.error ?? '오류'));
      }
    } catch (error) {
      _message('다운로드 오류: ' + error.toString());
    }
  }

  Future<void> _showVideos() async {
    final tab = _tab;
    await _detectMedia(tab);
    if (!mounted) return;
    final urls = tab.videos.toList();
    if (urls.isEmpty) {
      _message('이 페이지에서 직접 저장 가능한 영상을 찾지 못했습니다.');
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
                subtitle: Text('다운로드 허용된 직접 연결 영상만 지원'),
              ),
              Expanded(
                child: ListView.builder(
                  itemCount: urls.length,
                  itemBuilder: (_, i) => ListTile(
                    leading: const Icon(Icons.movie_outlined),
                    title: Text(
                      urls[i].pathSegments.isEmpty
                          ? '동영상'
                          : urls[i].pathSegments.last,
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: Text(urls[i].host),
                    trailing: const Icon(Icons.download_outlined),
                    onTap: () {
                      Navigator.pop(sheet);
                      _download(urls[i]);
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showDownloads() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: 0.72,
          child: AnimatedBuilder(
            animation: _downloads,
            builder: (_, child) {
              final items = _downloads.items;
              return Column(
                children: [
                  const ListTile(
                    title: Text('오프라인 동영상'),
                    subtitle: Text('완료한 영상을 탭하면 기기 플레이어로 열립니다.'),
                  ),
                  Expanded(
                    child: items.isEmpty
                        ? const Center(child: Text('저장된 동영상이 없습니다.'))
                        : ListView.builder(
                            itemCount: items.length,
                            itemBuilder: (_, i) {
                              final item = items[i];
                              final completed =
                                  item.state == VideoDownloadState.complete;
                              final running =
                                  item.state == VideoDownloadState.running;
                              return ListTile(
                                title: Text(
                                  item.fileName,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                subtitle: running
                                    ? LinearProgressIndicator(
                                        value: item.progress / 100,
                                      )
                                    : Text(
                                        item.state.name +
                                            (item.error == null
                                                ? ''
                                                : ': ' + item.error!),
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                leading: Icon(
                                  completed
                                      ? Icons.play_circle_outline
                                      : Icons.download_outlined,
                                ),
                                onTap: completed
                                    ? () => _downloads.open(item)
                                    : null,
                                trailing: IconButton(
                                  tooltip: running ? '취소' : '삭제',
                                  onPressed: () => _downloads.delete(item),
                                  icon: Icon(
                                    running
                                        ? Icons.cancel_outlined
                                        : Icons.delete_outline,
                                  ),
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
                  const ListTile(
                    leading: Icon(Icons.shield_outlined),
                    title: Text('DPI 우회'),
                    subtitle: Text(
                      '네이티브 엔진 미연결: 현재 우회 기능은 동작하지 '
                      '않습니다. Windows/Android 연결 테스트 후 추가 예정.',
                    ),
                  ),
                  const ListTile(
                    leading: Icon(Icons.info_outline),
                    title: Text('Internet Browser v0.1.0'),
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

  Widget _tabStrip() => SizedBox(
        height: 42,
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
                keyboardType: TextInputType.url,
                textInputAction: TextInputAction.go,
                autocorrect: false,
                onSubmitted: _go,
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
              tooltip: '동영상 감지',
              onPressed: _showVideos,
              icon: const Icon(Icons.video_library_outlined),
            ),
            PopupMenuButton<String>(
              tooltip: '메뉴',
              onSelected: (value) {
                switch (value) {
                  case 'new':
                    _addTab();
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
                }
              },
              itemBuilder: (_) => [
                const PopupMenuItem(value: 'new', child: Text('새 탭')),
                const PopupMenuItem(value: 'refresh', child: Text('새로고침')),
                PopupMenuItem(
                    value: 'bookmark',
                    child: Text(_bookmarked ? '북마크 해제' : '북마크 추가')),
                const PopupMenuItem(
                    value: 'bookmarks', child: Text('북마크')),
                const PopupMenuItem(value: 'history', child: Text('방문 기록')),
                const PopupMenuItem(
                    value: 'downloads', child: Text('동영상 서재')),
                const PopupMenuItem(
                    value: 'settings', child: Text('광고·DPI 설정')),
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

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width > 680;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Internet Browser'),
          actions: [
            IconButton(
              tooltip: '동영상 서재',
              onPressed: _showDownloads,
              icon: const Icon(Icons.download_outlined),
            ),
            if (!wide)
              TextButton(
                onPressed: _addTab,
                child: Text(_tabs.length.toString() + ' +'),
              ),
          ],
        ),
        body: _error != null
            ? Center(child: SelectableText('브라우저 초기화 실패:\n' + _error!))
            : !_ready
                ? const Center(child: CircularProgressIndicator())
                : Column(
                    children: [
                      if (wide || _tabs.length > 1) _tabStrip(),
                      _toolbar(wide),
                      if (_tab.progress < 100)
                        LinearProgressIndicator(value: _tab.progress / 100),
                      Expanded(
                        child: IndexedStack(
                          index: _selected,
                          children: _tabs.map(_webView).toList(),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }
}
