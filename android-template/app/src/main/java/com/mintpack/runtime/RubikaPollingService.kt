package com.mintpack.runtime

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** User-started foreground service. 5s is a target interval, not an OS guarantee. */
class RubikaPollingService : Service() {
    companion object {
        const val ACTION_START = "com.mintpack.runtime.action.START_POLLING"
        const val ACTION_STOP = "com.mintpack.runtime.action.STOP_POLLING"
        private const val CHANNEL_ID = "mintpack_bot_runner"
        private const val NOTIFICATION_ID = 4107
        const val ACTION_UPDATES = "com.mintpack.runtime.action.RUBIKA_UPDATES"
        private const val POLL_INTERVAL_MS = 5_000L
    }

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val workers = mutableMapOf<String, Job>()
    private lateinit var store: BotStore

    override fun onCreate() {
        super.onCreate()
        store = BotStore(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopNow()
            return START_NOT_STICKY
        }
        if (intent?.action != ACTION_START && !store.isPollingWanted()) {
            stopSelf()
            return START_NOT_STICKY
        }
        store.setPollingWanted(true)
        val botCount = store.list().size
        if (botCount == 0) {
            store.setPollingWanted(false)
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        val notification = buildNotification(botCount)
        if (Build.VERSION.SDK_INT >= 29) {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        synchronized(workers) {
            store.list().forEach { bot ->
                if (workers[bot.id]?.isActive != true) {
                    workers[bot.id] = serviceScope.launch { pollLoop(bot.id, bot.label) }
                }
            }
        }
        updateNotification()
        return START_STICKY
    }

    private suspend fun pollLoop(botId: String, label: String) {
        var backoff = POLL_INTERVAL_MS
        while (serviceScope.isActive) {
            val cycleStarted = android.os.SystemClock.elapsedRealtime()
            try {
                if (!isOnline()) {
                    delay(backoff)
                    backoff = (backoff * 2).coerceAtMost(60_000L)
                    continue
                }
                val token = store.token(botId) ?: break
                val payload = JSONObject().put("limit", 100)
                store.offset(botId)?.let { payload.put("offset_id", it) }
                val (_, raw) = withContext(Dispatchers.IO) { RubikaApi.request(token, "getUpdates", payload) }
                val result = JSONObject(raw)
                // Queue events before advancing the cursor so a process death cannot silently discard them.
                result.optJSONArray("updates")?.let { updates ->
                    if (updates.length() > 0) {
                        store.enqueueUpdates(botId, updates)
                        sendBroadcast(Intent(ACTION_UPDATES).setPackage(packageName).putExtra("botId", botId))
                    }
                }
                // Per current detailed Rubika getUpdates docs: input offset_id, output next_offset_id.
                store.saveOffset(botId, result.optString("next_offset_id").takeIf { it.isNotBlank() && it != "null" })
                backoff = POLL_INTERVAL_MS
                val elapsed = android.os.SystemClock.elapsedRealtime() - cycleStarted
                delay((POLL_INTERVAL_MS - elapsed).coerceAtLeast(0L))
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Deliberately avoid logging exception text: request URLs contain the bot token.
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(60_000L)
            }
        }
        synchronized(workers) { workers.remove(botId) }
        if (synchronized(workers) { workers.isEmpty() }) stopSelf()
    }

    private fun isOnline(): Boolean {
        val manager = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        val capabilities = manager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "اجرای ربات‌های روبیکا", NotificationManager.IMPORTANCE_LOW))
        }
    }

    private fun buildNotification(count: Int): Notification {
        val stopIntent = Intent(this, RubikaPollingService::class.java).setAction(ACTION_STOP)
        val pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0)
        val stopPending = PendingIntent.getService(this, 1, stopIntent, pendingFlags)
        val openPending = PendingIntent.getActivity(this, 2, Intent(this, MainActivity::class.java), pendingFlags)
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("MintPack · ربات‌های روبیکا")
            .setContentText("$count ربات در حال دریافت به‌روزرسانی هستند")
            .setContentIntent(openPending)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(android.R.drawable.ic_media_pause, "توقف", stopPending)
            .build()
    }

    private fun updateNotification() {
        val count = synchronized(workers) { workers.values.count { it.isActive } }
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(count))
    }

    private fun stopNow() {
        store.setPollingWanted(false)
        synchronized(workers) {
            workers.values.forEach { it.cancel() }
            workers.clear()
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        // Android 15+ calls this for dataSync's rolling 6-hour budget.
        stopNow()
    }

    override fun onDestroy() {
        serviceScope.cancel()
        synchronized(workers) { workers.clear() }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
