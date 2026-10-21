package org.herbstleyd.herbstchat

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        ChatCore.init(context)
        if (ChatCore.settings.background && ChatCore.hasSession()) ChatService.start(context)
    }
}
