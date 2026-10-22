package org.herbstleyd.herbstchat

import android.annotation.SuppressLint
import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.Executors

val STATUS_LABEL = mapOf("online" to "Online", "away" to "Abwesend", "busy" to "Beschäftigt",
    "invisible" to "Unsichtbar", "offline" to "Offline")
val STATUS_COLOR = mapOf("online" to 0xFF3BB54A, "away" to 0xFFF1C40F, "busy" to 0xFFE74C3C,
    "invisible" to 0xFF95A5A6, "offline" to 0xFF7F8C8D)
val MY_STATUSES = listOf("online", "away", "busy", "invisible")

data class Me(val id: Int, var nick: String, var email: String, val pubkey: String)
data class Contact(val id: Int, var nick: String, var pubkey: String, var status: String)
data class Msg(val me: Boolean, val text: String, val ts: Double, val cid: String? = null,
               var state: String? = null, val sys: Boolean = false, var err: String? = null,
               /** Server-Verlaufs-ID (Sync); 0 = alter Verlauf bereits hochgeladen, null = nur lokal */
               var h: Int? = null) {
    fun toJson(): JSONObject = JSONObject().apply {
        if (sys) put("sys", true) else put("me", me)
        put("text", text); put("ts", ts)
        cid?.let { put("cid", it) }; state?.let { put("state", it) }; err?.let { put("err", it) }
        h?.let { put("h", it) }
    }
    companion object {
        fun from(j: JSONObject) = Msg(j.optBoolean("me"), j.optString("text"), j.optDouble("ts", 0.0),
            j.optString("cid").ifEmpty { null }, j.optString("state").ifEmpty { null }, j.optBoolean("sys"),
            j.optString("err").ifEmpty { null }, if (j.has("h")) j.optInt("h") else null)
    }
}

enum class Phase { LOGIN, CONNECTING, READY }
data class Alert(val title: String, val text: String)

/**
 * Zentrale Chat-Logik (Protokoll identisch zum Desktop-Client). Läuft im App-Prozess und wird
 * vom Vordergrund-Dienst [ChatService] am Leben gehalten. Alle Methoden laufen auf dem Main-Thread.
 */
@SuppressLint("StaticFieldLeak")
object ChatCore : Connection.Listener {
    lateinit var app: Context; private set
    lateinit var settings: Settings; private set
    lateinit var pins: Pins; private set
    private lateinit var sessions: SessionStore
    private lateinit var profiles: ProfileFile
    private lateinit var conn: Connection
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()

    // ---- beobachtbarer UI-Zustand
    var rev by mutableIntStateOf(0); private set
    var phase by mutableStateOf(Phase.LOGIN); private set
    var loginBusy by mutableStateOf(false); private set
    var loginStatus by mutableStateOf(""); private set
    var loginError by mutableStateOf(false); private set
    var registeredNick by mutableStateOf<String?>(null)
    var connected by mutableStateOf(false); private set
    var connLabel by mutableStateOf("Nicht verbunden"); private set
    var myStatus by mutableStateOf("online"); private set
    var pinProblem by mutableStateOf<Connection.PinProblem?>(null)
    var alert by mutableStateOf<Alert?>(null)
    var searchResults by mutableStateOf<List<Pair<Int, String>>?>(null)
    var current by mutableStateOf<Int?>(null)
    var visible = false
    var themeRev by mutableIntStateOf(0)

    var me: Me? = null; private set
    val contacts = LinkedHashMap<Int, Contact>()
    private var auth: ByteArray? = null
    private var vault: ByteArray? = null
    private var kdfSalt: ByteArray? = null
    private var priv: ByteArray? = null
    private var profile = JSONObject()
    private val pending = LinkedHashMap<String, JSONObject>()
    val typingFrom = HashMap<Int, Long>()
    private var typingSent = 0L

