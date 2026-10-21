package org.herbstleyd.herbstchat

import android.os.Handler
import android.os.Looper
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * WebSocket über TLS (wss://host:port/ws). Das Server-Zertifikat ist selbstsigniert, daher
 * Trust-On-First-Use: der SHA-256-Fingerabdruck des Zertifikats (DER) wird beim ersten Verbinden
 * bestätigt und danach fest gepinnt – identisch zum Desktop-Client.
 */
class Connection(private val pins: Pins, private val listener: Listener) {
    interface Listener {
        fun onOpen()
        fun onMessage(d: JSONObject)
        fun onClosed(error: String?, pinProblem: PinProblem?)
    }

    data class PinProblem(val key: String, val fingerprint: String, val changed: Boolean)

    private val main = Handler(Looper.getMainLooper())
    private var ws: WebSocket? = null
    private var generation = 0
    var isOpen = false; private set
    var key = ""; private set

    private inner class PinTrust(val key: String) : X509TrustManager {
        @Volatile var seen: String? = null
        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        override fun checkServerTrusted(chain: Array<out X509Certificate>, authType: String?) {
            val fp = Crypto.hex(Crypto.sha256(chain[0].encoded))
            seen = fp
            if (pins.get(key) != fp) throw CertificateException("Zertifikat nicht vertrauenswürdig (Pin)")
        }
    }

    fun open(host: String, port: Int) {
        close()
        val gen = ++generation
        key = "$host:$port"
        val tm = PinTrust(key)
        val ctx = SSLContext.getInstance("TLS").apply { init(null, arrayOf(tm), null) }
        val client = OkHttpClient.Builder()
            .sslSocketFactory(ctx.socketFactory, tm)
            .hostnameVerifier { _, _ -> true }   // Echtheit wird über den Zertifikat-Pin geprüft
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.SECONDS)
            .pingInterval(30, TimeUnit.SECONDS)
            .build()
        val req = Request.Builder().url("https://$host:$port/ws").build()
        ws = client.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) = post(gen) {
                isOpen = true; listener.onOpen()
            }
            override fun onMessage(webSocket: WebSocket, text: String) = post(gen) {
                try { listener.onMessage(JSONObject(text)) } catch (_: Exception) {}
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(1000, null) }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = post(gen) {
                finish(null, null)
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) = post(gen) {
                val fp = tm.seen
                val pin = if (fp != null && pins.get(key) != fp) PinProblem(key, fp, pins.has(key)) else null
                finish(t.message ?: t.javaClass.simpleName, pin)
            }
        })
    }

    private fun finish(err: String?, pin: PinProblem?) {
        isOpen = false; ws = null; generation++
        listener.onClosed(err, pin)
    }

    private fun post(gen: Int, fn: () -> Unit) { main.post { if (gen == generation) fn() } }

    fun send(obj: JSONObject): Boolean {
        val w = ws
        return if (isOpen && w != null) w.send(obj.toString()) else false
    }

    /** Schließt ohne Callback */
    fun close() {
        generation++
        ws?.close(1000, null); ws?.cancel(); ws = null; isOpen = false
    }

    companion object {
        fun nice(fp: String) = fp.chunked(2).joinToString(":").uppercase()
    }
}
