package com.mintpack.runtime

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/** Shows a user-action reminder after boot; never launches a dataSync FGS from BOOT_COMPLETED. */
class BootNoticeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        if (BotStore(context).list().isEmpty()) return
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(NotificationChannel("mintpack_boot_notice", "یادآوری ربات‌ها", NotificationManager.IMPORTANCE_DEFAULT))
        }
        val open = PendingIntent.getActivity(
            context, 77, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0)
        )
        val notification = NotificationCompat.Builder(context, "mintpack_boot_notice")
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("ربات‌های MintPack متوقف هستند")
            .setContentText("برای شروع دوباره، برنامه را باز کنید.")
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        manager.notify(8801, notification)
    }
}