    private sealed class Pending {
        data class Register(val mail: String, val nick: String, val pw: String) : Pending()
        data class Login(val nick: String, val pw: String, val remember: Boolean) : Pending()
        data class Resume(val nick: String, val remember: Boolean) : Pending()
    }
    private var pendingAction: Pending? = null
    private var manualLogout = false
    private var rememberSession = false
    private var reconnectDelay = 3000L
    private var pwPending: Triple<ByteArray, ByteArray, ByteArray>? = null
    /** Chunks für den einmaligen Import des alten lokalen Verlaufs */
    private val uploadQueue = ArrayList<List<Pair<JSONObject, Msg>>>()

    private val reconnectRunnable = Runnable { reconnect() }
    private val pingRunnable = object : Runnable {
        override fun run() { send(JSONObject().put("t", "ping")); main.postDelayed(this, 25000) }
    }

    fun init(ctx: Context) {
        if (::app.isInitialized) return
        app = ctx.applicationContext
        settings = Settings(app); pins = Pins(app); sessions = SessionStore(app)
        profiles = ProfileFile(app.filesDir)
        conn = Connection(pins, this)
        myStatus = settings.startStatus
    }

    private fun bump() { rev++ }
    val loggedIn get() = me != null
    fun hasSession() = sessions.has()

    // ------------------------------------------------------------------ Login / Registrierung
    fun startLogin(nick: String, pw: String, remember: Boolean) {
        manualLogout = false
        pendingAction = Pending.Login(nick, pw, remember)
        setLogin(true, "Verbinde ...")
        conn.open(settings.server, settings.port)
    }

    fun startRegister(mail: String, nick: String, pw: String) {
        manualLogout = false
        pendingAction = Pending.Register(mail, nick, pw)
        setLogin(true, "Verbinde ...")
        conn.open(settings.server, settings.port)
    }

    /** Automatische Anmeldung mit gespeicherter Sitzung (z. B. nach Neustart). */
    fun resumeIfPossible(): Boolean {
        if (me != null || pendingAction != null) return true
        val s = sessions.load() ?: return false
        if (s.server != settings.server || s.port != settings.port) { sessions.clear(); return false }
        auth = s.auth; vault = s.vault; kdfSalt = s.salt
        manualLogout = false
        pendingAction = Pending.Resume(s.nick, true)
        phase = Phase.CONNECTING; connLabel = "Verbinde mit ${settings.server} ..."
        conn.open(settings.server, settings.port)
        ChatService.start(app)
        return true
    }

    fun cancelResume() { logout() }

    private fun setLogin(busy: Boolean, text: String, error: Boolean = false) {
        loginBusy = busy; loginStatus = text; loginError = error
    }

    private fun loginFail(msg: String) {
        val wasResume = pendingAction is Pending.Resume
        pendingAction = null
        if (wasResume || phase == Phase.CONNECTING) {
            sessions.clear(); auth = null; vault = null; kdfSalt = null
            phase = Phase.LOGIN; ChatService.stop(app)
        }
        setLogin(false, msg, true)
    }

    override fun onOpen() {
        connected = true; reconnectDelay = 3000L
        connLabel = "Verbunden mit ${settings.server}"
        main.removeCallbacks(reconnectRunnable)
        main.removeCallbacks(pingRunnable); main.postDelayed(pingRunnable, 25000)
        when (val pa = pendingAction) {
            is Pending.Register -> {
                setLogin(true, "Erzeuge Schlüssel und registriere ...")
                worker.execute {
                    val salt = Crypto.random(Crypto.SALT_BYTES)
                    val (a, v) = Crypto.derive(pa.pw, salt)
                    val (pk, sk) = Crypto.keypair()
                    val enc = Crypto.secretEncrypt(v, sk)
                    main.post {
                        send(JSONObject().put("t", "register").put("email", pa.mail).put("nick", pa.nick)
                            .put("salt", Crypto.b64e(salt)).put("auth", Crypto.b64e(a))
                            .put("pubkey", Crypto.b64e(pk)).put("enc_priv", Crypto.b64e(enc)))
                    }
                }
            }
            is Pending.Login -> send(JSONObject().put("t", "prelogin").put("nick", pa.nick))
            is Pending.Resume -> sendLogin(pa.nick)
            null -> if (me != null && auth != null) sendLogin(me!!.nick)
        }
        bump()
    }

