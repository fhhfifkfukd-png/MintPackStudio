package com.mintpack.runtime

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.BroadcastReceiver
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

class MainActivity : Activity() {
    companion object {
        private const val APP_ORIGIN = "https://appassets.androidplatform.net"
        private const val PAGE_URL = "$APP_ORIGIN/assets/site/index.html"
        private const val PICK_FILE_REQUEST = 7001
        private const val NOTIFICATION_PERMISSION_REQUEST = 7002
        private const val BRIDGE_SCRIPT = """
        (() => {
          const pending = new Map(); let sequence = 0;
          const send = (action, data = {}) => new Promise((resolve, reject) => {
            if (!window.mintNative || typeof window.mintNative.postMessage !== 'function') {
              reject(new Error('پل بومی در دسترس نیست.')); return;
            }
            const id = String(++sequence);
            pending.set(id, {resolve, reject});
            window.mintNative.postMessage(JSON.stringify({id, action, ...data}));
            setTimeout(() => { const p = pending.get(id); if (p) { pending.delete(id); p.reject(new Error('مهلت درخواست تمام شد.')); } }, 40000);
          });
          Object.defineProperty(window, '__mintResolve', {configurable:false, value:(message) => {
            const p = pending.get(String(message.id)); if (!p) return; pending.delete(String(message.id));
            if (!message.ok) { p.reject(new Error(message.error || 'درخواست Native ناموفق بود.')); return; }
            let data = message.data;
            if (typeof data === 'string') { try { data = JSON.parse(data); } catch (_) {} }
            if (message.httpStatus !== undefined) data = {httpStatus:message.httpStatus, response:data};
            p.resolve(data);
          }});
          // JavaScriptReplyProxy.postMessage() arrives on this WebMessageListener callback.
          window.mintNative.onmessage = (event) => {
            try { window.__mintResolve(JSON.parse(event.data)); }
            catch (_) { /* Ignore malformed native messages; pending calls will time out safely. */ }
          };
          Object.defineProperty(window, 'AppMint', {configurable:false, value:Object.freeze({
            rubikaRequest: ({token, method, payload = {}} = {}) => send('rubikaRequest', {token, method, payload}),
            saveBot: ({token, label = 'ربات جدید'} = {}) => send('saveBot', {token, label}),
            removeBot: (botId) => send('removeBot', {botId}),
            removeAllBots: () => send('removeAllBots'),
            listBots: () => send('listBots'),
            onUpdate: (handler) => { if (typeof handler !== 'function') throw new TypeError('handler must be a function'); const listener = (event) => handler(event.detail); window.addEventListener('AppMintUpdate', listener); return () => window.removeEventListener('AppMintUpdate', listener); },
            startPolling: () => send('startPolling'),
            stopPolling: () => send('stopPolling')
          })});
        })();
        """
    }

