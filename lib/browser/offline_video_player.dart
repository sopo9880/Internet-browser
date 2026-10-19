import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

import 'android_media_bridge.dart';
import 'video_library.dart';

/// Local offline-player screen. Browser video downloads only, not a copy
/// of YouTube's account, recommendations or protected streaming services.
class OfflineVideoPlayer extends StatefulWidget {
  const OfflineVideoPlayer({
    super.key,
    required this.items,
    required this.initialIndex,
    required this.onPositionChanged,
  });

  final List<SavedVideo> items;
  final int initialIndex;
  final Future<void> Function(SavedVideo, Duration) onPositionChanged;

  @override
  State<OfflineVideoPlayer> createState() => _OfflineVideoPlayerState();
}

class _OfflineVideoPlayerState extends State<OfflineVideoPlayer> {
  late final Player _player = Player();
  late final VideoController _video = VideoController(_player);
  final FocusNode _keyboard = FocusNode();
  final List<StreamSubscription<dynamic>> _subscriptions = [];
  late int _index;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  bool _playing = false;
  bool _controlsVisible = true;
  bool _locked = false;
  bool _loop = false;
  bool _temporaryFast = false;
  double _rate = 1.0;
  double _volume = 100.0;
  BoxFit _fit = BoxFit.contain;
  Tracks _tracks = const Tracks();
  String? _lastError;
  int _lastSavedSecond = -1;