    private fun sendLogin(nick: String) {
        send(JSONObject().put("t", "login").put("nick", nick).put("auth", Crypto.b64e(auth!!)).put("status", myStatus))
    }

    override fun onClosed(error: String?, pinProblem: Connection.PinProblem?) {
        connected = false
        main.removeCallbacks(pingRunnable)
        contacts.values.forEach { it.status = "offline" }
        if (pinProblem != null) {
            this.pinProblem = pinProblem
            connLabel = "Zertifikat muss bestätigt werden"
            if (pendingAction is Pending.Login || pendingAction is Pending.Register) setLogin(false, "")
            bump(); ChatService.update(app); return
        }
        val pa = pendingAction
        if (pa is Pending.Login || pa is Pending.Register) {
            pendingAction = null
            setLogin(false, "Verbindung fehlgeschlagen: " + (error ?: "Server nicht erreichbar."), true)
        } else if ((me != null || pa is Pending.Resume) && !manualLogout) {
            connLabel = "Verbindung getrennt – neuer Versuch ..."
            main.removeCallbacks(reconnectRunnable)
            main.postDelayed(reconnectRunnable, reconnectDelay)
            reconnectDelay = (reconnectDelay * 2).coerceAtMost(60000L)
        } else connLabel = "Nicht verbunden"
        bump(); ChatService.update(app)
    }

    fun reconnect() {
        main.removeCallbacks(reconnectRunnable)
        if ((me != null || pendingAction is Pending.Resume) && !manualLogout && !conn.isOpen)
            conn.open(settings.server, settings.port)
    }

    /** Wird bei Netzwechsel/App-Start aufgerufen: sofort neu verbinden statt auf Timer zu warten. */
    fun kick() { if (!connected) { reconnectDelay = 3000L; reconnect() } }

    fun acceptPin(p: Connection.PinProblem) {
        pins.put(p.key, p.fingerprint); pinProblem = null
        val pa = pendingAction
        when {
            pa is Pending.Login -> startLogin(pa.nick, pa.pw, pa.remember)
            pa is Pending.Register -> startRegister(pa.mail, pa.nick, pa.pw)
            else -> reconnect()
        }
    }

    fun rejectPin() {
        pinProblem = null
        val pa = pendingAction
        if (pa is Pending.Login || pa is Pending.Register) { pendingAction = null; setLogin(false, "Verbindung abgebrochen.", true) }
        else if (pa is Pending.Resume && me == null) { loginFail("Verbindung abgebrochen (Zertifikat).") }
        else { connLabel = "Verbindung abgebrochen (Zertifikat)" }
    }

