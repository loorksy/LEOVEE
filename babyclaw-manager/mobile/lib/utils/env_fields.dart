class EnvKeys {
  static const telegramToken = 'TELEGRAM_TOKEN';
  static const telegramUserId = 'TELEGRAM_USER_ID';
  static const claudeOauth = 'CLAUDE_CODE_OAUTH_TOKEN';
  static const openaiKey = 'OPENAI_API_KEY';
  static const telegramChatId = 'TELEGRAM_CHAT_ID';
  static const serverUrl = 'server_url';
  static const apiToken = 'api_token';
}

class EnvFieldSpec {
  const EnvFieldSpec({
    required this.key,
    required this.label,
    required this.hint,
    this.obscure = true,
    this.optional = false,
    this.keyboardType,
  });

  final String key;
  final String label;
  final String hint;
  final bool obscure;
  final bool optional;
  final String? keyboardType;
}

const envFields = <EnvFieldSpec>[
  EnvFieldSpec(
    key: EnvKeys.telegramToken,
    label: 'TELEGRAM_TOKEN',
    hint: 'توكن البوت من @BotFather',
  ),
  EnvFieldSpec(
    key: EnvKeys.telegramUserId,
    label: 'TELEGRAM_USER_ID',
    hint: 'معرف مستخدم تليجرام (من @userinfobot)',
    obscure: false,
    keyboardType: 'number',
  ),
  EnvFieldSpec(
    key: EnvKeys.claudeOauth,
    label: 'CLAUDE_CODE_OAUTH_TOKEN',
    hint: 'رمز المصادقة من أمر claude setup-token (يبدأ بـ sk-ant-oat)',
  ),
  EnvFieldSpec(
    key: EnvKeys.openaiKey,
    label: 'OPENAI_API_KEY',
    hint: '(اختياري) مفتاح OpenAI لنسخ الصوت',
    optional: true,
  ),
  EnvFieldSpec(
    key: EnvKeys.telegramChatId,
    label: 'TELEGRAM_CHAT_ID',
    hint: '(اختياري) معرف الدردشة للإشعارات الآلية',
    obscure: false,
    optional: true,
  ),
];
