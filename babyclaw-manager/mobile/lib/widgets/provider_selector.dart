import 'package:flutter/material.dart';

const providerOptions = <String, String>{
  'claude': 'Claude',
  'openai': 'OpenAI',
  'omniroute': 'OmniRoute',
};

class ProviderSelector extends StatelessWidget {
  const ProviderSelector({
    super.key,
    required this.value,
    required this.onChanged,
  });

  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'بدّل عند الحاجة. OpenAI وOmniRoute يمرّان عبر بوابة OmniRoute المحلية.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final entry in providerOptions.entries)
              ChoiceChip(
                label: Text(entry.value),
                selected: value == entry.key,
                onSelected: (_) => onChanged(entry.key),
              ),
          ],
        ),
      ],
    );
  }
}