    // ------------------------------------------------------------------ Eingehende Nachrichten
    override fun onMessage(d: JSONObject) {
        when (d.optString("t")) {
            "salt" -> {
                val pa = pendingAction as? Pending.Login ?: return
                setLogin(true, "Prüfe Passwort ...")
                val salt = Crypto.b64d(d.getString("salt"))
                worker.execute {
                    val (a, v) = Crypto.derive(pa.pw, salt)
                    main.post {
                        if (pendingAction !== pa) return@post
                        kdfSalt = salt; auth = a; vault = v
                        sendLogin(pa.nick)
                    }
                }
            }
            "register_ok" -> {
                val pa = pendingAction as? Pending.Register ?: return
                pendingAction = null
                setLogin(true, "Account erstellt – du wirst angemeldet ...")
                registeredNick = pa.nick
                conn.close()
                startLogin(pa.nick, pa.pw, settings.stayLoggedIn)
            }
            "login_ok" -> loginOk(d)
            "error" -> {
                val ctx = d.optString("ctx"); val msg = d.optString("msg", "Fehler")
                val pa = pendingAction
                when {
                    (ctx == "login" || ctx == "register") && pa != null -> { conn.close(); connected = false; loginFail(msg) }
                    ctx == "login" -> { manualLogout = true; alert = Alert("Herbstchat", msg); logout() }
                    ctx == "msg" -> markFailed(d.optString("cid"), msg)
                    else -> alert = Alert("Herbstchat", msg)
                }
            }
            "msg" -> incoming(d)
            "sent" -> {
                val cid = d.optString("cid"); pending.remove(cid)
                findCid(cid)?.let { it.state = if (d.optBoolean("queued")) "queued" else "sent"; saveProfile() }
            }
            "presence" -> {
                val c = contacts[d.optInt("id")] ?: return
                val was = c.status; c.status = d.optString("status", "offline")
                if (was == "offline" && c.status != "offline" && settings.notifyOnline && !visible)
                    Notifier.online(app, c.nick)
            }
            "contact" -> { val c = d.getJSONObject("contact"); addKnown(c); current = c.getInt("id") }
            "contact_removed" -> contacts.remove(d.optInt("id"))
            "search" -> {
                val arr = d.optJSONArray("results") ?: JSONArray()
                searchResults = (0 until arr.length()).map { arr.getJSONObject(it).let { r -> r.getInt("id") to r.getString("nick") } }
            }
            "typing" -> typingFrom[d.optInt("from")] = System.currentTimeMillis()
            "renamed" -> {
                if (d.optBoolean("self") && me != null) {
                    me!!.nick = d.getString("nick")
                    alert = Alert("Herbstchat", "Dein Nickname wurde vom Administrator in \"${d.getString("nick")}\" geändert.")
                    ChatService.update(app)
                } else contacts[d.optInt("id")]?.let {
                    it.nick = d.getString("nick"); names().put(it.id.toString(), it.nick)
                }
            }
            "notice" -> {
                val text = d.optString("text")
                alert = Alert("Systemnachricht vom Administrator", text)
                if (!visible) Notifier.notice(app, text)
            }
            "kicked" -> {
                manualLogout = true
                alert = Alert("Herbstchat", d.optString("reason", "Verbindung getrennt."))
                logout()
            }
            "password_ok" -> {
                val (s, a, v) = pwPending ?: return
                val m = me ?: return
                val oldVault = vault
                kdfSalt = s; auth = a; vault = v; pwPending = null
                saveProfile()
                if (oldVault != null && rememberSession) sessions.save(SessionStore.Session(m.nick, a, v, s, settings.server, settings.port))
                alert = Alert("Herbstchat", "Passwort erfolgreich geändert.")
            }
            "email_ok" -> { me?.email = d.optString("email"); alert = Alert("Herbstchat", "E-Mail-Adresse geändert.") }
            "history_delta" -> historyMerge(d)
            "history_uploaded" -> historyUploadNext(false)
            "msg_copy" -> msgCopy(d)
            "user" -> addKnown(d.getJSONObject("user"), persist = false)
        }
        bump()
    }

    private fun loginOk(d: JSONObject) {
        val first = me == null
        if (first) {
            try {
                priv = Crypto.secretDecrypt(vault!!, Crypto.b64d(d.getString("enc_priv")))
            } catch (e: Exception) {
                conn.close(); loginFail("Privater Schlüssel konnte nicht entschlüsselt werden."); return
            }
            val m = Me(d.getInt("id"), d.getString("nick"), d.optString("email"), d.getString("pubkey"))
            me = m
            loadProfile()
            val pa = pendingAction
            rememberSession = when (pa) { is Pending.Login -> pa.remember; is Pending.Resume -> pa.remember; else -> false }
            if (rememberSession) sessions.save(SessionStore.Session(m.nick, auth!!, vault!!, kdfSalt!!, settings.server, settings.port))
            else sessions.clear()
            if (settings.rememberNick) settings.lastNick = m.nick
            pendingAction = null
            setLogin(false, "")
            phase = Phase.READY
            ChatService.start(app)
            d.optString("motd").takeIf { it.isNotBlank() }?.let { alert = Alert("Nachricht des Tages", it) }
        }
        contacts.clear()
        val arr = d.optJSONArray("contacts") ?: JSONArray()
        for (i in 0 until arr.length()) addKnown(arr.getJSONObject(i))
        for (item in pending.values.toList()) send(item)
        uploadQueue.clear()
        if (d.has("history_counter"))      // Server >= 1.1 kann Verlauf synchronisieren
            send(JSONObject().put("t", "history_delta").put("since", profile.optInt("history_last", 0)))
        ChatService.update(app)
    }

