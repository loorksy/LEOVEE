import 'package:flutter/material.dart';
import 'package:get/get.dart';

import '../services/storage_service.dart';

class ThemeController extends GetxController {
  ThemeController(this._storage);

  final StorageService _storage;

  final RxBool isDark = false.obs;

  @override
  void onInit() {
    super.onInit();
    isDark.value = _storage.darkMode;
  }

  Future<void> toggle() async {
    isDark.value = !isDark.value;
    await _storage.setDarkMode(isDark.value);
    Get.changeThemeMode(isDark.value ? ThemeMode.dark : ThemeMode.light);
  }
}
