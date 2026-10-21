package org.herbstleyd.herbstchat

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts

class MainActivity : ComponentActivity() {
    private val notifPerm = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        ChatCore.init(this)
        if (!Crypto.selfTest()) ChatCore.alert = Alert("Herbstchat", "Die Kryptobibliothek (libsodium) konnte nicht geladen werden.")
        if (!ChatCore.loggedIn) ChatCore.resumeIfPossible()
        handleIntent(intent)
        if (Build.VERSION.SDK_INT >= 33) notifPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
        setContent { HerbstchatApp() }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(i: Intent?) {
        val chat = i?.getIntExtra("chat", -1) ?: -1
        if (chat >= 0 && ChatCore.loggedIn) ChatCore.openChat(chat)
    }

    override fun onResume() {
        super.onResume()
        ChatCore.visible = true
        ChatCore.current?.let { ChatCore.openChat(it) }
        ChatCore.kick()
    }

    override fun onPause() {
        ChatCore.visible = false
        super.onPause()
    }
}
