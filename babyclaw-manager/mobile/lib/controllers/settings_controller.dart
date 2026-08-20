import 'package:flutter/material.dart';
import 'package:get/get.dart';

import '../services/api_service.dart';
import '../services/storage_service.dart';
import '../utils/env_fields.dart';
import '../widgets/provider_selector.dart';

class SettingsController extends GetxController {
  SettingsController(this._storage, this._api);

  final StorageService _storage;
  final ApiService _api;

  final busy = false.obs;
  final provider = 'claude'.obs;
  final serverUrl = TextEditingController();
  final apiToken = TextEditingController();
  final fields = <String, TextEditingController>{};

  @override
  void onInit() {
    super.onInit();
    for (final spec in envFields) {
      fields[spec.key] = TextEditingController(text: _storage.read(spec.key));
    }
    serverUrl.text = _storage.read(
      EnvKeys.serverUrl,
      fallback: 'https://leovee.lork.cloud',
    );
    apiToken.text = _storage.read(EnvKeys.apiToken);
    final stored = _storage.read(EnvKeys.provider, fallback: 'claude');
    provider.value = providerOptions.containsKey(stored) ? stored : 'claude';
  }

  @override
  void onClose() {
    serverUrl.dispose();
    apiToken.dispose();
    for (final controller in fields.values) {
      controller.dispose();
    }
    super.onClose();
  }

  Map<String, String> _values() {
    return {
      for (final spec in envFields) spec.key: fields[spec.key]!.text.trim(),
      EnvKeys.provider: provider.value,
    };
  }

  Future<void> _persist() {
    return _storage.writeAll({
      ..._values(),
      EnvKeys.serverUrl: serverUrl.text.trim(),
      EnvKeys.apiToken: apiToken.text.trim(),
    });
  }

  void _snack(String title, String message, {bool error = false}) {
    Get.snackbar(
      title,
      message,
      snackPosition: SnackPosition.BOTTOM,
      backgroundColor: error ? const Color(0xFF7F1D1D) : const Color(0xFF14532D),
      colorText: Colors.white,
      margin: const EdgeInsets.all(16),
      borderRadius: 16,
    );
  }

  bool _requireServer() {
    if (serverUrl.text.trim().isEmpty || apiToken.text.trim().isEmpty) {
      _snack('تحقق من الحقول', 'أدخل عنوان الخادم ورمز API', error: true);
      return false;
    }
    return true;
  }

  Future<void> saveAndDeploy() async {
    final values = _values();
    if (values[EnvKeys.telegramToken]!.isEmpty ||
        values[EnvKeys.telegramUserId]!.isEmpty) {
      _snack('تحقق من الحقول', 'TELEGRAM_TOKEN و TELEGRAM_USER_ID مطلوبان',
          error: true);
      return;
    }
    if (provider.value == 'openai' && values[EnvKeys.openaiKey]!.isEmpty) {
      _snack('تحقق من الحقول', 'أدخل OPENAI_API_KEY قبل التبديل إلى OpenAI',
          error: true);
      return;
    }
    if (!_requireServer()) return;

    busy.value = true;
    try {
      await _persist();
      final result = await _api.deploy(
        serverUrl: serverUrl.text,
        apiToken: apiToken.text,
        values: values,
      );
      _snack('تم', result['message']?.toString() ?? 'تم التحديث بنجاح');
    } catch (error) {
      _snack('خطأ', error.toString(), error: true);
    } finally {
      busy.value = false;
    }
  }

  Future<void> switchProvider(String next) async {
    if (next == 'openai' &&
        (fields[EnvKeys.openaiKey]?.text.trim().isEmpty ?? true)) {
      _snack('تحقق من الحقول', 'أدخل OPENAI_API_KEY ثم احفظ قبل التبديل إلى OpenAI',
          error: true);
      return;
    }
    provider.value = next;
    if (!_requireServer()) return;

    busy.value = true;
    try {
      await _persist();
      final result = await _api.switchProvider(
        serverUrl: serverUrl.text,
        apiToken: apiToken.text,
        provider: next,
      );
      _snack('المزود', result['message']?.toString() ?? 'تم التبديل');
    } catch (error) {
      _snack('خطأ', error.toString(), error: true);
    } finally {
      busy.value = false;
    }
  }

  Future<void> testConnection() async {
    if (!_requireServer()) return;
    busy.value = true;
    try {
      await _persist();
      await _api.testConnection(
        serverUrl: serverUrl.text,
        apiToken: apiToken.text,
      );
      _snack('الاتصال', 'تم الوصول إلى الخادم بنجاح');
    } catch (error) {
      _snack('خطأ', error.toString(), error: true);
    } finally {
      busy.value = false;
    }
  }

  Future<void> restartBot() async {
    if (!_requireServer()) return;
    busy.value = true;
    try {
      await _persist();
      final result = await _api.restart(
        serverUrl: serverUrl.text,
        apiToken: apiToken.text,
      );
      _snack('الوكيل', result['message']?.toString() ?? 'تم إعادة تشغيل الوكيل');
    } catch (error) {
      _snack('خطأ', error.toString(), error: true);
    } finally {
      busy.value = false;
    }
  }
}