    // ------------------------------------------------------------------ Profil
    private fun obj(k: String): JSONObject = profile.optJSONObject(k) ?: JSONObject().also { profile.put(k, it) }
    fun names() = obj("names")
    fun keys() = obj("keys")
    fun unread() = obj("unread")
    private val historyCache = HashMap<String, MutableList<Msg>>()

    fun history(cid: Int): MutableList<Msg> = historyCache.getOrPut(cid.toString()) {
        val arr = obj("history").optJSONArray(cid.toString()) ?: JSONArray()
        MutableList(arr.length()) { Msg.from(arr.getJSONObject(it)) }
    }

    private fun loadProfile() {
        val m = me ?: return
        profile = profiles.load(m.id, settings.server, vault!!)
        historyCache.clear()
        for (k in listOf("history", "keys", "unread", "names")) obj(k)
        if (!profile.has("history_last")) profile.put("history_last", 0)
        if (obj("history").length() == 0 && !profile.has("legacy_uploaded")) profile.put("legacy_uploaded", true)
        if (!profile.has("sync_start")) profile.put("sync_start", now())
    }

    fun saveProfile() {
        val m = me ?: return; val v = vault ?: return
        val h = obj("history")
        for ((k, list) in historyCache) h.put(k, JSONArray().apply { list.takeLast(2000).forEach { put(it.toJson()) } })
        val out = JSONObject(profile.toString())
        if (!settings.saveHistory) out.put("history", JSONObject())
        val snapshot = out
        worker.execute { try { profiles.save(m.id, settings.server, v, snapshot) } catch (_: Exception) {} }
        bump()
    }

    /** Löscht den Verlauf lokal und auf dem Server (damit auf allen Geräten). */
    fun clearAllHistory() {
        historyCache.clear(); profile.put("history", JSONObject()); profile.put("unread", JSONObject()); saveProfile()
        send(JSONObject().put("t", "history_clear"))
    }

    fun clearChat(cid: Int) {
        historyCache.remove(cid.toString()); obj("history").remove(cid.toString()); saveProfile()
        send(JSONObject().put("t", "history_clear").put("contact_id", cid))
    }

    // ------------------------------------------------------------------ Kontakte
    private fun addKnown(c: JSONObject, persist: Boolean = true) {
        val id = c.getInt("id"); val key = id.toString(); val pk = c.getString("pubkey")
        val known = keys().optString(key).ifEmpty { null }
        if (known != null && known != pk)
            history(id).add(Msg(false, "⚠ Der Schlüssel dieses Kontakts hat sich geändert. Bitte Sicherheitsnummer prüfen!",
                now(), sys = true))
        keys().put(key, pk); names().put(key, c.getString("nick"))
        if (persist) contacts[id] = Contact(id, c.getString("nick"), pk, c.optString("status", "offline"))
    }

    data class Row(val id: Int, val nick: String, val status: String, val unread: Int, val inContacts: Boolean, val last: Msg?)

    fun contactRows(filter: String): List<Row> {
        val order = mapOf("online" to 0, "away" to 1, "busy" to 2, "offline" to 3)
        val un = unread()
        val ids = contacts.keys.toMutableSet()
        un.keys().forEach { k -> if (un.optInt(k) > 0) k.toIntOrNull()?.let { ids.add(it) } }
        return ids.mapNotNull { id ->
            val c = contacts[id]
            val nick = c?.nick ?: names().optString(id.toString(), "#$id")
            val st = c?.status ?: "offline"
            val u = un.optInt(id.toString())
            if (filter.isNotBlank() && !nick.contains(filter, true)) return@mapNotNull null
            if (!settings.showOffline && st == "offline" && u == 0) return@mapNotNull null
            Row(id, nick, st, u, c != null, history(id).lastOrNull { !it.sys })
        }.sortedWith(compareBy({ order[it.status] ?: 3 }, { it.nick.lowercase() }))
    }

