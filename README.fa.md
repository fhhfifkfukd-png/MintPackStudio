# MintPack Studio — نسخه توسعه‌ای ۰٫۱٫۰

MintPack Studio یک بسته‌بند پروژه وب به اپلیکیشن اندروید است. این مخزن شامل رابط فارسی، سرویس خصوصی ساخت Gradle، قالب اندروید Kotlin، پل امن JavaScript/Native و حالت اختیاری Rubika Bot Mode است.

> **وضعیت تحویل:** سورس و تست‌های سرویس در این محیط آماده و قابل دریافت‌اند؛ اما APK آزمایشی ضمیمه نشده است. در محیط اجرای فعلی Android SDK، ابزارهای Build Tools و `apksigner` و Gradle نصب نیستند؛ بنابراین ساخت و امضای واقعی APK در این جلسه قابل اجرا نبود. سرویس به‌جای تولید فایل جعلی، در نبود ابزار لازم Job را ناموفق اعلام می‌کند. ساخت روی رایانه/سرور دارای SDK باید قبل از انتشار با دستورهای این راهنما انجام و روی دستگاه واقعی آزمایش شود.

## اجزای مخزن

```text
MintPackStudio/
├── studio-web/                 # رابط فارسی RTL (HTML/CSS/JS)
├── service/                    # FastAPI و موتور ساخت Gradle
│   ├── app/archive.py           # استخراج امن ZIP و پیدا کردن index.html
│   ├── app/config.py            # اعتبارسنجی تنظیمات و تولید Manifest
│   ├── app/builder.py           # تولید پروژه Android، کامپایل و تأیید امضا
│   └── app/main.py              # API احراز هویت‌شده
├── android-template/            # پروژه قابل بازکردن در Android Studio
│   └── app/src/main/java/com/mintpack/runtime/
│       ├── MainActivity.kt      # WebView و پل امن پیام
│       ├── RubikaApi.kt         # کلاینت HTTPS روبیکا
│       ├── SecretStore.kt       # AES/GCM با Android Keystore
│       ├── BotStore.kt          # چندرباتی و صف updateها
│       ├── RubikaPollingService.kt
│       └── BootNoticeReceiver.kt
├── examples/                    # پروژه وب و ZIP نمونه
├── docs/                        # توضیح API و مدل امنیت
└── docker-compose.yml
```

## نیازمندی‌ها

- JDK 17 یا بالاتر (برای این پیکربندی JDK 17 پیشنهاد می‌شود).
- Android SDK با Platform API 36 و Android SDK Build-Tools شامل `apksigner`.
- Gradle 9.5.0 برای اجرای سرویس ساخت.
- Python 3.11 یا جدیدتر برای اجرای محلی سرویس.
- Docker و Docker Compose برای استقرار ساده‌تر.

نسخه‌های پیکربندی‌شده در پروژه: Android Gradle Plugin `9.3.0`، Kotlin Gradle Plugin `2.4.21`، Gradle `9.5.0`، AndroidX WebKit `1.18.0`، AndroidX Core KTX `1.17.0` و OkHttp `4.12.0`.

## اجرای رابط و API در حالت توسعه

از ریشه مخزن:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

python -m http.server 8080 --directory studio-web
```

در ترمینال دوم:

```bash
export MINTPACK_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export MINTPACK_DATA_DIR="./mintpack-data"
uvicorn service.app.main:app --host 127.0.0.1 --port 8000
```

در Windows، متغیرهای محیطی را با دستور PowerShell (`$env:MINTPACK_API_KEY=...`) تنظیم کنید. سپس `http://localhost:8080` را باز کنید، نشانی سرویس را `http://127.0.0.1:8000` بگذارید، همان API Key را وارد و «آزمایش اتصال» را بزنید.

## استقرار سرویس ساخت با Docker

۱. Android SDK را روی میزبان نصب کنید و مجوزهای SDK را بپذیرید. حداقل این بسته‌ها لازم‌اند:

```bash
sdkmanager --licenses
sdkmanager "platforms;android-36" "build-tools;36.0.0" "platform-tools"
```

۲. پوشه داده را با دسترسی نوشتن برای UID کاربر `gradle` در کانتینر (معمولاً UID 1000) بسازید، سپس فایل نمونه محیط را کپی و کلید قوی بسازید:

