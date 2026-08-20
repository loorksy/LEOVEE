# مدير BabyClaw — تطبيق الموبايل وخادم البيئة

مشروع متكامل لإزالة موقع `leovee.lork.cloud` من الـ VPS، تثبيت وكيل [BabyClaw (yogesharc)](https://github.com/yogesharc/babyclaw)، وتشغيل خادم API صغير يستقبل إعدادات `.env` من تطبيق Flutter.

## النشر الحالي على الـ VPS

الموقع الحي: `https://leovee.lork.cloud`

- `GET /health` يعمل بدون مصادقة
- مسارات `/api/*` تتطلب `Authorization: Bearer <API_TOKEN>`
- العنوان الافتراضي داخل تطبيق Flutter هو `https://leovee.lork.cloud`
- النسخة القديمة من Leovee محفوظة على الخادم في `/opt/leovee.bak-20260820`

## تبديل مزود الذكاء الاصطناعي

من `https://leovee.lork.cloud` بعد الدخول يمكن اختيار:

- **Claude**: Anthropic مباشرة (`CLAUDE_CODE_OAUTH_TOKEN` أو `ANTHROPIC_API_KEY`)
- **OpenAI**: عبر بوابة [OmniRoute](https://github.com/diegosouzapw/OmniRoute) المحلية مع `OPENAI_API_KEY`
- **OmniRoute**: توجيه تلقائي لعدة مزودين عبر `http://127.0.0.1:20128`

التبديل يعيد كتابة `ANTHROPIC_BASE_URL` ويعيد تشغيل وكيل BabyClaw.

رمز شاشة القفل هو **`2026`**. القيمة غير مخزّنة كنص واضح داخل التطبيق؛ يُقارن الإدخال مع بصمة SHA-256.

## المتطلبات

- VPS بنظام Ubuntu وصلاحية `root`
- Flutter 3.5+ على جهاز التطوير (لبناء APK/IPA)
- Node.js 18+ (موجود تلقائياً بعد سكربت BabyClaw)

---

## 1) تثبيت وتشغيل خادم API على الـ VPS

انسخ مجلد `babyclaw-manager` إلى الخادم ثم نفّذ السكربت كـ root. السكربت يحذف ملفات وخدمات Leovee، يثبت BabyClaw، وينشر API على المنفذ `3000` عبر PM2.

```bash
# من جهازك
scp -r babyclaw-manager root@YOUR_VPS_IP:/root/

# على الـ VPS
ssh root@YOUR_VPS_IP
cd /root/babyclaw-manager
chmod +x scripts/setup-vps.sh scripts/restart-agent.sh
CONFIRM_REMOVE_LEOVEE=yes bash scripts/setup-vps.sh
```

احفظ **رمز API** الذي يطبعه السكربت في النهاية. ستدخله في التطبيق.

تشغيل يدوي بدون السكربت الكامل:

```bash
# بعد تثبيت BabyClaw وإنشاء المستخدم babyclaw
sudo mkdir -p /home/babyclaw/env-api
sudo cp -a api/. /home/babyclaw/env-api/
sudo cp scripts/restart-agent.sh /home/babyclaw/env-api/restart-agent.sh
sudo chown -R babyclaw:babyclaw /home/babyclaw/env-api

sudo -u babyclaw bash -lc 'cd /home/babyclaw/env-api && cp .env.example .env && nano .env'
# عدّل API_TOKEN إلى قيمة طويلة عشوائية

sudo npm install -g pm2
sudo -u babyclaw bash -lc 'cd /home/babyclaw/env-api && npm install --omit=dev && pm2 start ecosystem.config.cjs && pm2 save'
sudo env PATH=$PATH pm2 startup systemd -u babyclaw --hp /home/babyclaw
```

التحقق:

```bash
curl -s http://127.0.0.1:3000/health
curl -s -H "Authorization: Bearer YOUR_API_TOKEN" http://127.0.0.1:3000/api/health
```

نقاط النهاية:

| المسار | الوظيفة |
| :--- | :--- |
| `GET /health` | فحص عام بدون مصادقة |
| `GET /api/health` | اختبار الاتصال من التطبيق (يتطلب Bearer token) |
| `POST /api/env` | تحديث `/home/babyclaw/.env` ثم إعادة تشغيل جلسة tmux `main` |
| `POST /api/restart` | إعادة تشغيل الوكيل فقط |

الحماية:

- كل مسارات `/api/*` تتطلب `Authorization: Bearer <API_TOKEN>`
- يمكن تقييد العناوين عبر `ALLOWED_IPS` في `/home/babyclaw/env-api/.env`
- تُحدَّث فقط المفاتيح المعروفة (`TELEGRAM_TOKEN` وغيرها)، وليس متغيرات النظام
- يُنشأ نسخة احتياطية `.env.bak-*` قبل كل كتابة
- بعد التحديث يُعاد تشغيل الوكيل عبر tmux حتى تُحمَّل القيم الجديدة

---

## 2) بناء وتشغيل تطبيق Flutter

```bash
cd babyclaw-manager/mobile
flutter pub get
flutter run
```

على محاكي أندرويد أو آيفون، أو على هاتف حقيقي مع تفعيل وضع المطوّر.

### بناء APK (أندرويد)

```bash
cd babyclaw-manager/mobile
flutter build apk --release
# الناتج: build/app/outputs/flutter-apk/app-release.apk
```

أو عبر Docker:

```bash
cd babyclaw-manager/mobile
docker build -t babyclaw-apk .
docker create --name babyclaw-apk-copy babyclaw-apk
docker cp babyclaw-apk-copy:/out/app-release.apk ./app-release.apk
docker rm babyclaw-apk-copy
```

انقل `app-release.apk` إلى الهاتف وثبّته (قد تحتاج السماح بالتثبيت من مصادر غير المتجر).

### بناء IPA (iOS)

يتطلب جهاز macOS وXcode وحساب Apple Developer:

```bash
cd babyclaw-manager/mobile
flutter build ipa --release
```

ثم وزّع الملف عبر Transporter أو TestFlight.

### استخدام التطبيق

1. افتح التطبيق وأدخل رمز الدخول `2026`.
2. أدخل عنوان الخادم مثل `http://IP:3000` ورمز API.
3. املأ متغيرات BabyClaw.
4. **حفظ وإرسال إلى الخادم** يخزّن القيم محلياً عبر `SharedPreferences` ثم يرسلها JSON إلى API ويعيد تشغيل الوكيل.
5. **اختبار الاتصال** يتحقق من الوصول إلى الـ VPS.
6. **إعادة تشغيل الوكيل** يعيد تشغيل جلسة tmux دون تغيير `.env`.
7. أيقونة القمر/الشمس تبدّل الوضع الليلي.

---

## هيكل المجلدات

```
babyclaw-manager/
  README.md
  scripts/setup-vps.sh          # حذف Leovee + تثبيت BabyClaw + تشغيل API
  scripts/restart-agent.sh      # إعادة تشغيل tmux session main
  api/                          # Node.js + Express + PM2
  mobile/                       # تطبيق Flutter (Android + iOS)
```

لا يشغّل هذا المستودع أوامر SSH على خادمك من تلقاء نفسه. نفّذ `setup-vps.sh` على الـ VPS الذي تملكه.
