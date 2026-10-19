import 'package:flutter/material.dart';

import 'dpi_options.dart';

/// ByeDPI/ciadpi presets: not the incompatible GoodbyeDPI blacklist arguments.
class DpiPresetPicker extends StatelessWidget {
  const DpiPresetPicker({
    super.key,
    required this.options,
    required this.windows,
    required this.onChanged,
  });

  final DpiOptions options;
  final bool windows;
  final ValueChanged<DpiPreset>? onChanged;

  @override
  Widget build(BuildContext context) {
    final preset = options.preset;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DropdownButtonFormField<DpiPreset>(
          key: ValueKey('dpi-preset-${preset.name}'),
          initialValue: preset,
          isExpanded: true,
          decoration: const InputDecoration(
            labelText: '인자 목록',
            border: OutlineInputBorder(),
          ),
          items: [
            for (final item in DpiPreset.values)
              DropdownMenuItem<DpiPreset>(
                value: item,
                child: Text(
                  DpiOptions.presetNames[item]!,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
          onChanged: onChanged == null
              ? null
              : (value) {
                  if (value != null) onChanged!(value);
                },
        ),
        const SizedBox(height: 8),
        Text(
          DpiOptions.presetDescriptions[preset]!,
          key: const Key('dpi-preset-description'),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 6),
        SelectableText(
          '실제 ByeDPI 인자: ${options.toArguments(windows: windows).join(' ')}',
          key: const Key('dpi-preset-arguments'),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 4),
        Text(
          '인자 저장과 실제 우회 성공은 별개입니다. GoodbyeDPI의 blacklist '
          '인자는 ByeDPI에 그대로 사용할 수 없습니다.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}