    fun nickOf(id: Int) = contacts[id]?.nick ?: names().optString(id.toString(), "?")
    fun statusOf(id: Int) = contacts[id]?.status ?: "offline"

    fun openChat(id: Int) {
        current = id
        if (unread().has(id.toString())) { unread().remove(id.toString()); saveProfile() }
        Notifier.cancel(app, id)
        bump()
    }

    fun search(q: String) = send(JSONObject().put("t", "search").put("q", q))
    fun addContact(id: Int) = send(JSONObject().put("t", "add_contact").put("id", id))
    fun removeContact(id: Int) { send(JSONObject().put("t", "remove_contact").put("id", id)); if (current == id) current = null }

    fun safetyNumber(id: Int): String? {
        val pk = keys().optString(id.toString()).ifEmpty { null } ?: return null
        return Crypto.safetyNumber(me!!.pubkey, pk)
    }

    // ------------------------------------------------------------------ Nachrichten
    private fun now() = System.currentTimeMillis() / 1000.0

    fun sendMessage(text: String): Boolean {
        val to = current ?: return false; val sk = priv ?: return false
        val pk = keys().optString(to.toString()).ifEmpty { null } ?: return false
        val cid = UUID.randomUUID().toString().replace("-", "")
        val body = JSONObject().put("text", text).put("ts", now()).toString().toByteArray(Charsets.UTF_8)
        val payload = Crypto.b64e(Crypto.boxEncrypt(sk, Crypto.b64d(pk), body))
        val item = JSONObject().put("t", "msg").put("to", to).put("payload", payload).put("cid", cid)
        pending[cid] = item
        history(to).add(Msg(true, text, now(), cid, "sending"))
        send(item); saveProfile()
        return true
    }

    private fun findCid(cid: String): Msg? {
        for (list in historyCache.values) list.asReversed().take(300).firstOrNull { it.cid == cid }?.let { return it }
        return null
    }

    private fun markFailed(cid: String, msg: String) {
        pending.remove(cid)
        findCid(cid)?.let { it.state = "failed"; it.err = msg; saveProfile() }
        alert = Alert("Senden fehlgeschlagen", msg)
    }

    private fun incoming(d: JSONObject) {
        val sender = d.getInt("from"); val key = sender.toString()
        d.optString("from_pubkey").takeIf { it.isNotEmpty() && !keys().has(key) }?.let { keys().put(key, it) }
        d.optString("from_nick").takeIf { it.isNotEmpty() }?.let { names().put(key, it) }
        val text = try {
            val pk = Crypto.b64d(keys().getString(key))
            JSONObject(String(Crypto.boxDecrypt(priv!!, pk, Crypto.b64d(d.getString("payload"))), Charsets.UTF_8)).optString("text")
        } catch (e: Exception) { "[Nachricht konnte nicht entschlüsselt werden]" }
        history(sender).add(Msg(false, text, d.optDouble("ts", now()), h = if (d.has("hid")) d.optInt("hid") else null))
        send(JSONObject().put("t", "ack").put("ids", JSONArray().put(d.get("id"))))
        typingFrom.remove(sender)
        val seen = visible && current == sender
        if (!seen) unread().put(key, unread().optInt(key) + 1)
        saveProfile()
        if (!seen && settings.notify && myStatus != "busy") Notifier.message(app, sender, nickOf(sender), text)
    }

    fun onTyping() {
        val to = current ?: return
        if (settings.sendTyping && System.currentTimeMillis() - typingSent > 3000) {
            typingSent = System.currentTimeMillis(); send(JSONObject().put("t", "typing").put("to", to))
        }
    }

    fun isTyping(id: Int) = typingFrom[id]?.let { System.currentTimeMillis() - it < 5000 } == true

