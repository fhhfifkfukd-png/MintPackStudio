const $ = (id) => document.getElementById(id);
const status = (message) => { $('status').textContent = message; };

function requireBridge() {
  if (!window.AppMint) throw new Error('پل بومی موجود نیست. APK را با فعال بودن Rubika Bot Mode بسازید.');
  return window.AppMint;
}

async function refreshBots() {
  const api = requireBridge();
  const result = await api.listBots();
  $('bots').replaceChildren();
  (result.bots || []).forEach((bot) => {
    const item = document.createElement('li');
    item.textContent = `${bot.label} · ${bot.id}`;
    $('bots').append(item);
  });
}

$('save').addEventListener('click', async () => {
  try {
    const token = $('token').value.trim();
    if (!token) throw new Error('ابتدا توکن ربات را وارد کنید.');
    const result = await requireBridge().saveBot({token, label: $('label').value.trim() || 'ربات جدید'});
    $('token').value = '';
    status(`توکن با Android Keystore رمزنگاری و ذخیره شد. شناسه: ${result.botId}`);
    await refreshBots();
  } catch (error) { status(error.message); }
});

$('start').addEventListener('click', async () => {
  try {
    const result = await requireBridge().startPolling();
    status(result.started ? 'سرویس Polling درخواست شروع دریافت کرد.' : 'پاسخ سرویس دریافت نشد.');
  } catch (error) { status(error.message); }
});

$('stop').addEventListener('click', async () => {
  try {
    await requireBridge().stopPolling();
    status('درخواست توقف سرویس ارسال شد.');
  } catch (error) { status(error.message); }
});

if (window.AppMint) {
  window.AppMint.onUpdate(({botId, updates}) => {
    $('updates').textContent = JSON.stringify({botId, updates}, null, 2);
  });
  refreshBots().catch((error) => status(error.message));
} else {
  status('این صفحه در مرورگر عادی اجرا شده؛ برای دسترسی به Kotlin آن را در APK با Rubika Bot Mode باز کنید.');
}
