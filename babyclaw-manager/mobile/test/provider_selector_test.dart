import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:babyclaw_manager/widgets/provider_selector.dart';

void main() {
  testWidgets('provider chips report the selected AI backend', (tester) async {
    var selected = 'claude';
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ProviderSelector(
            value: selected,
            onChanged: (value) => selected = value,
          ),
        ),
      ),
    );

    expect(find.text('Claude'), findsOneWidget);
    expect(find.text('OpenAI'), findsOneWidget);
    expect(find.text('OmniRoute'), findsOneWidget);

    await tester.tap(find.text('OpenAI'));
    await tester.pump();
    expect(selected, 'openai');

    await tester.tap(find.text('OmniRoute'));
    await tester.pump();
    expect(selected, 'omniroute');
  });
}