    // ------------------------------------------------------------------ History Sync
    // Der Server speichert nur Chiffretext (NaCl Box zwischen mir und dem Kontakt).
    private fun hkey(me: Boolean, ts: Double, text: String) = "$me|${Math.round(ts * 1000)}|$text"

    private fun decryptFor(cid: Int, blob: String): String? = try {
        val pk = keys().optString(cid.toString()).ifEmpty { null }
        if (pk == null) null
        else JSONObject(String(Crypto.boxDecrypt(priv!!, Crypto.b64d(pk), Crypto.b64d(blob)), Charsets.UTF_8)).optString("text")
    } catch (_: Exception) { null }

    private fun historyMerge(d: JSONObject) {
        d.optJSONObject("users")?.let { users ->
            users.keys().forEach { k ->
                val u = users.optJSONObject(k)
                if (u != null) {
                    val pk = u.optString("pubkey")
                    if (pk.isNotEmpty() && !keys().has(k)) keys().put(k, pk)
                    val nick = u.optString("nick")
                    if (nick.isNotEmpty() && !names().has(k)) names().put(k, nick)
                }
            }
        }
        val delta = d.optJSONArray("delta") ?: JSONArray()
        val touched = HashSet<Int>()
        val byCid = HashMap<Int, HashMap<String, Msg>>()
        val seen = HashMap<Int, HashSet<String>>()
        for (i in 0 until delta.length()) {
            val e = delta.getJSONObject(i)
            val cid = e.getInt("contact_id")
            val text = decryptFor(cid, e.getString("blob")) ?: continue
            val list = history(cid)
            val cids = byCid.getOrPut(cid) { HashMap<String, Msg>().also { m -> list.forEach { x -> x.cid?.let { m[it] = x } } } }
            val keysSeen = seen.getOrPut(cid) { HashSet<String>().also { k -> list.filter { !it.sys }.forEach { k.add(hkey(it.me, it.ts, it.text)) } } }
            val out = e.optBoolean("out")
            val mcid = if (e.isNull("cid")) "" else e.optString("cid")
            val hid = e.getInt("id")
            val ts = e.getDouble("ts")
            if (out && mcid.isNotEmpty()) {
                val existing = cids[mcid]
                if (existing != null) {
                    if (existing.state == null || existing.state == "sending") existing.state = "sent"
                    if (existing.h == null) existing.h = hid
                    continue
                }
            }
            val k = hkey(out, ts, text)
            if (k in keysSeen) continue
            val m = Msg(out, text, ts, mcid.ifEmpty { null }, if (out) "sent" else null, h = hid)
            list.add(m); keysSeen.add(k); touched.add(cid)
            if (mcid.isNotEmpty()) cids[mcid] = m
        }
        for (cid in touched) history(cid).sortBy { it.ts }
        profile.put("history_last", maxOf(profile.optInt("history_last", 0), d.optInt("last", 0)))
        saveProfile()
        if (d.optBoolean("more")) send(JSONObject().put("t", "history_delta").put("since", profile.optInt("history_last", 0)))
        else if (!profile.optBoolean("legacy_uploaded")) historyUploadStart()
    }

    /** Einmalig: lokalen Verlauf von vor 1.1.2 hochladen, damit andere Geräte ihn sehen. */
    private fun historyUploadStart() {
        val sk = priv ?: return
        val cutoff = profile.optDouble("sync_start", now())
        uploadQueue.clear()
        var chunk = ArrayList<Pair<JSONObject, Msg>>(); var size = 0
        val ids = obj("history").keys().asSequence().toList() + historyCache.keys
        for (key in ids.distinct()) {
            val cid = key.toIntOrNull() ?: continue
            val pk = keys().optString(key).ifEmpty { null } ?: continue
            for (m in history(cid)) {
                if (m.sys || m.h != null || m.ts >= cutoff || m.state == "sending" || m.state == "failed") continue
                val body = JSONObject().put("text", m.text).put("ts", m.ts).toString().toByteArray(Charsets.UTF_8)
                val blob = Crypto.b64e(Crypto.boxEncrypt(sk, Crypto.b64d(pk), body))
                if (chunk.isNotEmpty() && (chunk.size >= 150 || size + blob.length > 90000)) {
                    uploadQueue.add(chunk); chunk = ArrayList(); size = 0
                }
                chunk.add(JSONObject().put("contact_id", cid).put("out", m.me).put("blob", blob).put("ts", m.ts) to m)
                size += blob.length + 80
            }
        }
        if (chunk.isNotEmpty()) uploadQueue.add(chunk)
        historyUploadNext(true)
    }

