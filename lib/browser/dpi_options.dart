import 'package:shared_preferences/shared_preferences.dart';

/// Allowlisted ByeDPI settings. No arbitrary shell commands are accepted.
enum DpiPreset { balanced, split, disorder, aggressive, custom }

class DpiOptions {
  const DpiOptions({
    this.preset = DpiPreset.balanced,
    this.split = true,
    this.splitValue = '1+s',
    this.disorder = false,
    this.disorderValue = '3+s',
    this.tlsRecord = true,
    this.tlsValue = '1+s',
    this.autoRetry = true,
    this.httpModification = false,
    this.fakePacket = false,
    this.fakeTtl = 8,
  });

  final DpiPreset preset;
  final bool split;
  final String splitValue;
  final bool disorder;
  final String disorderValue;
  final bool tlsRecord;
  final String tlsValue;
  final bool autoRetry;
  final bool httpModification;
  final bool fakePacket;
  final int fakeTtl;

  static const _prefix = 'dpi_options_';
  static const presetNames = {
    DpiPreset.balanced: '기본 (권장)',
    DpiPreset.split: '분할 전송',
    DpiPreset.disorder: '역순 전송',
    DpiPreset.aggressive: '강화 우회',
    DpiPreset.custom: '사용자 지정',
  };

  static bool validPosition(String value) =>
      RegExp(r'^-?[0-9]{1,5}(\:[0-9]{1,3}){0,2}(\+[shnem]{1,3})?$')
          .hasMatch(value);

  List<String> toArguments({required bool windows}) {
    final args = <String>['-i', '127.0.0.1', '-p', '1080'];
    final defaultDisorder = windows ? '3+s' : '1';
    switch (preset) {
      case DpiPreset.balanced:
        args.addAll(['--split', '1+s', '--auto', 'torst',
          '--tlsrec', '1+s']);
        break;
      case DpiPreset.split:
        args.addAll(['--split', '1+s', '--tlsrec', '1+s']);
        break;
      case DpiPreset.disorder:
        args.addAll(['--split', '1+s', '--disorder', defaultDisorder]);
        break;
      case DpiPreset.aggressive:
        args.addAll(['--split', '1+s', '--disorder', defaultDisorder,
          '--auto', 'torst', '--tlsrec', '1+s', '--mod-http', 'h,d']);
        break;
      case DpiPreset.custom:
        if (split && validPosition(splitValue)) {
          args.addAll(['--split', splitValue]);
        }
        if (disorder && validPosition(disorderValue)) {
          args.addAll(['--disorder', disorderValue]);
        }
        if (tlsRecord && validPosition(tlsValue)) {
          args.addAll(['--tlsrec', tlsValue]);
        }
        if (autoRetry) args.addAll(['--auto', 'torst']);
        if (httpModification) args.addAll(['--mod-http', 'h,d']);
        if (fakePacket) {
          args.addAll(['--fake', '1', '--ttl', '${fakeTtl.clamp(1, 64)}']);
        }
        break;
    }
    return args;
  }

  DpiOptions copyWith({
    DpiPreset? preset,
    bool? split,
    String? splitValue,
    bool? disorder,
    String? disorderValue,
    bool? tlsRecord,
    String? tlsValue,
    bool? autoRetry,
    bool? httpModification,
    bool? fakePacket,
    int? fakeTtl,
  }) => DpiOptions(
    preset: preset ?? this.preset,
    split: split ?? this.split,
    splitValue: splitValue ?? this.splitValue,
    disorder: disorder ?? this.disorder,
    disorderValue: disorderValue ?? this.disorderValue,
    tlsRecord: tlsRecord ?? this.tlsRecord,
    tlsValue: tlsValue ?? this.tlsValue,
    autoRetry: autoRetry ?? this.autoRetry,
    httpModification: httpModification ?? this.httpModification,
    fakePacket: fakePacket ?? this.fakePacket,
    fakeTtl: fakeTtl ?? this.fakeTtl,
  );

  static DpiOptions fromPrefs(SharedPreferences prefs) {
    final raw = prefs.getString('${_prefix}preset');
    final preset = DpiPreset.values.firstWhere(
      (option) => option.name == raw,
      orElse: () => DpiPreset.balanced,
    );
    return DpiOptions(
      preset: preset,
      split: prefs.getBool('${_prefix}split') ?? true,
      splitValue: prefs.getString('${_prefix}split_value') ?? '1+s',
      disorder: prefs.getBool('${_prefix}disorder') ?? false,
      disorderValue: prefs.getString('${_prefix}disorder_value') ?? '3+s',
      tlsRecord: prefs.getBool('${_prefix}tls') ?? true,
      tlsValue: prefs.getString('${_prefix}tls_value') ?? '1+s',
      autoRetry: prefs.getBool('${_prefix}auto') ?? true,
      httpModification: prefs.getBool('${_prefix}http') ?? false,
      fakePacket: prefs.getBool('${_prefix}fake') ?? false,
      fakeTtl: prefs.getInt('${_prefix}ttl') ?? 8,
    );
  }

  Future<void> save(SharedPreferences prefs) async {
    await Future.wait([
      prefs.setString('${_prefix}preset', preset.name),
      prefs.setBool('${_prefix}split', split),
      prefs.setString('${_prefix}split_value', splitValue),
      prefs.setBool('${_prefix}disorder', disorder),
      prefs.setString('${_prefix}disorder_value', disorderValue),
      prefs.setBool('${_prefix}tls', tlsRecord),
      prefs.setString('${_prefix}tls_value', tlsValue),
      prefs.setBool('${_prefix}auto', autoRetry),
      prefs.setBool('${_prefix}http', httpModification),
      prefs.setBool('${_prefix}fake', fakePacket),
      prefs.setInt('${_prefix}ttl', fakeTtl.clamp(1, 64).toInt()),
    ]);
  }
}
