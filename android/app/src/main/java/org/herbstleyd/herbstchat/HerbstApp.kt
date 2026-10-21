package org.herbstleyd.herbstchat

import android.app.Application

class HerbstApp : Application() {
    override fun onCreate() {
        super.onCreate()
        ChatCore.init(this)
        Notifier.channels(this)
    }
}
