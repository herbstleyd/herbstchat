package org.herbstleyd.herbstchat

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

const val DEFAULT_SERVER = ""   // eigene Serveradresse beim ersten Start eintragen
const val DEFAULT_PORT = 47474
const val WEBSITE = "https://herbstleyd.org"
const val VERSION = "1.1.2"

class Settings(ctx: Context) {
    private val p: SharedPreferences = ctx.getSharedPreferences("settings", Context.MODE_PRIVATE)
    var server: String get() = p.getString("server", DEFAULT_SERVER)!!; set(v) = p.edit().putString("server", v).apply()
    var port: Int get() = p.getInt("port", DEFAULT_PORT); set(v) = p.edit().putInt("port", v).apply()
    var lastNick: String get() = p.getString("last_nick", "")!!; set(v) = p.edit().putString("last_nick", v).apply()
    var rememberNick by BoolPref(p, "remember_nick", true)
    var stayLoggedIn by BoolPref(p, "stay_logged_in", true)
    var theme: String get() = p.getString("theme", "dunkel")!!; set(v) = p.edit().putString("theme", v).apply()
    var accent: String get() = p.getString("accent", ACCENT_DEFAULT)!!.let { if (it in ACCENTS.values) it else ACCENT_DEFAULT }; set(v) = p.edit().putString("accent", v).apply()
    var fontScale: Float get() = p.getFloat("font_scale", 1f); set(v) = p.edit().putFloat("font_scale", v).apply()
    var showTime by BoolPref(p, "show_time", true)
    var compact by BoolPref(p, "compact", false)
    var showOffline by BoolPref(p, "show_offline", true)
    var enterSends by BoolPref(p, "enter_sends", false)
    var notify by BoolPref(p, "notify", true)
    var notifyPreview by BoolPref(p, "notify_preview", true)
    var notifyOnline by BoolPref(p, "notify_online", false)
    var sendTyping by BoolPref(p, "send_typing", true)
    var saveHistory by BoolPref(p, "save_history", true)
    var background by BoolPref(p, "background", true)
    var startStatus: String get() = p.getString("start_status", "online")!!; set(v) = p.edit().putString("start_status", v).apply()

    fun resetDefaults() {
        val keep = listOf("server", "port", "last_nick")
        val e = p.edit()
        p.all.keys.filter { it !in keep }.forEach { e.remove(it) }
        e.apply()
    }

    private class BoolPref(val p: SharedPreferences, val key: String, val def: Boolean) {
        operator fun getValue(t: Any?, prop: Any?): Boolean = p.getBoolean(key, def)
        operator fun setValue(t: Any?, prop: Any?, v: Boolean) = p.edit().putBoolean(key, v).apply()
    }
}

/** TLS-Zertifikat-Pins (Trust-On-First-Use), wie server_pins.json am Desktop */
class Pins(ctx: Context) {
    private val p = ctx.getSharedPreferences("server_pins", Context.MODE_PRIVATE)
    fun get(key: String): String? = p.getString(key, null)
    fun has(key: String) = p.contains(key)
    fun put(key: String, fp: String) = p.edit().putString(key, fp).apply()
    fun clear() = p.edit().clear().apply()
}

/**
 * "Angemeldet bleiben": Auth- und Tresor-Schlüssel werden mit einem Schlüssel aus dem
 * Android-Keystore (hardwaregestützt, nicht exportierbar) verschlüsselt gespeichert.
 * Das Passwort selbst wird nie gespeichert.
 */
class SessionStore(ctx: Context) {
    private val p = ctx.getSharedPreferences("session", Context.MODE_PRIVATE)
    private val alias = "herbstchat_session"

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(alias, null) as? SecretKey)?.let { return it }
        val kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        kg.init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return kg.generateKey()
    }

    data class Session(val nick: String, val auth: ByteArray, val vault: ByteArray, val salt: ByteArray,
                       val server: String, val port: Int)

    fun save(s: Session) {
        val js = JSONObject().put("nick", s.nick).put("auth", Crypto.b64e(s.auth)).put("vault", Crypto.b64e(s.vault))
            .put("salt", Crypto.b64e(s.salt)).put("server", s.server).put("port", s.port).toString()
        val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE, key())
        val ct = c.doFinal(js.toByteArray())
        p.edit().putString("iv", Crypto.b64e(c.iv)).putString("data", Crypto.b64e(ct)).apply()
    }

    fun load(): Session? = try {
        val iv = p.getString("iv", null); val data = p.getString("data", null)
        if (iv == null || data == null) null else {
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Crypto.b64d(iv)))
            val j = JSONObject(String(c.doFinal(Crypto.b64d(data))))
            Session(j.getString("nick"), Crypto.b64d(j.getString("auth")), Crypto.b64d(j.getString("vault")),
                Crypto.b64d(j.getString("salt")), j.getString("server"), j.getInt("port"))
        }
    } catch (e: Exception) { null }

    fun has() = p.contains("data")
    fun clear() = p.edit().clear().apply()
}

/** Lokales Profil (Verlauf, bekannte Schlüssel, ungelesen, Namen) – mit dem Tresor-Schlüssel verschlüsselt. */
class ProfileFile(private val dir: File) {
    fun file(uid: Int, server: String) = File(dir, "profile_${uid}_${server.replace(Regex("[^A-Za-z0-9._-]"), "_")}.dat")

    fun load(uid: Int, server: String, vault: ByteArray): JSONObject = try {
        JSONObject(String(Crypto.secretDecrypt(vault, file(uid, server).readBytes()), Charsets.UTF_8))
    } catch (e: Exception) { JSONObject() }

    fun save(uid: Int, server: String, vault: ByteArray, obj: JSONObject) {
        val f = file(uid, server); val tmp = File(f.path + ".tmp")
        tmp.writeBytes(Crypto.secretEncrypt(vault, obj.toString().toByteArray(Charsets.UTF_8)))
        tmp.renameTo(f)
    }
}
