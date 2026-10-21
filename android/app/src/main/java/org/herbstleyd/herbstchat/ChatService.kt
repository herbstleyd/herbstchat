package org.herbstleyd.herbstchat

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/** Vordergrund-Dienst: hält die Verbindung offen, damit Nachrichten auch im Hintergrund ankommen. */
class ChatService : Service() {
    private var netCb: ConnectivityManager.NetworkCallback? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ChatCore.init(this)
        val cm = getSystemService(ConnectivityManager::class.java)
        netCb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { android.os.Handler(mainLooper).post { ChatCore.kick() } }
        }
        try { cm.registerDefaultNetworkCallback(netCb!!) } catch (_: Exception) {}
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            if (Build.VERSION.SDK_INT >= 34)
                startForeground(Notifier.ID_SERVICE, Notifier.service(this), ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING)
            else startForeground(Notifier.ID_SERVICE, Notifier.service(this))
        } catch (e: Exception) { stopSelf(); return START_NOT_STICKY }
        if (!ChatCore.loggedIn && !ChatCore.resumeIfPossible()) { stopSelf(); return START_NOT_STICKY }
        return START_STICKY
    }

    override fun onDestroy() {
        netCb?.let { try { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(it) } catch (_: Exception) {} }
        super.onDestroy()
    }

    companion object {
        var running = false; private set
        fun start(ctx: Context) {
            if (!ChatCore.settings.background) return
            try { ContextCompat.startForegroundService(ctx, Intent(ctx, ChatService::class.java)); running = true } catch (_: Exception) {}
        }
        fun stop(ctx: Context) { running = false; ctx.stopService(Intent(ctx, ChatService::class.java)) }
        fun update(ctx: Context) {
            if (!running) return
            try { NotificationManagerCompat.from(ctx).notify(Notifier.ID_SERVICE, Notifier.service(ctx)) } catch (_: SecurityException) {}
        }
    }
}
