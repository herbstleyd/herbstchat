package org.herbstleyd.herbstchat

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

object Notifier {
    const val CH_MSG = "nachrichten"
    const val CH_SYS = "system"
    const val CH_SERVICE = "verbindung"
    const val ID_SERVICE = 1
    private const val ID_NOTICE = 2
    private const val ID_ONLINE = 3

    fun channels(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_MSG, "Nachrichten", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Neue Chat-Nachrichten"; enableVibration(true)
        })
        nm.createNotificationChannel(NotificationChannel(CH_SYS, "Systemnachrichten & Kontakte", NotificationManager.IMPORTANCE_DEFAULT))
        nm.createNotificationChannel(NotificationChannel(CH_SERVICE, "Hintergrundverbindung", NotificationManager.IMPORTANCE_MIN).apply {
            description = "Hält die Verbindung zum Herbstchat-Server offen"; setShowBadge(false)
        })
    }

    fun openIntent(ctx: Context, chat: Int? = null): PendingIntent {
        val i = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (chat != null) i.putExtra("chat", chat)
        return PendingIntent.getActivity(ctx, chat ?: 0, i, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    private fun allowed(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun post(ctx: Context, id: Int, b: NotificationCompat.Builder) {
        if (!allowed(ctx)) return
        try { NotificationManagerCompat.from(ctx).notify(id, b.build()) } catch (_: SecurityException) {}
    }

    private fun color(): Int = try { android.graphics.Color.parseColor(ChatCore.settings.accent) } catch (_: Exception) { 0xFF0066CC.toInt() }

    fun message(ctx: Context, from: Int, nick: String, text: String) {
        val preview = if (ChatCore.settings.notifyPreview) text.take(300) else "Neue Nachricht"
        val n = ChatCore.unread().optInt(from.toString(), 1)
        post(ctx, 1000 + from, NotificationCompat.Builder(ctx, CH_MSG)
            .setSmallIcon(R.drawable.ic_notification).setColor(color())
            .setContentTitle(if (n > 1) "$nick ($n neue)" else "Nachricht von $nick")
            .setContentText(preview).setStyle(NotificationCompat.BigTextStyle().bigText(preview))
            .setCategory(NotificationCompat.CATEGORY_MESSAGE).setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true).setContentIntent(openIntent(ctx, from)))
    }

    fun notice(ctx: Context, text: String) = post(ctx, ID_NOTICE, NotificationCompat.Builder(ctx, CH_SYS)
        .setSmallIcon(R.drawable.ic_notification).setColor(color())
        .setContentTitle("Herbstchat – Systemnachricht").setContentText(text)
        .setStyle(NotificationCompat.BigTextStyle().bigText(text)).setAutoCancel(true).setContentIntent(openIntent(ctx)))

    fun online(ctx: Context, nick: String) = post(ctx, ID_ONLINE, NotificationCompat.Builder(ctx, CH_SYS)
        .setSmallIcon(R.drawable.ic_notification).setColor(color())
        .setContentTitle("$nick ist jetzt online").setAutoCancel(true).setTimeoutAfter(60000).setContentIntent(openIntent(ctx)))

    fun service(ctx: Context): android.app.Notification {
        val c = ChatCore
        val text = when {
            c.connected && c.me != null -> "Verbunden als ${c.me!!.nick} · ${STATUS_LABEL[c.myStatus]}"
            else -> c.connLabel
        }
        return NotificationCompat.Builder(ctx, CH_SERVICE)
            .setSmallIcon(R.drawable.ic_notification).setColor(color())
            .setContentTitle("Herbstchat").setContentText(text).setOngoing(true).setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_MIN).setContentIntent(openIntent(ctx)).build()
    }

    fun cancel(ctx: Context, from: Int) = NotificationManagerCompat.from(ctx).cancel(1000 + from)
    fun cancelAll(ctx: Context) {
        val nm = NotificationManagerCompat.from(ctx)
        nm.activeNotifications.forEach { if (it.id != ID_SERVICE) nm.cancel(it.id) }
    }
}
