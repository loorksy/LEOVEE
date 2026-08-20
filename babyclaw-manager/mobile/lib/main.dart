import 'package:flutter/material.dart';
import 'package:get/get.dart';

import 'controllers/auth_controller.dart';
import 'controllers/settings_controller.dart';
import 'controllers/theme_controller.dart';
import 'screens/lock_screen.dart';
import 'screens/settings_screen.dart';
import 'services/api_service.dart';
import 'services/storage_service.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final storage = await StorageService().init();
  Get.put(storage, permanent: true);
  Get.put(ApiService(), permanent: true);
  Get.put(ThemeController(storage), permanent: true);
  Get.put(AuthController(), permanent: true);
  Get.put(SettingsController(storage, Get.find<ApiService>()), permanent: true);
  runApp(const BabyClawApp());
}

class BabyClawApp extends StatelessWidget {
  const BabyClawApp({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Get.find<ThemeController>();
    return Obx(
      () => GetMaterialApp(
        title: 'BabyClaw Manager',
        debugShowCheckedModeBanner: false,
        locale: const Locale('ar'),
        fallbackLocale: const Locale('ar'),
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        themeMode: theme.isDark.value ? ThemeMode.dark : ThemeMode.light,
        initialRoute: '/lock',
        getPages: [
          GetPage(name: '/lock', page: () => const LockScreen()),
          GetPage(name: '/settings', page: () => const SettingsScreen()),
        ],
      ),
    );
  }
}