```bash
mkdir -p data
sudo chown 1000:1000 data
cp .env.example .env
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

خروجی را در `.env` به‌عنوان `MINTPACK_API_KEY` بگذارید و `ANDROID_SDK_ROOT_HOST` را به مسیر Android SDK میزبان تنظیم کنید. `.env` و دایرکتوری SDK را در Git قرار ندهید.

۳. سرویس را بسازید و اجرا کنید:

```bash
docker compose up --build -d
docker compose logs -f mintpack-builder
```

در `docker-compose.yml`، سرویس فقط روی `127.0.0.1:8000` منتشر می‌شود. برای دسترسی شبکه‌ای، آن را پشت reverse proxy با HTTPS، محدودیت نرخ، احراز هویت/شبکه خصوصی و فایروال قرار دهید. پورت سرویس را مستقیم روی اینترنت عمومی باز نکنید. دامنه رابط کاربری را در `MINTPACK_CORS_ORIGINS` قرار دهید.

## ساخت یک APK

۱. در رابط، یک ZIP شامل `index.html` و assetها یا فایل‌های HTML/CSS/JS را وارد کنید.
۲. «بررسی و پیش‌نمایش» را بزنید. برای ZIP، مسیرهای داخل آرشیو حفظ می‌شوند و ورودی مناسب `index.html` شناسایی می‌شود.
۳. Package Name، نام، نسخه، جهت صفحه و مجوزهای لازم را انتخاب کنید.
۴. برای Release یک فایل JKS/keystore و alias و رمزهای امضا ارائه دهید. کلید امضا را خودتان با ابزار معتبر Java بسازید و نسخه پشتیبان آفلاین نگه دارید.
۵. آدرس سرویس خصوصی و API Key را وارد کنید و ساخت را آغاز کنید.
۶. دانلود فقط هنگامی فعال می‌شود که Gradle یک APK واقعی بسازد، APK شامل Manifest و DEX باشد و `apksigner verify` موفق شود.

نمونه ZIP در `examples/sample-web-project.zip` و نمونهٔ اتصال روبیکا در `examples/rubika-bot-demo.zip` موجود است.

## بازکردن قالب در Android Studio

پوشه `android-template` یک پروژه Android Gradle قابل بازکردن است. در Android Studio آن را Open کنید، Android SDK API 36 را نصب کنید و Sync را اجرا کنید. برای build محلی بدون سرویس، متغیرهای محیطی امضای Release را تنظیم کنید؛ یا از Build Variants/Gradle Task برای Debug استفاده کنید.

در این مخزن `gradle-wrapper.properties` وجود دارد، اما فایل اجرایی Wrapper (`gradle-wrapper.jar`) در این محیط به‌دلیل نبود دسترسی دریافت Gradle توزیع نشده است. با نصب Gradle 9.5.0 یک‌بار در پوشه `android-template` اجرا کنید:

```bash
gradle wrapper --gradle-version 9.5.0 --distribution-type bin
```

این دستور فایل‌های استاندارد Wrapper را تولید می‌کند. سپس `./gradlew assembleDebug` یا در Windows `gradlew.bat assembleDebug` را اجرا کنید.

## پل JavaScript و Kotlin

پل فقط در حالت `nativeBridgeEnabled` ثبت می‌شود و origin آن به `https://appassets.androidplatform.net` محدود است. ارتباط با `WebViewCompat.addWebMessageListener` و `addDocumentStartJavaScript` انجام می‌شود؛ از `addJavascriptInterface` استفاده نشده است.

```javascript
const response = await window.AppMint.rubikaRequest({
  token,
  method: "getMe",
  payload: {}
});

// مدیریت updateهای دریافتی در زمان فعال بودن صفحه:
const unsubscribe = window.AppMint.onUpdate(({ botId, updates }) => {
  console.log("updates", botId, updates);
});
```

پاسخ درخواست با `httpStatus` و `response` برمی‌گردد؛ بدنه JSON روبیکا بدون حدس‌زدن schema به caller تحویل می‌شود. خطاهای شبکه با متن امن و بدون متن exception حامل توکن گزارش می‌شوند.

**محتوای پروژهٔ بسته‌بندی‌شده بخشی از مبدأ مورداعتماد اپ است.** هر JavaScript محلی یا اسکریپت شخص ثالثی که در همان صفحه اجرا شود، می‌تواند به پل دسترسی پیدا کند. فقط پروژه‌ای را با Bridge فعال کنید که منبع و وابستگی‌هایش را بررسی کرده‌اید.

## Rubika Bot Mode