    private fun historyUploadNext(first: Boolean) {
        if (!first && uploadQueue.isNotEmpty()) uploadQueue.removeAt(0).forEach { it.second.h = 0 }
        if (uploadQueue.isNotEmpty()) {
            send(JSONObject().put("t", "history_upload").put("hv", 2)
                .put("entries", JSONArray().apply { uploadQueue[0].forEach { put(it.first) } }))
        } else if (!profile.optBoolean("legacy_uploaded")) {
            profile.put("legacy_uploaded", true); saveProfile()
        } else saveProfile()
    }

    /** Nachricht, die ich auf einem anderen Gerät gesendet habe. */
    private fun msgCopy(d: JSONObject) {
        val to = d.getInt("to"); val key = to.toString()
        d.optString("to_pubkey").takeIf { it.isNotEmpty() && !keys().has(key) }?.let { keys().put(key, it) }
        d.optString("to_nick").takeIf { it.isNotEmpty() }?.let { names().put(key, it) }
        val text = decryptFor(to, d.getString("payload")) ?: return
        val cid = if (d.isNull("cid")) "" else d.optString("cid")
        if (cid.isNotEmpty() && findCid(cid) != null) return
        history(to).add(Msg(true, text, d.optDouble("ts", now()), cid.ifEmpty { null }, "sent",
            h = if (d.has("hid")) d.optInt("hid") else 0))
        saveProfile()
    }

    // ------------------------------------------------------------------ Konto
    fun setStatus(st: String) {
        myStatus = st; settings.startStatus = st
        send(JSONObject().put("t", "status").put("status", st)); ChatService.update(app)
    }

    /** Liefert Fehlermeldung oder null; Ergebnis kommt asynchron als Alert. */
    fun changePassword(old: String, new: String, onError: (String) -> Unit) {
        val s = kdfSalt; val sk = priv
        if (s == null || sk == null) return onError("Nicht angemeldet.")
        worker.execute {
            val (oldAuth, _) = Crypto.derive(old, s)
            if (!oldAuth.contentEquals(auth)) { main.post { onError("Altes Passwort falsch.") }; return@execute }
            val salt = Crypto.random(Crypto.SALT_BYTES)
            val (a, v) = Crypto.derive(new, salt)
            val enc = Crypto.secretEncrypt(v, sk)
            main.post {
                pwPending = Triple(salt, a, v)
                send(JSONObject().put("t", "change_password").put("old_auth", Crypto.b64e(oldAuth))
                    .put("salt", Crypto.b64e(salt)).put("auth", Crypto.b64e(a)).put("enc_priv", Crypto.b64e(enc)))
            }
        }
    }

    fun changeEmail(mail: String) = send(JSONObject().put("t", "change_email").put("email", mail))

    fun send(obj: JSONObject) = conn.send(obj)

    fun logout() {
        manualLogout = true
        main.removeCallbacks(reconnectRunnable); main.removeCallbacks(pingRunnable)
        try { saveProfile() } catch (_: Exception) {}
        conn.close(); sessions.clear()
        me = null; auth = null; vault = null; priv = null; kdfSalt = null
        contacts.clear(); historyCache.clear(); profile = JSONObject(); pending.clear(); typingFrom.clear()
        current = null; pendingAction = null; connected = false; connLabel = "Nicht verbunden"
        phase = Phase.LOGIN; setLogin(false, "")
        ChatService.stop(app); Notifier.cancelAll(app)
        bump()
    }
}