    private lateinit var webView: WebView
    private lateinit var config: JSONObject
    private val bridgeScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var updateReceiverRegistered = false
    private var pageReady = false
    private var activityResumed = false
    private val botUpdatesReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: android.content.Context?, intent: Intent?) {
            val botId = intent?.getStringExtra("botId") ?: return
            if (!::webView.isInitialized || !pageReady || !activityResumed) return
            dispatchPendingUpdates(botId)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        config = readConfig()
        applyWindowSettings()
        webView = WebView(this)
        setContentView(webView)
        configureWebView()
        ContextCompat.registerReceiver(this, botUpdatesReceiver, IntentFilter(RubikaPollingService.ACTION_UPDATES), ContextCompat.RECEIVER_NOT_EXPORTED)
        updateReceiverRegistered = true
        webView.loadUrl(PAGE_URL)
    }

    private fun readConfig(): JSONObject = try {
        assets.open("mintpack-config.json").bufferedReader().use { JSONObject(it.readText()) }
    } catch (_: Exception) { JSONObject() }

    private fun applyWindowSettings() {
        val status = config.optString("statusBarColor", "#17152d")
        val navigation = config.optString("navigationBarColor", "#ffffff")
        runCatching { window.statusBarColor = Color.parseColor(status) }
        runCatching { window.navigationBarColor = Color.parseColor(navigation) }
        window.decorView.systemUiVisibility = if (navigation.equals("#ffffff", true)) {
            View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        } else 0
        if (config.optBoolean("fullScreen", false)) {
            window.setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN, WindowManager.LayoutParams.FLAG_FULLSCREEN)
        }
    }

    private fun configureWebView() {
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        webView.settings.apply {
            javaScriptEnabled = config.optBoolean("javascriptEnabled", true)
            domStorageEnabled = config.optBoolean("offlineStorage", true)
            databaseEnabled = config.optBoolean("offlineStorage", true)
            allowFileAccess = false
            allowContentAccess = false
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            if (Build.VERSION.SDK_INT >= 26) safeBrowsingEnabled = true
            mediaPlaybackRequiresUserGesture = true
        }
        webView.isVerticalScrollBarEnabled = false
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                pageReady = true
                if (config.optBoolean("nativeBridgeEnabled", false) && activityResumed) {
                    BotStore(this@MainActivity).pendingBotIds().forEach(::dispatchPendingUpdates)
                }
            }
            override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?) =
                request?.url?.let(assetLoader::shouldInterceptRequest)
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                if (request == null) return true
                if (!request.isForMainFrame) return false
                val uri = request.url
                if (uri.scheme == "https" && uri.host == "appassets.androidplatform.net") return false
                if (uri.scheme == "https" || uri.scheme == "http") {
                    runCatching { startActivity(Intent(Intent.ACTION_VIEW, uri)) }
                    return true
                }
                return true
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
                return try {
                    startActivityForResult(intent, PICK_FILE_REQUEST)
                    true
                } catch (_: Exception) {
                    fileChooserCallback = null
                    false
                }
            }
        }
        webView.setDownloadListener { url, _, _, _, _ ->
            runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
                .onFailure { Toast.makeText(this, "برای دانلود، لینک را در مرورگر باز کنید.", Toast.LENGTH_LONG).show() }
        }

        if (config.optBoolean("nativeBridgeEnabled", false)) installSecureBridge()
    }

    private fun installSecureBridge() {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER) ||
            !WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            Toast.makeText(this, "نسخه WebView دستگاه از پل امن پشتیبانی نمی‌کند.", Toast.LENGTH_LONG).show()
            return
        }
        WebViewCompat.addWebMessageListener(
            webView,
            "mintNative",
            setOf(APP_ORIGIN)
        ) { _, message: WebMessageCompat, sourceOrigin, isMainFrame, replyProxy ->
            if (!isMainFrame || sourceOrigin.toString() != APP_ORIGIN) return@addWebMessageListener
            val rawMessage = message.data
            if (rawMessage.isNullOrBlank() || rawMessage.length > 1_000_000) {
                replyProxy.postMessage(JSONObject().put("id", "").put("ok", false).put("error", "اندازه پیام پل معتبر نیست.").toString())
                return@addWebMessageListener
            }
            val request = runCatching { JSONObject(rawMessage) }.getOrNull()
            if (request == null) {
                replyProxy.postMessage(JSONObject().put("id", "").put("ok", false).put("error", "پیام پل معتبر نیست.").toString())
                return@addWebMessageListener
            }
            val requestId = request.optString("id")
            bridgeScope.launch {
                val response = try {
                    dispatchBridge(request)
                } catch (error: Exception) {
                    JSONObject().put("id", requestId).put("ok", false)
                        .put("error", error.message ?: "درخواست ناموفق بود.")
                }
                replyProxy.postMessage(response.toString())
            }
        }
        WebViewCompat.addDocumentStartJavaScript(webView, BRIDGE_SCRIPT, setOf(APP_ORIGIN))
    }

    private fun dispatchPendingUpdates(botId: String) {
        val updates = BotStore(this).drainUpdates(botId)
        if (updates.length() == 0 || !::webView.isInitialized) return
        val event = JSONObject().put("botId", botId).put("updates", updates).toString()
        webView.evaluateJavascript("window.dispatchEvent(new CustomEvent('AppMintUpdate',{detail:JSON.parse(${JSONObject.quote(event)})}));", null)
    }

    private suspend fun dispatchBridge(request: JSONObject): JSONObject {
        val id = request.optString("id")
        return when (request.optString("action")) {
            "rubikaRequest" -> {
                val token = request.optString("token")
                val method = request.optString("method")
                val payload = request.optJSONObject("payload") ?: JSONObject()
                val result = try {
                    withContext(Dispatchers.IO) { RubikaApi.request(token, method, payload) }
                } catch (_: Exception) {
                    // Never propagate transport exception text: OkHttp messages can include token-bearing URLs.
                    throw IllegalStateException("ارتباط با API روبیکا ناموفق بود؛ اتصال و ورودی‌ها را بررسی کنید.")
                }
                JSONObject().put("id", id).put("ok", true).put("data", result.second).put("httpStatus", result.first)
            }
            "saveBot" -> {
                val token = request.optString("token")
                val label = request.optString("label", "ربات جدید")
                val bot = BotStore(this).add(label, token)
                JSONObject().put("id", id).put("ok", true)
                    .put("data", JSONObject().put("botId", bot.id).put("label", bot.label))
            }
            "removeBot" -> {
                val store = BotStore(this)
                store.remove(request.optString("botId"))
                if (store.list().isEmpty()) {
                    store.setPollingWanted(false)
                    stopService(Intent(this, RubikaPollingService::class.java))
                }
                JSONObject().put("id", id).put("ok", true).put("data", JSONObject().put("removed", true))
            }
            "removeAllBots" -> {
                stopService(Intent(this, RubikaPollingService::class.java))
                BotStore(this).removeAll()
                JSONObject().put("id", id).put("ok", true).put("data", JSONObject().put("removedAll", true))
            }
            "listBots" -> JSONObject().put("id", id).put("ok", true).put("data", JSONObject(BotStore(this).publicJson()))
            "startPolling" -> {
                if (!config.optBoolean("rubikaMode", false)) throw IllegalStateException("Rubika Bot Mode هنگام ساخت فعال نشده است.")
                if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_PERMISSION_REQUEST)
                    throw IllegalStateException("ابتدا دسترسی اعلان‌ها را فعال کنید و دوباره تلاش کنید.")
                }
                val botStore = BotStore(this)
                if (botStore.list().isEmpty()) throw IllegalStateException("ابتدا حداقل یک ربات ذخیره کنید.")
                botStore.setPollingWanted(true)
                val intent = Intent(this, RubikaPollingService::class.java).setAction(RubikaPollingService.ACTION_START)
                ContextCompat.startForegroundService(this, intent)
                JSONObject().put("id", id).put("ok", true).put("data", JSONObject().put("started", true))
            }
            "stopPolling" -> {
                BotStore(this).setPollingWanted(false)
                stopService(Intent(this, RubikaPollingService::class.java))
                JSONObject().put("id", id).put("ok", true).put("data", JSONObject().put("stopped", true))
            }
            else -> throw IllegalArgumentException("عملیات Native پشتیبانی نمی‌شود.")
        }
    }

    @Deprecated("Legacy file chooser callback for WebView")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_FILE_REQUEST) return
        val callback = fileChooserCallback ?: return
        fileChooserCallback = null
        val uris = mutableListOf<Uri>()
        if (resultCode == RESULT_OK && data != null) {
            data.clipData?.let { clip ->
                for (i in 0 until clip.itemCount) uris.add(clip.getItemAt(i).uri)
            }
            if (uris.isEmpty()) data.data?.let(uris::add)
        }
        callback.onReceiveValue(if (uris.isEmpty()) null else uris.toTypedArray())
    }

    override fun onResume() {
        super.onResume()
        activityResumed = true
        if (pageReady && config.optBoolean("nativeBridgeEnabled", false)) {
            BotStore(this).pendingBotIds().forEach(::dispatchPendingUpdates)
        }
    }

    override fun onPause() {
        activityResumed = false
        super.onPause()
    }

    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        bridgeScope.cancel()
        if (updateReceiverRegistered) {
            runCatching { unregisterReceiver(botUpdatesReceiver) }
            updateReceiverRegistered = false
        }
        if (::webView.isInitialized) {
            webView.stopLoading()
            webView.destroy()
        }
        super.onDestroy()
    }

}