API بر اساس مستندات رسمی از مبدأ ثابت `https://botapi.rubika.ir` و مسیر `/v3/{token}/{method}` استفاده می‌کند. در `getUpdates`، cursor ورودی `offset_id` و مقدار بازگشتی `next_offset_id` است. updateها قبل از ذخیره cursor در صف محلی قرار می‌گیرند. token با AES/GCM و کلید غیرقابل‌استخراج Android Keystore رمز می‌شود.

برای شروع، برنامه باید در foreground باشد و کاربر صریحاً Polling را فعال کند. فاصله ۵ ثانیه هدف چرخه polling است، نه تضمین زمانی. اندروید ممکن است سرویس را متوقف کند؛ در Android 15+ سرویس `dataSync` محدودیت زمانی تجمیعی دارد و پس از سقف سیستم باید متوقف شود. گزینه روشن‌شدن گوشی فقط یادآوری نشان می‌دهد و سرویس را خودکار از Boot اجرا نمی‌کند.

**محدودیت مهم نسخه فعلی:** وقتی Activity/WebView فعال نیست، سرویس فقط updateها را دریافت و در صف محلی نگه می‌دارد؛ منطق دلخواه JavaScript پروژه در پس‌زمینه به‌صورت headless اجرا نمی‌شود. updateها با بازگشت کاربر و بارگذاری صفحه به رویداد `AppMintUpdate` تحویل می‌شوند. بنابراین برای رباتی که باید حتی بعد از بسته‌شدن برنامه مستقل پاسخ دهد، پردازش پیام باید در یک backend دائمی یا یک Runtime بومی اختصاصی پیاده‌سازی شود؛ این نسخه چنین اجرای مستقل جاوااسکریپتی را ادعا نمی‌کند.

## آزمون‌ها

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q service/tests
python -m compileall -q service
node --check studio-web/app.js
```

تست‌ها شامل ZIP تو‌در‌تو، حفظ مسیرها، Zip Slip، symlink، index مبهم/مفقود، احراز هویت API، CSP پیش‌نمایش، اعتبارسنجی نسخه و قراردادهای منبع Kotlin هستند. این تست‌ها **جایگزین build اندروید یا تست runtime روی دستگاه نیستند**. پس از نصب SDK، ساخت Release، نصب APK روی دستگاه API 24+، تست پل، مجوز اعلان و رفتار توقف سرویس را جداگانه انجام دهید.

## محدودیت‌های نسخه ۰٫۱٫۰

- وضعیت Jobها در حافظه سرویس نگهداری می‌شود؛ با restart سرویس، وضعیت Jobهای قبلی از API بازیابی نمی‌شود. برای استقرار پایدار، persistence مبتنی بر SQLite/PostgreSQL و مدیریت cleanup خروجی‌ها لازم است.
- Polling پس‌زمینه به‌تنهایی به معنای اجرای handlerهای JavaScript هنگام بسته بودن Activity نیست؛ updateها فعلاً صف می‌شوند و پس از بازگشت صفحه تحویل می‌گردند.
- پیش‌نمایش‌ها حداکثر ۲۴ ساعت نگه داشته می‌شوند و هنگام درخواست inspect بعدی پاک‌سازی می‌شوند؛ endpoint حذف دستی نیز وجود دارد.
- رابط هنوز تاریخچهٔ ساخت پایدار، مدیریت پروژه‌های ذخیره‌شده و سیستم Backup/Restore مستقل ندارد.
- تست Instrumentation/Emulator و APK نصب‌شده در این محیط اجرا نشده است.
- برای فایل‌های تکی، ساختار پوشهٔ انتخاب‌شده از مرورگر قابل تشخیص نیست؛ برای حفظ ساختار assetها ZIP ارائه کنید.
- فایل JKS و رمزها برای مدت همان Job به سرویس ساخت خصوصی ارسال می‌شوند؛ سرویس کلید بارگذاری‌شده را در پایان Job حذف می‌کند، اما مدیر سرور و میزبان build به آن دسترسی بالقوه دارند. از سرور شخص ثالث ناشناس استفاده نکنید.

## مجوز و حریم خصوصی

سورس برای بررسی، تغییر و توسعه تحویل شده است. پیش از انتشار عمومی، مجوز کتابخانه‌های وابسته، سیاست حریم خصوصی خود محصول، مدیریت کلیدهای امضا، محدودسازی منابع سرور، نگهداری فایل‌های خروجی و مقررات فروشگاه مقصد را بررسی کنید.