  SavedVideo get _item => widget.items[_index];

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex.clamp(0, widget.items.length - 1).toInt();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    _subscriptions.addAll([
      _player.stream.position.listen((value) {
        if (!mounted) return;
        setState(() => _position = value);
        if (value.inSeconds > 0 &&
            value.inSeconds ~/ 10 != _lastSavedSecond ~/ 10) {
          _lastSavedSecond = value.inSeconds;
          unawaited(widget.onPositionChanged(_item, value));
        }
      }),
      _player.stream.duration.listen((value) {
        if (mounted) setState(() => _duration = value);
      }),
      _player.stream.playing.listen((value) {
        if (!mounted) return;
        setState(() => _playing = value);
        unawaited(AndroidMediaBridge.setPlayback(
          title: _item.title, playing: value));
      }),
      _player.stream.tracks.listen((value) {
        if (mounted) setState(() => _tracks = value);
      }),
      _player.stream.completed.listen((completed) {
        if (!completed || !mounted) return;
        if (_loop) {
          unawaited(_player.seek(Duration.zero));
          unawaited(_player.play());
        } else if (_index < widget.items.length - 1) {
          unawaited(_open(_index + 1));
        }
      }),
      _player.stream.error.listen((value) {
        if (mounted) setState(() => _lastError = value);
      }),
    ]);
    AndroidMediaBridge.setMediaCommandHandler((action) async {
      if (action == 'play') await _player.play();
      if (action == 'pause') await _player.pause();
    });
    unawaited(_open(_index));
  }

  Future<void> _open(int index) async {
    if (index < 0 || index >= widget.items.length) return;
    if (_position > Duration.zero) {
      await widget.onPositionChanged(_item, _position);
    }
    setState(() {
      _index = index;
      _position = Duration.zero;
      _duration = Duration.zero;
      _lastSavedSecond = -1;
      _lastError = null;
      _controlsVisible = true;
    });
    final item = _item;
    if (!await File(item.filePath).exists()) {
      if (mounted) setState(() => _lastError = '저장된 영상 파일이 없습니다.');
      return;
    }
    try {
      await _player.open(Media(Uri.file(item.filePath).toString()));
      if (item.lastPositionMs > 0) {
        await _player.seek(Duration(milliseconds: item.lastPositionMs));
      }
      await _player.setRate(_rate);
      await _loadExternalSubtitle(item);
      await AndroidMediaBridge.setPlayback(
        title: item.title, playing: true,
      );
    } catch (error) {
      if (mounted) setState(() => _lastError = error.toString());
    }
  }

  Future<void> _loadExternalSubtitle(SavedVideo item) async {
    final path = item.subtitlePath;
    final stem = item.filePath.substring(
      0, math.max(0, item.filePath.lastIndexOf('.')),
    );
    final candidates = <String>[
      if (path != null) path,
      '$stem.srt', '$stem.vtt', '$stem.ass',
    ];
    for (final file in candidates) {
      if (await File(file).exists()) {
        try {
          await _player.setSubtitleTrack(
            SubtitleTrack.uri(Uri.file(file).toString()),
          );
          return;
        } catch (_) {
          // Unsupported subtitle file is not fatal to video playback.
        }
      }
    }
  }

  Future<void> _seekRelative(int seconds) async {
    final endMs = _duration.inMilliseconds;
    final target = _position.inMilliseconds + seconds * 1000;
    await _player.seek(Duration(
      milliseconds: target.clamp(0, math.max(endMs, 0)).toInt(),
    ));
  }

  Future<void> _fastStart() async {
    if (_temporaryFast || _locked) return;
    _temporaryFast = true;
    await _player.setRate(2.0);
    if (mounted) setState(() {});
  }

  Future<void> _fastEnd() async {
    if (!_temporaryFast) return;
    _temporaryFast = false;
    await _player.setRate(_rate);
    if (mounted) setState(() {});
  }

  Future<void> _togglePlay() async {
    await _player.playOrPause();
    unawaited(widget.onPositionChanged(_item, _position));
  }

  Future<void> _setRate(double value) async {
    _rate = value.clamp(0.25, 2.0).toDouble();
    await _player.setRate(_temporaryFast ? 2.0 : _rate);
    if (mounted) setState(() {});
  }

  Future<void> _volumeChange(double delta) async {
    _volume = (_volume + delta).clamp(0.0, 100.0).toDouble();
    await _player.setVolume(_volume);
    if (mounted) setState(() {});
  }

  void _handleKey(KeyEvent event) {
    if (event is! KeyDownEvent || _locked) return;
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.space ||
        key == LogicalKeyboardKey.keyK) {
      unawaited(_togglePlay());
    } else if (key == LogicalKeyboardKey.keyJ) {
      unawaited(_seekRelative(-10));
    } else if (key == LogicalKeyboardKey.keyL) {
      unawaited(_seekRelative(10));
    } else if (key == LogicalKeyboardKey.arrowLeft) {
      unawaited(_seekRelative(-5));
    } else if (key == LogicalKeyboardKey.arrowRight) {
      unawaited(_seekRelative(5));
    } else if (key == LogicalKeyboardKey.arrowUp) {
      unawaited(_volumeChange(5));
    } else if (key == LogicalKeyboardKey.arrowDown) {
      unawaited(_volumeChange(-5));
    } else if (key == LogicalKeyboardKey.keyM) {
      unawaited(_player.setVolume(_volume > 0 ? 0 : 100));
      setState(() => _volume = _volume > 0 ? 0 : 100);
    } else if (key == LogicalKeyboardKey.keyF) {
      setState(() => _controlsVisible = !_controlsVisible);
    } else if (key == LogicalKeyboardKey.keyC) {
      unawaited(_player.setSubtitleTrack(
        _player.state.track.subtitle.id == 'no'
            ? SubtitleTrack.auto() : SubtitleTrack.no(),
      ));
    } else if (key == LogicalKeyboardKey.comma) {
      unawaited(_setRate(math.max(0.25, _rate - 0.25)));
    } else if (key == LogicalKeyboardKey.period) {
      unawaited(_setRate(math.min(2.0, _rate + 0.25)));
    } else {
      const digits = [
        LogicalKeyboardKey.digit0, LogicalKeyboardKey.digit1,
        LogicalKeyboardKey.digit2, LogicalKeyboardKey.digit3,
        LogicalKeyboardKey.digit4, LogicalKeyboardKey.digit5,
        LogicalKeyboardKey.digit6, LogicalKeyboardKey.digit7,
        LogicalKeyboardKey.digit8, LogicalKeyboardKey.digit9,
      ];
      final digit = digits.indexOf(key);
      if (digit >= 0 && _duration > Duration.zero) {
        unawaited(_player.seek(
          Duration(milliseconds: _duration.inMilliseconds * digit ~/ 10),
        ));
      }
    }
  }

  String _clock(Duration value) {
    final seconds = value.inSeconds;
    final h = seconds ~/ 3600;
    final m = (seconds % 3600) ~/ 60;
    final s = seconds % 60;
    final mm = m.toString().padLeft(2, '0');
    final ss = s.toString().padLeft(2, '0');
    return h == 0 ? '$mm:$ss' : '$h:$mm:$ss';
  }

  Future<void> _showOptions() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheet) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const ListTile(title: Text('동영상 플레이어 설정')),
            ListTile(
              leading: const Icon(Icons.speed_outlined),
              title: const Text('재생 배속'),
              subtitle: Text('${_rate.toStringAsFixed(2)}배'),
              onTap: () async {
                final value = await showDialog<double>(
                  context: sheet,
                  builder: (dialog) => SimpleDialog(
                    title: const Text('재생 속도'),
                    children: [
                      for (final speed in const [
                        0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0
                      ])
                        SimpleDialogOption(
                          onPressed: () => Navigator.pop(dialog, speed),
                          child: Text('$speed×'),
                        ),
                    ],
                  ),
                );
                if (value != null) await _setRate(value);
                if (sheet.mounted) Navigator.pop(sheet);
              },
            ),
            ListTile(
              leading: const Icon(Icons.high_quality_outlined),
              title: const Text('화질 / 비디오 트랙'),
              subtitle: Text(
                _tracks.video.length <= 2
                    ? '저장된 단일 화질 · ${_item.quality ?? '원본'}'
                    : '파일에 포함된 비디오 트랙 선택',
              ),
              onTap: _tracks.video.length <= 2 ? null : () async {
                await showDialog<void>(
                  context: sheet,
                  builder: (dialog) => SimpleDialog(
                    title: const Text('사용 가능한 비디오 트랙'),
                    children: [
                      for (final track in _tracks.video)
                        SimpleDialogOption(
                          onPressed: () {
                            unawaited(_player.setVideoTrack(track));
                            Navigator.pop(dialog);
                          },
                          child: Text(track.h == null
                              ? (track.title ?? track.id)
                              : '${track.h}p · ${track.title ?? track.id}'),
                        ),
                    ],
                  ),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.subtitles_outlined),
              title: const Text('자막 트랙'),
              subtitle: const Text('내장 자막 및 동영상과 같은 이름의 SRT/VTT/ASS'),
              onTap: () async {
                await showDialog<void>(
                  context: sheet,
                  builder: (dialog) => SimpleDialog(
                    title: const Text('자막 선택'),
                    children: [
                      SimpleDialogOption(
                        child: const Text('자막 끄기'),
                        onPressed: () {
                          unawaited(_player.setSubtitleTrack(SubtitleTrack.no()));
                          Navigator.pop(dialog);
                        },
                      ),
                      for (final track in _tracks.subtitle)
                        SimpleDialogOption(
                          onPressed: () {
                            unawaited(_player.setSubtitleTrack(track));
                            Navigator.pop(dialog);
                          },
                          child: Text(track.title ?? track.language ?? track.id),
                        ),
                    ],
                  ),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.aspect_ratio_outlined),
              title: const Text('화면 맞춤'),
              subtitle: Text(_fit == BoxFit.cover ? '화면 채우기' : '원본 비율'),
              onTap: () {
                setState(() => _fit =
                    _fit == BoxFit.contain ? BoxFit.cover : BoxFit.contain);
                Navigator.pop(sheet);
              },
            ),
            SwitchListTile(
              title: const Text('현재 영상 반복 재생'),
              value: _loop,
              onChanged: (value) {
                setState(() => _loop = value);
                Navigator.pop(sheet);
              },
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    unawaited(widget.onPositionChanged(_item, _position));
    AndroidMediaBridge.setMediaCommandHandler(null);
    unawaited(AndroidMediaBridge.stopPlayback());
    for (final sub in _subscriptions) {
      unawaited(sub.cancel());
    }
    unawaited(_player.dispose());
    _keyboard.dispose();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final endMs = math.max(1, _duration.inMilliseconds);
    final value = _position.inMilliseconds.clamp(0, endMs).toDouble();
    return Scaffold(
      backgroundColor: Colors.black,
      body: KeyboardListener(
        autofocus: true,
        focusNode: _keyboard,
        onKeyEvent: _handleKey,
        child: Stack(
          fit: StackFit.expand,
          children: [
            GestureDetector(
              onTap: () => setState(
                () => _controlsVisible = !_controlsVisible,
              ),
              onDoubleTapDown: (details) {
                if (_locked) return;
                final width = MediaQuery.sizeOf(context).width;
                unawaited(_seekRelative(
                  details.globalPosition.dx < width / 2 ? -10 : 10,
                ));
              },
              onLongPressStart: (_) => unawaited(_fastStart()),
              onLongPressEnd: (_) => unawaited(_fastEnd()),
              onVerticalDragUpdate: (details) {
                if (details.primaryDelta != null && !_locked) {
                  unawaited(_volumeChange(-details.primaryDelta! / 5));
                }
              },
              child: Video(
                controller: _video,
                controls: NoVideoControls,
                fit: _fit,
                pauseUponEnteringBackgroundMode: false,
              ),
            ),
            if (_temporaryFast)
              const Align(
                alignment: Alignment.topCenter,
                child: SafeArea(child: Chip(label: Text('2× 재생'))),
              ),
            if (_lastError != null)
              Align(
                alignment: Alignment.center,
                child: Text(
                  _lastError!,
                  style: const TextStyle(color: Colors.white),
                  textAlign: TextAlign.center,
                ),
              ),
            if (_controlsVisible || _locked)
              SafeArea(
                child: Column(
                  children: [
                    Row(
                      children: [
                        IconButton(
                          tooltip: '닫기',
                          onPressed: () => Navigator.maybePop(context),
                          icon: const Icon(Icons.arrow_back, color: Colors.white),
                        ),
                        Expanded(
                          child: Text(
                            _item.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: Colors.white),
                          ),
                        ),
                        IconButton(
                          tooltip: _locked ? '화면 잠금 해제' : '화면 조작 잠금',
                          onPressed: () => setState(() => _locked = !_locked),
                          icon: Icon(
                            _locked ? Icons.lock : Icons.lock_open,
                            color: Colors.white,
                          ),
                        ),
                        if (!_locked && AndroidMediaBridge.supported)
                          IconButton(
                            tooltip: '화면 속 화면(PiP)',
                            onPressed: () => unawaited(
                              AndroidMediaBridge.enterPictureInPicture()),
                            icon: const Icon(Icons.picture_in_picture_alt,
                                color: Colors.white),
                          ),
                        if (!_locked)
                          IconButton(
                            tooltip: '재생 설정',
                            onPressed: _showOptions,
                            icon: const Icon(Icons.settings,
                                color: Colors.white),
                          ),
                      ],
                    ),
                    const Spacer(),
                    if (!_locked) ...[
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          IconButton(
                            tooltip: '이전 영상',
                            iconSize: 38,
                            onPressed: _index > 0
                                ? () => unawaited(_open(_index - 1)) : null,
                            icon: const Icon(Icons.skip_previous,
                                color: Colors.white),
                          ),
                          IconButton(
                            tooltip: '10초 뒤로',
                            iconSize: 42,
                            onPressed: () => unawaited(_seekRelative(-10)),
                            icon: const Icon(Icons.replay_10,
                                color: Colors.white),
                          ),
                          IconButton(
                            tooltip: _playing ? '일시정지' : '재생',
                            iconSize: 62,
                            onPressed: () => unawaited(_togglePlay()),
                            icon: Icon(
                              _playing ? Icons.pause_circle : Icons.play_circle,
                              color: Colors.white,
                            ),
                          ),
                          IconButton(
                            tooltip: '10초 앞으로',
                            iconSize: 42,
                            onPressed: () => unawaited(_seekRelative(10)),
                            icon: const Icon(Icons.forward_10,
                                color: Colors.white),
                          ),
                          IconButton(
                            tooltip: '다음 영상',
                            iconSize: 38,
                            onPressed: _index < widget.items.length - 1
                                ? () => unawaited(_open(_index + 1)) : null,
                            icon: const Icon(Icons.skip_next,
                                color: Colors.white),
                          ),
                        ],
                      ),
                      Row(
                        children: [
                          const SizedBox(width: 12),
                          Text(_clock(_position),
                              style: const TextStyle(color: Colors.white)),
                          Expanded(
                            child: Slider(
                              value: value,
                              min: 0,
                              max: endMs.toDouble(),
                              onChanged: (v) => setState(() =>
                                  _position = Duration(milliseconds: v.toInt())),
                              onChangeEnd: (v) => unawaited(_player.seek(
                                  Duration(milliseconds: v.toInt()))),
                            ),
                          ),
                          Text(_clock(_duration),
                              style: const TextStyle(color: Colors.white)),
                          const SizedBox(width: 12),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
