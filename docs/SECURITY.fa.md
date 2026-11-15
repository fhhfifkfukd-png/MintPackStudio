# یادداشت امنیتی

## ZIP و فایل‌های وب

- مسیر مطلق، drive path، `..`، symlink و مسیرهای تداخلی رد می‌شوند.
- تعداد ورودی‌ها، حجم فایل، حجم تجمعی، نسبت فشرده‌سازی و حجم واقعی بایت‌های استخراج‌شده کنترل می‌شود.
- فایل‌های ZIP خارج از allowlist پسوندی رد می‌شوند.
- انتخاب index.html در مسیر کم‌عمق‌تر صورت می‌گیرد؛ چند index هم‌عمق باعث خطای صریح می‌شود.
- پیش‌نمایش داخل iframe با `sandbox="allow-scripts"` و CSP sandbox اجرا می‌شود و `allow-same-origin` دریافت نمی‌کند.

## WebView و Native Bridge

- bridge فقط برای origin محلی `https://appassets.androidplatform.net` ثبت می‌شود.
- پیام‌های frame فرعی رد می‌شوند.
- از `WebMessageListener` استفاده می‌شود، نه `addJavascriptInterface`.
- فایل‌دسترسی مستقیم، content access، mixed content و cleartext غیرفعال‌اند.
- لینک‌های HTTPS/HTTP خارج از origin در مرورگر خارجی باز می‌شوند.
- JavaScript محتوای بسته‌بندی‌شده به پل دسترسی دارد؛ فعال‌سازی bridge برای پروژه ناشناخته خطرناک است.

## توکن‌ها و کلید امضا

- Token ربات و صف updateهای دریافتی در SharedPreferences فقط به شکل ciphertext ذخیره می‌شوند؛ هر دو با AES-GCM و کلید غیرقابل‌استخراج Android Keystore رمز می‌شوند.
- صف update پیش از جلو بردن cursor به‌صورت پایدار commit می‌شود تا مرگ فرایند باعث حذف بی‌صدای پیام‌ها نشود؛ صف به ۵۰ update و حدود ۲۰۰ کیلوبایت محدود است.
- API Rubika ثابت و HTTPS است؛ توکن از query string/بدنه log نمی‌شود و خطاهای انتقال با exception خام به صفحه برگردانده نمی‌شوند.
- API Key سرویس ساخت باید حداقل ۳۲ نویسه تصادفی داشته باشد.
- Keystore و رمز آن برای انجام build به سرویس خصوصی ارسال می‌شود و پس از پایان Job فایل آپلودی حذف می‌گردد. این روش جایگزین HSM یا امضای کاملاً local نیست.
- API را فقط روی loopback/private network یا پشت HTTPS و reverse proxy امن منتشر کنید.

## سرویس پس‌زمینه

- سرویس فقط با اقدام کاربر شروع می‌شود.
- notification کانال دائمی و action توقف دارد.
- سرویس از نوع `dataSync` است؛ Android 15+ زمان اجرای تجمعی و محدودیت شروع از پس‌زمینه را اعمال می‌کند.
- گیرنده Boot فقط اعلان یادآوری می‌فرستد و FGS را از پس‌زمینه راه‌اندازی نمی‌کند.
