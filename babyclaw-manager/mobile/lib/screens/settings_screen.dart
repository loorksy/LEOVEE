import 'package:flutter/material.dart';
import 'package:get/get.dart';

import '../controllers/settings_controller.dart';
import '../controllers/theme_controller.dart';
import '../utils/env_fields.dart';
import '../widgets/env_field.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final settings = Get.find<SettingsController>();
    final theme = Get.find<ThemeController>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('إعدادات BabyClaw'),
        actions: [
          Obx(
            () => IconButton(
              tooltip: 'الوضع الليلي',
              onPressed: theme.toggle,
              icon: Icon(
                theme.isDark.value
                    ? Icons.light_mode_outlined
                    : Icons.dark_mode_outlined,
              ),
            ),
          ),
        ],
      ),
      body: Obx(
        () => AbsorbPointer(
          absorbing: settings.busy.value,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
            children: [
              _Card(
                title: 'الخادم',
                child: Column(
                  children: [
                    EnvField(
                      controller: settings.serverUrl,
                      label: 'عنوان الخادم / IP',
                      hint: 'مثال: http://203.0.113.10:3000',
                      obscure: false,
                      keyboardType: TextInputType.url,
                    ),
                    const SizedBox(height: 14),
                    EnvField(
                      controller: settings.apiToken,
                      label: 'رمز API',
                      hint: 'الرمز الذي طبعه سكربت الإعداد على الـ VPS',
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _Card(
                title: 'متغيرات البيئة',
                child: Column(
                  children: [
                    for (var i = 0; i < envFields.length; i++) ...[
                      EnvField(
                        controller: settings.fields[envFields[i].key]!,
                        label: envFields[i].label,
                        hint: envFields[i].hint,
                        obscure: envFields[i].obscure,
                        keyboardType: envFields[i].keyboardType == 'number'
                            ? TextInputType.number
                            : TextInputType.text,
                      ),
                      if (i != envFields.length - 1) const SizedBox(height: 14),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: settings.saveAndDeploy,
                icon: const Icon(Icons.cloud_upload_outlined),
                label: const Text('حفظ وإرسال إلى الخادم'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: settings.testConnection,
                icon: const Icon(Icons.wifi_tethering),
                label: const Text('اختبار الاتصال'),
              ),
              const SizedBox(height: 12),
              FilledButton.tonalIcon(
                onPressed: settings.restartBot,
                icon: const Icon(Icons.restart_alt),
                label: const Text('إعادة تشغيل الوكيل'),
              ),
              if (settings.busy.value) ...[
                const SizedBox(height: 20),
                const Center(child: CircularProgressIndicator()),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 14),
            child,
          ],
        ),
      ),
    );
  }
}
