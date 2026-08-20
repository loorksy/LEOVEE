import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:get/get.dart';

import 'package:babyclaw_manager/controllers/auth_controller.dart';
import 'package:babyclaw_manager/screens/lock_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    Get.testMode = true;
    Get.put(AuthController());
  });

  tearDown(Get.reset);

  testWidgets('wrong PIN shows an error and stays on lock screen', (tester) async {
    await tester.pumpWidget(
      GetMaterialApp(
        home: const LockScreen(),
        getPages: [
          GetPage(
            name: '/settings',
            page: () => const Scaffold(body: Text('settings-ok')),
          ),
        ],
      ),
    );

    await tester.enterText(find.byType(TextField), '0000');
    await tester.tap(find.text('دخول'));
    await tester.pump();

    expect(find.text('رمز الدخول غير صحيح'), findsOneWidget);
    expect(find.text('settings-ok'), findsNothing);
  });

  testWidgets('correct PIN opens settings', (tester) async {
    await tester.pumpWidget(
      GetMaterialApp(
        home: const LockScreen(),
        getPages: [
          GetPage(
            name: '/settings',
            page: () => const Scaffold(body: Text('settings-ok')),
          ),
        ],
      ),
    );

    await tester.enterText(find.byType(TextField), '2026');
    await tester.tap(find.text('دخول'));
    await tester.pumpAndSettle();

    expect(find.text('settings-ok'), findsOneWidget);
  });
}
